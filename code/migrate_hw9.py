"""Add the HW9 persisted view counter to the existing listings table."""

from sqlalchemy import inspect, text

from database import db_session_basede26

COLUMN_NAME = "viewCount"


def main() -> None:
    """Apply and verify the idempotent HW9 schema migration."""

    engine = db_session_basede26
    inspector = inspect(engine)

    if "listings" not in inspector.get_table_names():
        raise RuntimeError(
            "The listings table was not found. Run the earlier homework "
            "database setup before the HW9 migration."
        )

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("listings")
    }

    with engine.begin() as connection:
        if COLUMN_NAME not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE listings "
                    "ADD COLUMN `viewCount` INT NOT NULL DEFAULT 0"
                )
            )

    final_columns = {
        column["name"]: column
        for column in inspect(engine).get_columns("listings")
    }

    if COLUMN_NAME not in final_columns:
        raise RuntimeError(
            "HW9 migration verification failed: viewCount is missing."
        )

    with engine.connect() as connection:
        listing_count = int(
            connection.execute(
                text("SELECT COUNT(*) FROM listings")
            ).scalar_one()
        )

    print("HW9 migration complete")
    print("Added/verified column: listings.viewCount")
    print(f"Rental listings preserved: {listing_count}")


if __name__ == "__main__":
    main()
