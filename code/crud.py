from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from models import PropertyManager, RentalListing
from schemas import (
    ListingCreate,
    ListingUpdate,
    PropertyManagerCreate,
    PropertyManagerUpdate,
)


# ---------------------------------------------------------
# Property managers
# ---------------------------------------------------------

def create_property_manager(
    db: Session,
    payload: PropertyManagerCreate,
) -> PropertyManager:
    """Create and persist one property manager."""

    data = payload.model_dump()
    data["email"] = str(payload.email).lower()

    manager = PropertyManager(**data)
    db.add(manager)

    try:
        db.commit()
        db.refresh(manager)
        return manager
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Property manager email must be unique",
        ) from exc


def list_property_managers(
    db: Session,
    skip: int = 0,
    limit: int = 50,
) -> list[PropertyManager]:
    """Return property managers with pagination."""

    statement = (
        select(PropertyManager)
        .order_by(PropertyManager.id)
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def get_property_manager(
    db: Session,
    manager_id: int,
) -> PropertyManager:
    """Return one property manager or a 404 error."""

    manager = db.get(PropertyManager, manager_id)

    if manager is None:
        raise HTTPException(
            status_code=404,
            detail="Property manager not found",
        )

    return manager


def update_property_manager(
    db: Session,
    manager_id: int,
    payload: PropertyManagerUpdate,
) -> PropertyManager:
    """Update the supplied property-manager fields."""

    manager = get_property_manager(db, manager_id)

    data = payload.model_dump(
        exclude_unset=True,
        exclude_none=True,
    )

    if "email" in data:
        data["email"] = str(data["email"]).lower()

    for field_name, value in data.items():
        setattr(manager, field_name, value)

    try:
        db.commit()
        db.refresh(manager)
        return manager
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Property manager email must be unique",
        ) from exc


def delete_property_manager(
    db: Session,
    manager_id: int,
) -> None:
    """Delete a manager only when no listings reference it."""

    manager = get_property_manager(db, manager_id)

    listing_count = db.scalar(
        select(func.count(RentalListing.id)).where(
            RentalListing.propertyManagerId == manager_id
        )
    )

    if listing_count and listing_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete a property manager "
                "with associated rental listings"
            ),
        )

    db.delete(manager)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete a property manager "
                "with associated rental listings"
            ),
        ) from exc


# ---------------------------------------------------------
# Rental listings
# ---------------------------------------------------------

def create_listing(
    db: Session,
    payload: ListingCreate,
) -> RentalListing:
    """Create and persist one rental listing."""

    if db.get(
        PropertyManager,
        payload.propertyManagerId,
    ) is None:
        raise HTTPException(
            status_code=404,
            detail="Property manager not found",
        )

    data = payload.model_dump()
    data["submitterEmail"] = str(
        payload.submitterEmail
    ).lower()

    listing = RentalListing(**data)
    db.add(listing)

    try:
        db.commit()
        db.refresh(listing)
        return listing
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Listing code must be unique",
        ) from exc


def get_listings_naive(
    db: Session,
    skip: int = 0,
    limit: int = 50,
) -> list[RentalListing]:
    """
    Return listings using the intentional HW4 N+1 pattern.

    Accessing listing.events triggers an additional query
    for each listing.
    """

    statement = (
        select(RentalListing)
        .order_by(RentalListing.id)
        .offset(skip)
        .limit(limit)
    )

    listings = list(db.scalars(statement).all())

    for listing in listings:
        listing.events

    return listings


def get_listings_fixed(
    db: Session,
    skip: int = 0,
    limit: int = 50,
) -> list[RentalListing]:
    """Return listings while eagerly loading related events."""

    statement = (
        select(RentalListing)
        .options(
            selectinload(RentalListing.events)
        )
        .order_by(RentalListing.id)
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def get_listing(
    db: Session,
    listing_id: int,
) -> RentalListing:
    """Return one listing by ID with its related events."""

    statement = (
        select(RentalListing)
        .options(
            selectinload(RentalListing.events)
        )
        .where(RentalListing.id == listing_id)
    )

    listing = db.scalar(statement)

    if listing is None:
        raise HTTPException(
            status_code=404,
            detail="Rental listing not found",
        )

    return listing


def update_listing(
    db: Session,
    listing_id: int,
    payload: ListingUpdate,
) -> RentalListing:
    """Update the supplied rental-listing fields."""

    listing = get_listing(db, listing_id)

    data = payload.model_dump(
        exclude_unset=True,
        exclude_none=True,
    )

    if "propertyManagerId" in data:
        manager = db.get(
            PropertyManager,
            data["propertyManagerId"],
        )

        if manager is None:
            raise HTTPException(
                status_code=404,
                detail="Property manager not found",
            )

    if "submitterEmail" in data:
        data["submitterEmail"] = str(
            data["submitterEmail"]
        ).lower()

    for field_name, value in data.items():
        setattr(listing, field_name, value)

    try:
        db.commit()
        db.refresh(listing)
        return listing
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Listing code must be unique",
        ) from exc


def delete_listing(
    db: Session,
    listing_id: int,
) -> None:
    """Delete one rental listing by ID."""

    listing = get_listing(db, listing_id)

    db.delete(listing)
    db.commit()


def get_listings_by_property_manager(
    db: Session,
    manager_id: int,
    skip: int = 0,
    limit: int = 50,
) -> list[RentalListing]:
    """Return listings associated with one property manager."""

    get_property_manager(db, manager_id)

    statement = (
        select(RentalListing)
        .options(
            selectinload(RentalListing.events)
        )
        .where(
            RentalListing.propertyManagerId == manager_id
        )
        .order_by(RentalListing.id)
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())