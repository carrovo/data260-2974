"""Demonstrate stale semantic data and data-version invalidation."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from database import SessionLocal
from hw9_config import STUDENT_NAME
from hw9_semantic_cache import SemanticResponseCache
from models import RentalListing

LISTING_ID = 4
SHIPPED_THRESHOLD = 0.90
RENT_CHANGE = Decimal("25.00")


def rent_answer(listing: RentalListing) -> str:
    """Build an answer directly from the current relational record."""

    return (
        f"Rental listing {listing.id} ({listing.listingCode}) has a monthly "
        f"rent of ${listing.monthlyRent:,.2f}."
    )


def main() -> None:
    """Show a stale hit, invalidate it, return fresh data, then restore MySQL."""

    cache = SemanticResponseCache(threshold=SHIPPED_THRESHOLD)
    cache.clear_entries(reset_data_version=True)
    db = SessionLocal()
    database_modified = False
    original_rent: Decimal | None = None
    result: dict[str, Any]

    try:
        listing = db.get(RentalListing, LISTING_ID)
        if listing is None:
            raise RuntimeError(f"Rental listing {LISTING_ID} was not found")

        original_rent = Decimal(listing.monthlyRent)
        query = f"What is the monthly rent for rental listing {LISTING_ID}?"
        original_answer = rent_answer(listing)
        _cache_key, cached_version = cache.store(query, original_answer)

        listing.monthlyRent = original_rent + RENT_CHANGE
        db.commit()
        database_modified = True
        db.refresh(listing)
        updated_rent = Decimal(listing.monthlyRent)
        current_answer = rent_answer(listing)

        stale_lookup = cache.find(query, enforce_data_version=False)
        if not stale_lookup.is_hit or stale_lookup.answer != original_answer:
            raise RuntimeError("The controlled stale hit was not reproduced")
        if stale_lookup.answer == current_answer:
            raise RuntimeError("The database update did not make the cache stale")

        invalidation_version = cache.bump_data_version()
        invalidated_lookup = cache.find(query, enforce_data_version=True)
        if invalidated_lookup.is_hit:
            raise RuntimeError("The stale cache entry was not invalidated")

        _new_key, refreshed_version = cache.store(query, current_answer)
        refreshed_lookup = cache.find(query, enforce_data_version=True)
        if not refreshed_lookup.is_hit:
            raise RuntimeError("The refreshed answer was not cached")
        if refreshed_lookup.answer != current_answer:
            raise RuntimeError("The refreshed cache answer is incorrect")

        strategy = (
            "After a relevant relational write, increment the Redis data-version "
            "key. Each cache entry stores the version from creation time. A "
            "version-aware lookup deletes and rejects an entry when its stored "
            "version differs from the current version."
        )
        tradeoff = (
            "This coarse global version is simple and prevents stale answers, "
            "but any relevant listing update invalidates older semantic entries, "
            "reducing hit rate and causing extra agent recomputation."
        )
        result = {
            "student_name": STUDENT_NAME,
            "listing_id": LISTING_ID,
            "query": query,
            "threshold": SHIPPED_THRESHOLD,
            "original_rent": f"{original_rent:.2f}",
            "updated_rent": f"{updated_rent:.2f}",
            "cached_version": cached_version,
            "stale_hit": True,
            "stale_answer_returned": stale_lookup.answer,
            "correct_answer_after_update": current_answer,
            "invalidation_version": invalidation_version,
            "stale_entry_rejected": not invalidated_lookup.is_hit,
            "refreshed_version": refreshed_version,
            "fresh_answer_returned": refreshed_lookup.answer,
            "strategy": strategy,
            "tradeoff": tradeoff,
        }
    finally:
        restored_version: str | None = None
        restored_rent: Decimal | None = None
        if database_modified and original_rent is not None:
            db.rollback()
            listing = db.get(RentalListing, LISTING_ID)
            if listing is None:
                raise RuntimeError("Listing disappeared before database restore")
            listing.monthlyRent = original_rent
            db.commit()
            db.refresh(listing)
            restored_rent = Decimal(listing.monthlyRent)
            restored_version = cache.bump_data_version()
        cache.clear_entries()
        db.close()

    result["database_restored"] = (
        original_rent is not None and restored_rent == original_rent
    )
    result["restored_rent"] = (
        f"{restored_rent:.2f}" if restored_rent is not None else None
    )
    result["restored_data_version"] = restored_version
    if not result["database_restored"]:
        raise RuntimeError("The original database rent was not restored")

    output_path = Path("reports/hw09/raw/part3_stale_invalidation.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )

    print(f"Student: {STUDENT_NAME}")
    print("=== HW9 Part 3.5: Stale Answer and Invalidation ===")
    print(f"Query: {result['query']}")
    print(f"Cached data version: {result['cached_version']}")
    print(f"Original database rent: ${result['original_rent']}")
    print(f"Updated database rent: ${result['updated_rent']}")
    print(f"Stale cache hit: {result['stale_hit']}")
    print(f"Stale answer returned: {result['stale_answer_returned']}")
    print(f"Correct answer after update: {result['correct_answer_after_update']}")
    print(f"Data version after update: {result['invalidation_version']}")
    print(f"Stale entry rejected: {result['stale_entry_rejected']}")
    print(f"Fresh answer returned: {result['fresh_answer_returned']}")
    print(f"Strategy: {result['strategy']}")
    print(f"Trade-off: {result['tradeoff']}")
    print(f"Database restored: {result['database_restored']}")
    print(f"Restored rent: ${result['restored_rent']}")
    print(f"Restored data version: {result['restored_data_version']}")
    print("STALE_INVALIDATION_STATUS: PASS")


if __name__ == "__main__":
    main()
