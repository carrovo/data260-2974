import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import db_session_basede26


logger = logging.getLogger("s2974_rel.domain_tools")

Envelope = dict[str, Any]


def success_response(data: Any) -> Envelope:
    """Create the shared successful response envelope."""

    return {
        "ok": True,
        "data": data,
        "error": None,
    }


def error_response(message: str) -> Envelope:
    """Create the shared failed response envelope."""

    return {
        "ok": False,
        "data": None,
        "error": message,
    }


def _valid_positive_integer(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    )


def _money(value: Any) -> str | None:
    if value is None:
        return None

    return f"{Decimal(value):.2f}"


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    return str(value)


def search_listings(
    query: str,
    limit: int = 5,
) -> Envelope:
    """Search rental listings by code, title, address, or type."""

    if not isinstance(query, str) or not query.strip():
        return error_response(
            "query must be a non-empty string"
        )

    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 25
    ):
        return error_response(
            "limit must be an integer between 1 and 25"
        )

    statement = text(
        """
        SELECT
            id,
            listingCode,
            listingTitle,
            address,
            propertyType,
            monthlyRent,
            availableUnits,
            propertyManagerId
        FROM listings
        WHERE listingCode LIKE :pattern
           OR listingTitle LIKE :pattern
           OR address LIKE :pattern
           OR propertyType LIKE :pattern
        ORDER BY id
        LIMIT :limit
        """
    )

    try:
        with db_session_basede26.connect() as connection:
            rows = connection.execute(
                statement,
                {
                    "pattern": f"%{query.strip()}%",
                    "limit": limit,
                },
            ).mappings().all()
    except SQLAlchemyError:
        logger.exception("Listing search failed")
        return error_response(
            "database operation failed"
        )

    data = [
        {
            "id": row["id"],
            "listingCode": row["listingCode"],
            "listingTitle": row["listingTitle"],
            "address": row["address"],
            "propertyType": row["propertyType"],
            "monthlyRent": _money(row["monthlyRent"]),
            "availableUnits": row["availableUnits"],
            "propertyManagerId": row["propertyManagerId"],
        }
        for row in rows
    ]

    return success_response(data)


def listing_details(listing_id: int) -> Envelope:
    """Return one listing and its related property manager."""

    if not _valid_positive_integer(listing_id):
        return error_response(
            "listing_id must be a positive integer"
        )

    statement = text(
        """
        SELECT
            l.id,
            l.listingCode,
            l.listingTitle,
            l.address,
            l.submitterEmail,
            l.description,
            l.propertyType,
            l.monthlyRent,
            l.availableUnits,
            l.termsAccepted,
            l.propertyManagerId,
            l.created_at,
            l.updated_at,
            pm.firstName AS managerFirstName,
            pm.lastName AS managerLastName,
            pm.email AS managerEmail
        FROM listings AS l
        JOIN property_managers AS pm
            ON pm.id = l.propertyManagerId
        WHERE l.id = :listing_id
        """
    )

    try:
        with db_session_basede26.connect() as connection:
            row = connection.execute(
                statement,
                {"listing_id": listing_id},
            ).mappings().first()
    except SQLAlchemyError:
        logger.exception("Listing detail lookup failed")
        return error_response(
            "database operation failed"
        )

    if row is None:
        return error_response(
            f"listing {listing_id} was not found"
        )

    data = {
        "id": row["id"],
        "listingCode": row["listingCode"],
        "listingTitle": row["listingTitle"],
        "address": row["address"],
        "submitterEmail": row["submitterEmail"],
        "description": row["description"],
        "propertyType": row["propertyType"],
        "monthlyRent": _money(row["monthlyRent"]),
        "availableUnits": row["availableUnits"],
        "termsAccepted": bool(row["termsAccepted"]),
        "propertyManagerId": row["propertyManagerId"],
        "created_at": _timestamp(row["created_at"]),
        "updated_at": _timestamp(row["updated_at"]),
        "propertyManager": {
            "id": row["propertyManagerId"],
            "firstName": row["managerFirstName"],
            "lastName": row["managerLastName"],
            "email": row["managerEmail"],
        },
    }

    return success_response(data)


def manager_rent_summary(
    property_manager_id: int,
) -> Envelope:
    """Aggregate listing and rent statistics for one manager."""

    if not _valid_positive_integer(property_manager_id):
        return error_response(
            "property_manager_id must be a positive integer"
        )

    statement = text(
        """
        SELECT
            pm.id AS managerId,
            pm.firstName,
            pm.lastName,
            pm.email,
            COUNT(l.id) AS listingCount,
            COALESCE(SUM(l.availableUnits), 0) AS totalAvailableUnits,
            AVG(l.monthlyRent) AS averageRent,
            MIN(l.monthlyRent) AS minimumRent,
            MAX(l.monthlyRent) AS maximumRent
        FROM property_managers AS pm
        LEFT JOIN listings AS l
            ON l.propertyManagerId = pm.id
        WHERE pm.id = :property_manager_id
        GROUP BY
            pm.id,
            pm.firstName,
            pm.lastName,
            pm.email
        """
    )

    try:
        with db_session_basede26.connect() as connection:
            row = connection.execute(
                statement,
                {
                    "property_manager_id":
                        property_manager_id,
                },
            ).mappings().first()
    except SQLAlchemyError:
        logger.exception("Manager aggregate lookup failed")
        return error_response(
            "database operation failed"
        )

    if row is None:
        return error_response(
            f"property manager {property_manager_id} "
            "was not found"
        )

    data = {
        "propertyManager": {
            "id": row["managerId"],
            "firstName": row["firstName"],
            "lastName": row["lastName"],
            "email": row["email"],
        },
        "listingCount": int(row["listingCount"]),
        "totalAvailableUnits": int(
            row["totalAvailableUnits"]
        ),
        "averageRent": _money(row["averageRent"]),
        "minimumRent": _money(row["minimumRent"]),
        "maximumRent": _money(row["maximumRent"]),
    }

    return success_response(data)