"""Deterministic demonstration of the HW9 Part 1 view counter."""

from redis import Redis
from sqlalchemy import select

from database import SessionLocal
from hw9_cache import DatabaseCache
from hw9_config import REDIS_URL, VIEW_SYNC_INTERVAL
from models import RentalListing

STUDENT_NAME = "Xuanhua Li"
TOTAL_ACCESSES = 25


def main() -> None:
    """Run 25 accesses and verify Redis and database counts."""

    redis_client = Redis.from_url(
        REDIS_URL,
        decode_responses=True,
    )
    redis_client.ping()

    db = SessionLocal()

    try:
        listing = db.scalars(
            select(RentalListing).order_by(RentalListing.id)
        ).first()

        if listing is None:
            raise RuntimeError(
                "No rental listing exists for the Part 1 demo."
            )

        cache = DatabaseCache(db, redis_client)
        cache_key = cache.listing_views_key(listing.id)

        # Reset only this demo counter for deterministic evidence.
        redis_client.delete(cache_key)
        listing.viewCount = 0
        db.commit()

        print(f"Student: {STUDENT_NAME}")
        print(f"Listing ID: {listing.id}")
        print(f"Redis key: {cache_key}")
        print("=== Testing Counter ===")

        for access_number in range(1, TOTAL_ACCESSES + 1):
            total = cache.increment_listing_views(listing.id)
            print(f"Access #{access_number}: Total = {total}")

            if total % VIEW_SYNC_INTERVAL == 0:
                print("✓ Synced views to database")

        db.refresh(listing)
        redis_count = int(redis_client.get(cache_key) or 0)
        database_count = int(listing.viewCount)

        print("=== Final Verification ===")
        print(f"Redis count: {redis_count}")
        print(f"Database count: {database_count}")

        if redis_count != TOTAL_ACCESSES:
            raise AssertionError("Redis count should be 25.")

        if database_count != 20:
            raise AssertionError(
                "Database count should contain the last completed batch."
            )

        print("PART1_STATUS: PASS")
    finally:
        db.close()
        redis_client.close()


if __name__ == "__main__":
    main()
