"""Redis-backed cache operations for DATA 260 Homework 9."""

import logging

from redis import Redis
from sqlalchemy.orm import Session

from hw9_config import PREFIX, REDIS_URL, VIEW_SYNC_INTERVAL
from models import RentalListing

logger = logging.getLogger(__name__)


class DatabaseCache:
    """Coordinate Redis counters with the relational database."""

    def __init__(
        self,
        db: Session,
        redis_client: Redis | None = None,
    ) -> None:
        self.db = db
        self.redis_client = redis_client or Redis.from_url(
            REDIS_URL,
            decode_responses=True,
        )

    @staticmethod
    def listing_views_key(listing_id: int) -> str:
        """Return the required PREFIX-scoped Redis key."""

        return f"{PREFIX}:views:listing:{listing_id}"

    def increment_listing_views(self, listing_id: int) -> int:
        """Increment a Redis view count and sync every tenth view."""

        listing = self.db.get(RentalListing, listing_id)

        if listing is None:
            raise LookupError(
                f"Rental listing {listing_id} was not found."
            )

        key = self.listing_views_key(listing_id)

        # Initialize a missing Redis counter from the persisted value. NX
        # prevents this initialization from overwriting an active counter.
        self.redis_client.set(
            key,
            int(listing.viewCount),
            nx=True,
        )

        current_count = int(self.redis_client.incr(key))

        if current_count % VIEW_SYNC_INTERVAL == 0:
            listing.viewCount = current_count
            self.db.commit()
            self.db.refresh(listing)
            logger.info(
                "Synced views to database: listing_id=%s count=%s",
                listing_id,
                current_count,
            )

        return current_count
