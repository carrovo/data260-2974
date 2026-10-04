import os

from dotenv import load_dotenv
from sqlalchemy import inspect, text

from database import db_session_basede26
from models import PropertyManager


load_dotenv()

SID4 = int(os.getenv("SID4", "2974"))


def main() -> None:
    """Upgrade the existing HW4 MySQL schema for HW5."""

    engine = db_session_basede26
    inspector = inspect(engine)

    if "listings" not in inspector.get_table_names():
        raise RuntimeError(
            "The existing HW4 listings table was not found. "
            "Run the HW4 database setup first."
        )

    # Create only the new HW5 related-entity table.
    PropertyManager.__table__.create(
        bind=engine,
        checkfirst=True,
    )

    default_email = f"manager{SID4}@example.com"

    # Create one manager for the existing HW4 listings.
    with engine.begin() as connection:
        manager_id = connection.execute(
            text(
                "SELECT id FROM property_managers "
                "ORDER BY id LIMIT 1"
            )
        ).scalar_one_or_none()

        if manager_id is None:
            result = connection.execute(
                text(
                    "INSERT INTO property_managers "
                    "(`firstName`, `lastName`, email) "
                    "VALUES (:first_name, :last_name, :email)"
                ),
                {
                    "first_name": "Default",
                    "last_name": "Manager",
                    "email": default_email,
                },
            )
            manager_id = int(result.lastrowid)

    existing_columns = {
        column["name"]
        for column in inspect(engine).get_columns("listings")
    }

    column_definitions = {
        "listingCode": "VARCHAR(30) NULL",
        "monthlyRent": "DECIMAL(10, 2) NULL",
        "availableUnits": "INT NOT NULL DEFAULT 1",
        "propertyManagerId": "INT NULL",
        "updated_at": (
            "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ),
    }

    # Add only columns that do not already exist.
    with engine.begin() as connection:
        for column_name, definition in column_definitions.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        "ALTER TABLE listings "
                        f"ADD COLUMN `{column_name}` {definition}"
                    )
                )

        # Give every existing listing a deterministic unique code.
        connection.execute(
            text(
                "UPDATE listings "
                "SET `listingCode` = CONCAT("
                ":code_prefix, LPAD(id, 6, '0')"
                ") "
                "WHERE `listingCode` IS NULL "
                "OR `listingCode` = ''"
            ),
            {"code_prefix": f"S{SID4}-"},
        )

        # Give existing listings deterministic rent values.
        connection.execute(
            text(
                "UPDATE listings "
                "SET `monthlyRent` = "
                "1500.00 + (MOD(id, 20) * 50.00) "
                "WHERE `monthlyRent` IS NULL"
            )
        )

        # Connect existing listings to the default manager.
        connection.execute(
            text(
                "UPDATE listings "
                "SET `propertyManagerId` = :manager_id "
                "WHERE `propertyManagerId` IS NULL"
            ),
            {"manager_id": manager_id},
        )

        # Make populated fields required.
        connection.execute(
            text(
                "ALTER TABLE listings "
                "MODIFY COLUMN `listingCode` VARCHAR(30) NOT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE listings "
                "MODIFY COLUMN `monthlyRent` "
                "DECIMAL(10, 2) NOT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE listings "
                "MODIFY COLUMN `propertyManagerId` INT NOT NULL"
            )
        )

    # Add indexes and foreign key only when they are absent.
    with engine.begin() as connection:
        unique_code_index_count = connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'listings' "
                "AND column_name = 'listingCode' "
                "AND non_unique = 0"
            )
        ).scalar_one()

        if unique_code_index_count == 0:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX "
                    "uq_listings_listingCode "
                    "ON listings (`listingCode`)"
                )
            )

        manager_index_count = connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'listings' "
                "AND column_name = 'propertyManagerId'"
            )
        ).scalar_one()

        if manager_index_count == 0:
            connection.execute(
                text(
                    "CREATE INDEX ix_listings_propertyManagerId "
                    "ON listings (`propertyManagerId`)"
                )
            )

        manager_fk_count = connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM information_schema.key_column_usage "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'listings' "
                "AND column_name = 'propertyManagerId' "
                "AND referenced_table_name = 'property_managers'"
            )
        ).scalar_one()

        if manager_fk_count == 0:
            connection.execute(
                text(
                    "ALTER TABLE listings "
                    "ADD CONSTRAINT fk_listings_property_manager "
                    "FOREIGN KEY (`propertyManagerId`) "
                    "REFERENCES property_managers(id) "
                    "ON DELETE RESTRICT"
                )
            )

        listing_count = connection.execute(
            text("SELECT COUNT(*) FROM listings")
        ).scalar_one()

    # Verify the required columns after migration.
    final_columns = {
        column["name"]
        for column in inspect(engine).get_columns("listings")
    }

    required_columns = set(column_definitions)
    missing_columns = required_columns - final_columns

    if missing_columns:
        raise RuntimeError(
            "Migration verification failed. Missing columns: "
            f"{sorted(missing_columns)}"
        )

    print("HW5 migration complete")
    print(f"Default property manager ID: {manager_id}")
    print(f"Rental listings preserved: {listing_count}")
    print("Added/verified listing columns:")

    for column_name in sorted(required_columns):
        print(f"- {column_name}")


if __name__ == "__main__":
    main()