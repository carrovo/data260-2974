import os
from dataclasses import dataclass, replace

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:

    def load_dotenv() -> bool:
        """Allow pure offline tests before dependencies are installed."""

        return False


load_dotenv()


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must be an integer; received {raw_value!r}"
        ) from exc

    if value < 1:
        raise RuntimeError(f"{name} must be positive")

    return value


@dataclass(frozen=True)
class HW6Settings:
    """Environment-backed settings for the HW6 memory system."""

    sid4: int = 2974
    port_base: int = 8274
    prefix: str = "s2974"
    seed: int = 2974
    verify_seed: int = 262974
    domain_id: int = 6
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "s2974_doc"
    ollama_model: str = "qwen3:8b"
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    short_term_n: int = 12
    summarize_every_user_messages: int = 4
    episodic_top_k: int = 3
    lifetime_every_session_summaries: int = 2

    @classmethod
    def from_env(cls) -> "HW6Settings":
        return cls(
            mongo_uri=os.getenv(
                "MONGODB_URI",
                "mongodb://localhost:27017",
            ),
            mongo_db=os.getenv(
                "MONGODB_DB",
                "s2974_doc",
            ),
            ollama_model=os.getenv(
                "OLLAMA_MODEL",
                "qwen3:8b",
            ),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL",
                "http://localhost:11434",
            ),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            ),
            short_term_n=_positive_int("SHORT_TERM_N", 12),
            summarize_every_user_messages=_positive_int(
                "SUMMARIZE_EVERY_USER_MSGS",
                4,
            ),
            episodic_top_k=_positive_int(
                "EPISODIC_TOP_K",
                3,
            ),
            lifetime_every_session_summaries=_positive_int(
                "LIFETIME_EVERY_SESSION_SUMMARIES",
                2,
            ),
        )

    def with_short_term_n(self, value: int) -> "HW6Settings":
        if value < 2 or value > 100:
            raise ValueError("short-term window must be between 2 and 100")

        return replace(self, short_term_n=value)


settings = HW6Settings.from_env()
