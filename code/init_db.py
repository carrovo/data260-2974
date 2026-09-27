from sqlalchemy import inspect

from database import Base, db_session_basede26

# Import models so SQLAlchemy registers all model classes
# in Base.metadata before creating the tables.
import models  # noqa: F401


def main() -> None:
    # Create all tables that do not already exist.
    # This does not delete or overwrite existing tables.
    Base.metadata.create_all(bind=db_session_basede26)

    # Confirm the tables visible in the target database.
    inspector = inspect(db_session_basede26)
    tables = sorted(inspector.get_table_names())

    print("Database tables:", tables)


if __name__ == "__main__":
    main()