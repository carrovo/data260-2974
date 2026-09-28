import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)


# Load environment variables from the project-root .env file.
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. "
        "Please create the project-root .env file."
    )


# Required HW4 database connection variable name.
db_session_basede26 = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# Create one SQLAlchemy session factory.
SessionLocal = sessionmaker(
    bind=db_session_basede26,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


@event.listens_for(Session, "do_orm_execute")
def count_sql_statements(
    execute_state,
) -> None:
    """Count ORM statements for the current request."""
    db = execute_state.session

    if not db.info.get(
        "count_sql_statements",
        False,
    ):
        return

    current_count = db.info.get(
        "sql_statement_count",
        0,
    )

    db.info["sql_statement_count"] = (
        current_count + 1
    )


def reset_sql_count(db: Session) -> None:
    """Reset the counter before the measured query."""
    db.info["sql_statement_count"] = 0


def get_sql_count(db: Session) -> int:
    """Return the measured SQL statement count."""
    return int(
        db.info.get(
            "sql_statement_count",
            0,
        )
    )


def get_db() -> Generator[Session, None, None]:
    """Open one database session per request."""
    db = SessionLocal()

    db.info["count_sql_statements"] = True
    db.info["sql_statement_count"] = 0

    try:
        yield db
    finally:
        db.close()