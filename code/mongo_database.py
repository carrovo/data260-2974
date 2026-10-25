from collections.abc import Iterator
from threading import Lock

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import CollectionInvalid

from hw6_config import settings

_client: MongoClient | None = None
_client_lock = Lock()


LISTING_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "listingTitle",
            "status",
            "propertyType",
            "availableFrom",
            "createdAt",
            "updatedAt",
        ],
        "properties": {
            "listingTitle": {
                "bsonType": "string",
                "minLength": 1,
                "maxLength": 100,
            },
            "description": {
                "bsonType": ["string", "null"],
                "maxLength": 2000,
            },
            "status": {
                "enum": ["active", "pending", "rented"],
            },
            "propertyType": {
                "enum": [
                    "Apartment",
                    "House",
                    "Studio",
                    "Shared Room",
                ],
            },
            "availableFrom": {"bsonType": "date"},
            "createdAt": {"bsonType": "date"},
            "updatedAt": {"bsonType": "date"},
        },
    }
}

MESSAGE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "user_id",
            "session_id",
            "role",
            "content",
            "created_at",
        ],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": "string"},
            "role": {"enum": ["user", "assistant"]},
            "content": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    }
}

SUMMARY_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "user_id",
            "session_id",
            "scope",
            "text",
            "created_at",
        ],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": ["string", "null"]},
            "scope": {"enum": ["session", "user"]},
            "text": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    }
}

EPISODE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "user_id",
            "session_id",
            "fact",
            "importance",
            "embedding",
            "created_at",
        ],
        "properties": {
            "user_id": {"bsonType": "string"},
            "session_id": {"bsonType": "string"},
            "fact": {
                "bsonType": "string",
                "minLength": 1,
                "maxLength": 240,
            },
            "importance": {
                "bsonType": "double",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "embedding": {
                "bsonType": "array",
                "items": {"bsonType": "double"},
            },
            "created_at": {"bsonType": "date"},
        },
    }
}


def get_mongo_client() -> MongoClient:
    """Return a shared, timezone-aware PyMongo client."""

    global _client

    if _client is None:
        with _client_lock:
            if _client is None:
                _client = MongoClient(
                    settings.mongo_uri,
                    tz_aware=True,
                    serverSelectionTimeoutMS=3000,
                )

    return _client


def get_mongo_db() -> Database:
    return get_mongo_client()[settings.mongo_db]


def _create_or_update_collection(
    db: Database,
    name: str,
    validator: dict | None = None,
) -> None:
    options = {}

    if validator is not None:
        options = {
            "validator": validator,
            "validationLevel": "strict",
            "validationAction": "error",
        }

    try:
        db.create_collection(name, **options)
    except CollectionInvalid:
        if validator is not None:
            db.command(
                "collMod",
                name,
                **options,
            )


def ensure_hw6_collections() -> None:
    """Create HW6 collections, validation, and useful indexes."""

    db = get_mongo_db()
    db.command("ping")

    _create_or_update_collection(
        db,
        "listings",
        LISTING_VALIDATOR,
    )

    _create_or_update_collection(
        db,
        "messages",
        MESSAGE_VALIDATOR,
    )
    _create_or_update_collection(
        db,
        "summaries",
        SUMMARY_VALIDATOR,
    )
    _create_or_update_collection(
        db,
        "episodes",
        EPISODE_VALIDATOR,
    )
    _create_or_update_collection(db, "chat_metrics")

    db.listings.create_index(
        [("createdAt", DESCENDING)],
        name="idx_listings_created_at",
    )
    db.messages.create_index(
        [
            ("user_id", ASCENDING),
            ("session_id", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="idx_messages_user_session_time",
    )
    db.summaries.create_index(
        [
            ("user_id", ASCENDING),
            ("scope", ASCENDING),
            ("session_id", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="idx_summaries_lookup",
    )
    db.episodes.create_index(
        [
            ("user_id", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="idx_episodes_user_time",
    )
    db.chat_metrics.create_index(
        [
            ("user_id", ASCENDING),
            ("session_id", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="idx_chat_metrics_lookup",
    )


def mongo_db_dependency() -> Iterator[Database]:
    """FastAPI dependency for the shared MongoDB database."""

    yield get_mongo_db()
