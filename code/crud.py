from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models import RentalListing
from schemas import ListingCreate, ListingUpdate


def create_listing(
    db: Session,
    payload: ListingCreate,
) -> RentalListing:
    """Create and persist one rental listing."""

    listing = RentalListing(
        **payload.model_dump()
    )

    db.add(listing)
    db.commit()
    db.refresh(listing)

    return listing


def get_listings_naive(
    db: Session,
    skip: int = 0,
    limit: int = 50,
) -> list[RentalListing]:
    """
    Return listings using the intentional N+1 pattern.

    The main listing query runs first. Then accessing
    listing.events triggers one additional query per listing.
    """

    statement = (
        select(RentalListing)
        .order_by(RentalListing.id)
        .offset(skip)
        .limit(limit)
    )

    listings = list(db.scalars(statement).all())

    # Intentionally trigger one related-data query per listing.
    for listing in listings:
        listing.events

    return listings


def get_listings_fixed(
    db: Session,
    skip: int = 0,
    limit: int = 50,
) -> list[RentalListing]:
    """
    Return listings using eager loading.

    selectinload retrieves the related events in a batch
    instead of issuing one query for every listing.
    """

    statement = (
        select(RentalListing)
        .options(selectinload(RentalListing.events))
        .order_by(RentalListing.id)
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def get_listing(
    db: Session,
    listing_id: int,
) -> RentalListing | None:
    """Return one listing by ID with its related events."""

    statement = (
        select(RentalListing)
        .options(selectinload(RentalListing.events))
        .where(RentalListing.id == listing_id)
    )

    return db.scalar(statement)


def update_listing(
    db: Session,
    listing_id: int,
    payload: ListingUpdate,
) -> RentalListing | None:
    """Update the primary and secondary listing fields."""

    listing = db.get(RentalListing, listing_id)

    if listing is None:
        return None

    listing.listingTitle = payload.listingTitle.strip()
    listing.address = payload.address.strip()

    db.commit()
    db.refresh(listing)

    return listing


def delete_listing(
    db: Session,
    listing_id: int,
) -> RentalListing | None:
    """Delete one listing by ID."""

    listing = db.get(RentalListing, listing_id)

    if listing is None:
        return None

    db.delete(listing)
    db.commit()

    return listing