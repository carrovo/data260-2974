from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    Query,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pymongo.errors import PyMongoError
from sqlalchemy.orm import Session

from crud import (
    create_listing,
    create_property_manager,
    delete_listing,
    delete_property_manager,
    get_listing,
    get_listings_by_property_manager,
    get_listings_fixed,
    get_listings_naive,
    get_property_manager,
    list_property_managers,
    update_listing,
    update_property_manager,
)
from database import (
    Base,
    db_session_basede26,
    get_db,
    get_sql_count,
    reset_sql_count,
)
from models import PropertyManager, RentalListing, User
from mongo_database import ensure_hw6_collections
from routers.auth import (
    get_current_user,
    require_moderator,
    require_writer,
)
from routers.auth import router as auth_router
from routers.hw6_listings import router as hw6_listings_router
from routers.hw6_memory import router as hw6_memory_router
from schemas import (
    ListingCreate,
    ListingOut,
    ListingUpdate,
    PropertyManagerCreate,
    PropertyManagerOut,
    PropertyManagerUpdate,
)

# Create tables that do not already exist.
# Existing tables are updated by the versioned migration scripts.
Base.metadata.create_all(bind=db_session_basede26)


app = FastAPI(
    title="Rental Housing Listings API",
    version="6.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(hw6_listings_router)
app.include_router(hw6_memory_router)


@app.on_event("startup")
def initialize_hw6_mongodb() -> None:
    """Apply MongoDB collection validators when MongoDB is available."""

    try:
        ensure_hw6_collections()
    except PyMongoError as exc:
        print(f"HW6 MongoDB startup warning: {type(exc).__name__}: {exc}")


@app.get("/health")
def health() -> dict[str, str]:
    """Public health check used by verification scripts."""

    return {
        "status": "ok",
    }


@app.get("/hw6-chat", response_class=HTMLResponse)
def hw6_chat_page() -> str:
    """Small optional chat UI used for HW6 screenshots."""

    path = Path(__file__).with_name("hw6_chat.html")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------
# Property-manager endpoints
# ---------------------------------------------------------


@app.post(
    "/api/property-managers",
    response_model=PropertyManagerOut,
    status_code=status.HTTP_201_CREATED,
)
def add_property_manager(
    payload: PropertyManagerCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_writer),
) -> PropertyManager:
    """Create one property manager."""

    return create_property_manager(
        db=db,
        payload=payload,
    )


@app.get(
    "/api/property-managers",
    response_model=list[PropertyManagerOut],
)
def read_property_managers(
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PropertyManager]:
    """Return property managers with pagination."""

    return list_property_managers(
        db=db,
        skip=skip,
        limit=limit,
    )


@app.get(
    "/api/property-managers/{manager_id}",
    response_model=PropertyManagerOut,
)
def read_property_manager(
    manager_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PropertyManager:
    """Return one property manager by ID."""

    return get_property_manager(
        db=db,
        manager_id=manager_id,
    )


@app.put(
    "/api/property-managers/{manager_id}",
    response_model=PropertyManagerOut,
)
def edit_property_manager(
    manager_id: int,
    payload: PropertyManagerUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_writer),
) -> PropertyManager:
    """Update one property manager."""

    return update_property_manager(
        db=db,
        manager_id=manager_id,
        payload=payload,
    )


@app.delete(
    "/api/property-managers/{manager_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_property_manager(
    manager_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_moderator),
) -> Response:
    """Delete a manager when no listings reference it."""

    delete_property_manager(
        db=db,
        manager_id=manager_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )


@app.get(
    "/api/property-managers/{manager_id}/listings",
    response_model=list[ListingOut],
)
def read_listings_for_property_manager(
    manager_id: int,
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RentalListing]:
    """Return listings associated with one property manager."""

    return get_listings_by_property_manager(
        db=db,
        manager_id=manager_id,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------
# Rental-listing endpoints
# ---------------------------------------------------------


@app.get(
    "/api/listings",
    response_model=list[ListingOut],
)
def list_listings(
    response: Response,
    skip: int = Query(
        default=0,
        ge=0,
    ),
    page_size: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RentalListing]:
    """Return listings using eager loading and pagination."""

    reset_sql_count(db)

    listings = get_listings_fixed(
        db=db,
        skip=skip,
        limit=page_size,
    )

    response.headers["X-SQL-Statements"] = str(get_sql_count(db))

    return listings


@app.get(
    "/api/listings/naive",
    response_model=list[ListingOut],
)
def list_listings_naive(
    response: Response,
    page_size: int = Query(
        default=10,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RentalListing]:
    """Retain the intentional HW4 N+1 endpoint."""

    reset_sql_count(db)

    listings = get_listings_naive(
        db=db,
        limit=page_size,
    )

    response.headers["X-SQL-Statements"] = str(get_sql_count(db))

    return listings


@app.get(
    "/api/listings/fixed",
    response_model=list[ListingOut],
)
def list_listings_fixed_endpoint(
    response: Response,
    page_size: int = Query(
        default=10,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RentalListing]:
    """Retain the optimized HW4 eager-loading endpoint."""

    reset_sql_count(db)

    listings = get_listings_fixed(
        db=db,
        limit=page_size,
    )

    response.headers["X-SQL-Statements"] = str(get_sql_count(db))

    return listings


@app.get(
    "/api/listings/{listing_id}",
    response_model=ListingOut,
)
def read_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RentalListing:
    """Return one rental listing by ID."""

    return get_listing(
        db=db,
        listing_id=listing_id,
    )


@app.post(
    "/api/listings",
    response_model=ListingOut,
    status_code=status.HTTP_201_CREATED,
)
def add_listing(
    payload: ListingCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_writer),
) -> RentalListing:
    """Create one rental listing."""

    return create_listing(
        db=db,
        payload=payload,
    )


@app.put(
    "/api/listings/{listing_id}",
    response_model=ListingOut,
)
def edit_listing(
    listing_id: int,
    payload: ListingUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_writer),
) -> RentalListing:
    """Update one rental listing."""

    return update_listing(
        db=db,
        listing_id=listing_id,
        payload=payload,
    )


@app.delete(
    "/api/listings/{listing_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_moderator),
) -> Response:
    """Delete one rental listing."""

    delete_listing(
        db=db,
        listing_id=listing_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
