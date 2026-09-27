from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from crud import (
    create_listing,
    delete_listing,
    get_listing,
    get_listings_fixed,
    get_listings_naive,
    update_listing,
)
from database import Base, db_session_basede26, get_db
from models import RentalListing
from routers.auth import require_session, router as auth_router
from schemas import ListingCreate, ListingOut, ListingUpdate


# Create missing tables when the application starts.
# The explicit code/init_db.py script remains the reproducible
# schema initialization script for the assignment.
Base.metadata.create_all(bind=db_session_basede26)


app = FastAPI(
    title="Rental Housing Listings API",
    version="4.0.0",
)


# Allow the React development server to send cookie-based requests.
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


# Register authentication routes such as login, logout, and me.
app.include_router(auth_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Public health check used by verification scripts."""

    return {
        "status": "ok",
    }


@app.get(
    "/api/listings",
    response_model=list[ListingOut],
)
def list_listings(
    page_size: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
) -> list[RentalListing]:
    """
    Return listings for authenticated users.

    The normal list endpoint uses the fixed eager-loading version.
    """

    return get_listings_fixed(
        db=db,
        limit=page_size,
    )


@app.get(
    "/api/listings/naive",
    response_model=list[ListingOut],
)
def list_listings_naive(
    page_size: int = Query(
        default=10,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
) -> list[RentalListing]:
    """
    Intentionally demonstrate the N+1 query pattern.

    This endpoint is required for the Part 3 comparison.
    """

    return get_listings_naive(
        db=db,
        limit=page_size,
    )


@app.get(
    "/api/listings/fixed",
    response_model=list[ListingOut],
)
def list_listings_fixed(
    page_size: int = Query(
        default=10,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
) -> list[RentalListing]:
    """
    Return listings with eager-loaded related events.

    This endpoint is the optimized comparison version.
    """

    return get_listings_fixed(
        db=db,
        limit=page_size,
    )


@app.get(
    "/api/listings/{listing_id}",
    response_model=ListingOut,
)
def read_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
) -> RentalListing:
    """Return one listing by ID for an authenticated user."""

    listing = get_listing(
        db=db,
        listing_id=listing_id,
    )

    if listing is None:
        raise HTTPException(
            status_code=404,
            detail="Rental listing not found",
        )

    return listing


@app.post(
    "/api/listings",
    response_model=ListingOut,
    status_code=201,
)
def add_listing(
    payload: ListingCreate,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
) -> RentalListing:
    """Create one listing for an authenticated user."""

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
    _session=Depends(require_session),
) -> RentalListing:
    """Update the primary and secondary listing fields."""

    listing = update_listing(
        db=db,
        listing_id=listing_id,
        payload=payload,
    )

    if listing is None:
        raise HTTPException(
            status_code=404,
            detail="Rental listing not found",
        )

    return listing


@app.delete(
    "/api/listings/{listing_id}",
)
def remove_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
) -> dict[str, str]:
    """Delete one listing by ID."""

    listing = delete_listing(
        db=db,
        listing_id=listing_id,
    )

    if listing is None:
        raise HTTPException(
            status_code=404,
            detail="Rental listing not found",
        )

    return {
        "message": "Rental listing deleted successfully",
    }