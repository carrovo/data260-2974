import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Load environment variables from the project-root .env file.
load_dotenv()

# The database URL contains the MySQL connection information.
# The actual password is stored only in .env and is not committed to Git.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Please create the project-root .env file."
    )

# Required HW4 database connection variable name.
# pool_pre_ping helps detect and refresh stale database connections.
db_session_basede26 = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)# connect MySQL

# Create one SQLAlchemy session factory for FastAPI requests.
SessionLocal = sessionmaker(
    bind=db_session_basede26,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass

# FastAPI dependency that opens one database session per request
# and closes it automatically after the request finishes.
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()