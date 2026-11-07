"""Demonstrate one complete database-backed semantic-cache false hit."""

import json
from pathlib import Path

from database import SessionLocal
from hw9_config import STUDENT_NAME
from hw9_semantic_cache import SemanticResponseCache
from models import RentalListing

CACHED_LISTING_ID = 4
INCOMING_LISTING_ID = 5
DEMO_THRESHOLD = 0.95


def rent_answer(listing: RentalListing) -> str:
    """Build a deterministic answer from the current relational record."""

    return (
        f"Rental listing {listing.id} ({listing.listingCode}) has a monthly "
        f"rent of ${listing.monthlyRent:,.2f}."
    )


def main() -> None:
    """Cache listing 4's rent and show its incorrect reuse for listing 5."""

    db = SessionLocal()
    try:
        cached_listing = db.get(RentalListing, CACHED_LISTING_ID)
        incoming_listing = db.get(RentalListing, INCOMING_LISTING_ID)
        if cached_listing is None or incoming_listing is None:
            raise RuntimeError("Listings 4 and 5 are required for the demo")

        cached_query = (
            f"What is the monthly rent for rental listing {cached_listing.id}?"
        )
        incoming_query = (
            f"What is the monthly rent for rental listing {incoming_listing.id}?"
        )
        cached_answer = rent_answer(cached_listing)
        correct_answer = rent_answer(incoming_listing)

        cache = SemanticResponseCache(threshold=DEMO_THRESHOLD)
        cache.clear_entries(reset_data_version=True)
        _cache_key, data_version = cache.store(cached_query, cached_answer)
        lookup = cache.find(incoming_query)

        if not lookup.is_hit:
            raise RuntimeError("The controlled case did not produce a false hit")
        if lookup.answer != cached_answer:
            raise RuntimeError("Redis returned an unexpected cached answer")
        if cached_answer == correct_answer:
            raise RuntimeError("The two records must have different rent answers")

        explanation = (
            "The two questions have nearly identical wording and intent; only "
            "the numeric entity identifier changes from 4 to 5. The embedding "
            "emphasizes the shared monthly-rent semantics and underweights the "
            "record ID, even though that ID changes the correct database answer."
        )
        result = {
            "student_name": STUDENT_NAME,
            "case_id": "similar_miss_02",
            "threshold": DEMO_THRESHOLD,
            "cached_query": cached_query,
            "incoming_query": incoming_query,
            "similarity": round(lookup.similarity, 6),
            "cached_answer_returned": lookup.answer,
            "correct_answer": correct_answer,
            "data_version": data_version,
            "embedding_confusion": explanation,
            "is_false_hit": True,
        }

        output_path = Path("reports/hw09/raw/part3_false_hit.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )

        print(f"Student: {STUDENT_NAME}")
        print("=== HW9 Part 3.3: Complete False Hit ===")
        print("Case: similar_miss_02")
        print(f"Threshold: {DEMO_THRESHOLD:.2f}")
        print(f"Cached query: {cached_query}")
        print(f"Incoming query: {incoming_query}")
        print(f"Similarity score: {lookup.similarity:.6f}")
        print(f"Cached answer returned: {lookup.answer}")
        print(f"Correct answer: {correct_answer}")
        print(f"Why the embedding was confused: {explanation}")
        print("FALSE_HIT_STATUS: PASS")
    finally:
        db.close()


if __name__ == "__main__":
    main()
