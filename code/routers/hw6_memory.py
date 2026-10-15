from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from file_memory import FileMemoryManager
from hw6_config import settings
from hw6_memory import (
    LocalEmbeddingProvider,
    MemoryService,
    MongoMemoryRepository,
    serialize_document,
)
from hw6_schemas import ChatRequest, ChatResponse
from mongo_database import mongo_db_dependency
from pymongo.database import Database
from pymongo.errors import PyMongoError

from src.model_client import ModelClient

router = APIRouter(tags=["HW6 Memory"])
PROJECT_ROOT = Path(__file__).resolve().parents[2]

_model = ModelClient(
    model_name=settings.ollama_model,
    temperature=0.0,
    reasoning=False,
    base_url=settings.ollama_base_url,
    seed=settings.seed,
)
_embedder = LocalEmbeddingProvider(settings.embedding_model)
_file_memory = FileMemoryManager(PROJECT_ROOT)


def _service(db: Database) -> MemoryService:
    return MemoryService(
        repository=MongoMemoryRepository(db),
        model=_model,
        embedder=_embedder,
        settings=settings,
        file_memory=_file_memory,
    )


@router.post(
    "/api/chat",
    response_model=ChatResponse,
)
def chat(
    payload: ChatRequest,
    db: Database = Depends(mongo_db_dependency),
) -> dict:
    try:
        return _service(db).chat(
            user_id=payload.user_id,
            session_id=payload.session_id,
            message=payload.message,
            memory_mode=payload.memory_mode,
            policy=payload.policy,
            short_term_n=payload.short_term_n,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except PyMongoError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is unavailable for the chat request.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"The local memory/model pipeline failed: {type(exc).__name__}: {exc}"
            ),
        ) from exc


@router.get("/api/memory/{user_id}")
def get_memory(
    user_id: str,
    session_id: str | None = Query(default=None),
    db: Database = Depends(mongo_db_dependency),
) -> dict:
    message_query: dict = {"user_id": user_id}
    summary_query: dict = {
        "user_id": user_id,
        "scope": "session",
    }

    if session_id:
        message_query["session_id"] = session_id
        summary_query["session_id"] = session_id

    try:
        messages = list(
            db.messages.find(message_query).sort("created_at", -1).limit(16)
        )
        messages.reverse()
        session_summary = db.summaries.find_one(
            summary_query,
            sort=[("created_at", -1)],
        )
        lifetime_summary = db.summaries.find_one(
            {
                "user_id": user_id,
                "scope": "user",
                "session_id": None,
            },
            sort=[("created_at", -1)],
        )
        episodes = list(
            db.episodes.find({"user_id": user_id}).sort("created_at", -1).limit(20)
        )
    except PyMongoError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is unavailable for memory retrieval.",
        ) from exc

    episode_payload = []

    for episode in episodes:
        item = serialize_document(episode)
        embedding = item.pop("embedding", [])
        item["embedding_dimensions"] = len(embedding)
        episode_payload.append(item)

    return {
        "user_id": user_id,
        "session_id": session_id,
        "messages": [serialize_document(message) for message in messages],
        "latest_session_summary": (
            serialize_document(session_summary) if session_summary else None
        ),
        "latest_lifetime_summary": (
            serialize_document(lifetime_summary) if lifetime_summary else None
        ),
        "episodes": episode_payload,
        "file_memory_status": _file_memory.consolidation_status(),
    }


@router.get("/api/aggregate/{user_id}")
def get_aggregate(
    user_id: str,
    db: Database = Depends(mongo_db_dependency),
) -> dict:
    repository = MongoMemoryRepository(db)

    try:
        daily_counts = repository.daily_message_counts(user_id)
        summaries = repository.recent_summaries(user_id, limit=6)
    except PyMongoError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is unavailable for aggregation.",
        ) from exc

    return {
        "user_id": user_id,
        "daily_message_counts": [
            {
                "date": row["_id"],
                "message_count": row["message_count"],
            }
            for row in daily_counts
        ],
        "recent_summaries": [serialize_document(summary) for summary in summaries],
    }
