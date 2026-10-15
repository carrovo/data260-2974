from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Response, status
from hw6_schemas import (
    DocumentListingCreate,
    DocumentListingOut,
    DocumentListingUpdate,
)
from mongo_database import mongo_db_dependency
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError

router = APIRouter(
    prefix="/api/doc-listings",
    tags=["HW6 MongoDB Document Listings"],
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MongoDB document id.",
        )

    return ObjectId(value)


def _serialize(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "listingTitle": document["listingTitle"],
        "description": document.get("description"),
        "status": document["status"],
        "propertyType": document["propertyType"],
        "availableFrom": document["availableFrom"],
        "createdAt": document["createdAt"],
        "updatedAt": document["updatedAt"],
    }


def _database_error(action: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"MongoDB error while {action}.",
    )


@router.post(
    "",
    response_model=DocumentListingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_document_listing(
    payload: DocumentListingCreate,
    db: Database = Depends(mongo_db_dependency),
) -> dict:
    now = _utc_now()
    document = payload.model_dump(mode="python")
    document["status"] = payload.status.value
    document["propertyType"] = payload.propertyType.value
    document["createdAt"] = now
    document["updatedAt"] = now

    try:
        result = db.listings.insert_one(document)
        created = db.listings.find_one({"_id": result.inserted_id})
    except (DuplicateKeyError, PyMongoError) as exc:
        raise _database_error("creating the listing") from exc

    if created is None:
        raise _database_error("reading the created listing")

    return _serialize(created)


@router.get(
    "",
    response_model=list[DocumentListingOut],
)
def list_document_listings(
    db: Database = Depends(mongo_db_dependency),
) -> list[dict]:
    try:
        documents = list(db.listings.find().sort("createdAt", -1))
    except PyMongoError as exc:
        raise _database_error("listing documents") from exc

    return [_serialize(document) for document in documents]


@router.get(
    "/{listing_id}",
    response_model=DocumentListingOut,
)
def get_document_listing(
    listing_id: str,
    db: Database = Depends(mongo_db_dependency),
) -> dict:
    try:
        document = db.listings.find_one({"_id": _object_id(listing_id)})
    except PyMongoError as exc:
        raise _database_error("retrieving the listing") from exc

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document listing not found.",
        )

    return _serialize(document)


@router.put(
    "/{listing_id}",
    response_model=DocumentListingOut,
)
def update_document_listing(
    listing_id: str,
    payload: DocumentListingUpdate,
    db: Database = Depends(mongo_db_dependency),
) -> dict:
    object_id = _object_id(listing_id)
    updates = payload.model_dump(
        mode="python",
        exclude_unset=True,
    )

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field is required for update.",
        )

    if payload.status is not None:
        updates["status"] = payload.status.value

    if payload.propertyType is not None:
        updates["propertyType"] = payload.propertyType.value

    updates["updatedAt"] = _utc_now()

    try:
        result = db.listings.update_one(
            {"_id": object_id},
            {"$set": updates},
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document listing not found.",
            )

        document = db.listings.find_one({"_id": object_id})
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise _database_error("updating the listing") from exc

    if document is None:
        raise _database_error("reading the updated listing")

    return _serialize(document)


@router.delete(
    "/{listing_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document_listing(
    listing_id: str,
    db: Database = Depends(mongo_db_dependency),
) -> Response:
    try:
        result = db.listings.delete_one({"_id": _object_id(listing_id)})
    except PyMongoError as exc:
        raise _database_error("deleting the listing") from exc

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document listing not found.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
