"""Pure validation and domain logic for HW8 Kafka listing messages."""

from collections.abc import Callable, MutableMapping
from typing import Any
from uuid import uuid4

from hw8_config import RESPONSE_TOPIC

CREATE_LISTING = "CREATE_LISTING"
GET_LISTING = "GET_LISTING"
ALLOWED_PROPERTY_TYPES = {
    "Apartment",
    "House",
    "Studio",
    "Shared Room",
}
REQUIRED_LISTING_FIELDS = (
    "listingTitle",
    "address",
    "description",
    "propertyType",
    "monthlyRent",
)


def error_response(correlation_id: object, error: str) -> dict[str, Any]:
    """Build a clean error response that preserves the request correlation ID."""

    return {
        "correlation_id": correlation_id,
        "success": False,
        "error": error,
    }


def validate_request_envelope(request: object) -> str | None:
    """Return an error message when a Kafka request envelope is invalid."""

    if not isinstance(request, dict):
        return "Request must be a JSON object"

    correlation_id = request.get("correlation_id")
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        return "correlation_id is required"

    reply_to = request.get("reply_to")
    if reply_to != RESPONSE_TOPIC:
        return f"reply_to must be {RESPONSE_TOPIC}"

    operation = request.get("operation")
    if not isinstance(operation, str) or not operation.strip():
        return "operation is required"

    if not isinstance(request.get("data"), dict):
        return "data must be a JSON object"

    return None


def validate_listing_data(
    data: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and normalize CREATE_LISTING data."""

    for field in REQUIRED_LISTING_FIELDS:
        if field not in data:
            return None, f"{field} is required"

    normalized: dict[str, Any] = {}
    for field in ("listingTitle", "address", "description", "propertyType"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, f"{field} must be a non-empty string"
        normalized[field] = value.strip()

    if len(normalized["description"]) < 26:
        return None, "description must contain at least 26 characters"

    if normalized["propertyType"] not in ALLOWED_PROPERTY_TYPES:
        allowed = ", ".join(sorted(ALLOWED_PROPERTY_TYPES))
        return None, f"propertyType must be one of: {allowed}"

    monthly_rent = data.get("monthlyRent")
    if (
        isinstance(monthly_rent, bool)
        or not isinstance(monthly_rent, (int, float))
        or monthly_rent <= 0
    ):
        return None, "monthlyRent must be a number greater than 0"
    normalized["monthlyRent"] = monthly_rent

    available_units = data.get("availableUnits", 1)
    if (
        isinstance(available_units, bool)
        or not isinstance(available_units, int)
        or available_units < 0
    ):
        return None, "availableUnits must be an integer greater than or equal to 0"
    normalized["availableUnits"] = available_units

    return normalized, None


def process_request(
    request: object,
    entities: MutableMapping[str, dict[str, Any]],
    id_factory: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Process one CREATE_LISTING or GET_LISTING request."""

    correlation_id = (
        request.get("correlation_id") if isinstance(request, dict) else None
    )
    envelope_error = validate_request_envelope(request)
    if envelope_error:
        return error_response(correlation_id, envelope_error)

    assert isinstance(request, dict)
    operation = request["operation"]
    data = request["data"]

    if operation == CREATE_LISTING:
        normalized, validation_error = validate_listing_data(data)
        if validation_error:
            return error_response(correlation_id, validation_error)

        create_id = id_factory or (lambda: str(uuid4()))
        entity_id = create_id()
        entity = {
            "entity_id": entity_id,
            **(normalized or {}),
        }
        entities[entity_id] = entity
        return {
            "correlation_id": correlation_id,
            "success": True,
            "entity_id": entity_id,
            "message": "Rental listing created",
        }

    if operation == GET_LISTING:
        entity_id = data.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            return error_response(correlation_id, "entity_id is required")

        entity = entities.get(entity_id)
        if entity is None:
            return error_response(correlation_id, "Rental listing not found")

        return {
            "correlation_id": correlation_id,
            "success": True,
            "entity": dict(entity),
        }

    return error_response(correlation_id, "Unknown operation")
