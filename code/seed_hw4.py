import argparse
import os
import random

from dotenv import load_dotenv
from sqlalchemy import func, select

from database import SessionLocal
from models import ListingEvent, RentalListing


load_dotenv()

# HW4 requires deterministic seed data.
SEED = int(os.getenv("SEED", "2974"))
TARGET_LISTINGS = 5_000
TARGET_EVENTS = 200

PROPERTY_TYPES = [
    "Apartment",
    "House",
    "Studio",
    "Shared Room",
]


def reset_listing_data(db) -> None:
    """Remove only listing-related data before reseeding."""
    # Delete child rows before parent rows because of the foreign key.
    db.query(ListingEvent).delete(synchronize_session=False)
    db.query(RentalListing).delete(synchronize_session=False)
    db.commit()


def create_listings(db) -> list[RentalListing]:
    """Create the required number of rental listings."""
    listings = []

    for index in range(1, TARGET_LISTINGS + 1):
        property_type = PROPERTY_TYPES[(index + SEED) % len(PROPERTY_TYPES)]

        listings.append(
            RentalListing(
                listingTitle=f"Seed Rental Listing {index:05d}",
                address=f"{100 + index} Market Street, San Jose, CA",
                submitterEmail=f"seed-owner-{index:05d}@example.com",
                description=(
                    f"Deterministic HW4 rental listing number {index} "
                    "created for database performance experiments."
                ),
                propertyType=property_type,
                termsAccepted=True,
            )
        )

    db.add_all(listings)
    db.flush()

    return listings


def create_events(db, listings: list[RentalListing]) -> None:
    """Create 200 related events using a deterministic random generator."""
    generator = random.Random(SEED)
    event_types = ["viewed", "updated", "contacted", "saved"]

    events = []

    for index in range(1, TARGET_EVENTS + 1):
        listing = generator.choice(listings)
        event_type = event_types[(index + SEED) % len(event_types)]

        events.append(
            ListingEvent(
                listing_id=listing.id,
                event_type=event_type,
                details=f"Seed event {index:03d} for HW4 experiment",
            )
        )

    db.add_all(events)


def get_count(db, model) -> int:
    """Return the number of rows in a table."""
    statement = select(func.count()).select_from(model)
    return int(db.execute(statement).scalar_one())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed HW4 rental listings and related events."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing listing data before reseeding.",
    )
    args = parser.parse_args()

    db = SessionLocal()

    try:
        current_count = get_count(db, RentalListing)

        if current_count > 0 and not args.reset:
            raise RuntimeError(
                "Listings already exist. Re-run with --reset "
                "to replace listing data."
            )

        if args.reset:
            reset_listing_data(db)

        listings = create_listings(db)
        create_events(db, listings)
        db.commit()

        listing_count = get_count(db, RentalListing)
        event_count = get_count(db, ListingEvent)

        print(f"Seed: {SEED}")
        print(f"Listings created: {listing_count}")
        print(f"Events created: {event_count}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()