import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from domain_tools import error_response
from reliable_domain_tools import (
    listing_details,
    manager_rent_summary,
    search_listings,
)

logger = logging.getLogger("s2974_rel.tool_executor")

Envelope = dict[str, Any]
ToolHandler = Callable[..., Envelope]


class ToolArguments(BaseModel):
    """Strict base model for locally validated tool arguments."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class SearchListingsArguments(ToolArguments):
    query: str = Field(
        min_length=1,
        description=(
            "Listing code, title, address, or property-type term."
        ),
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=25,
        description="Maximum number of listings to return.",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")

        return value.strip()


class ListingDetailsArguments(ToolArguments):
    listing_id: int = Field(
        gt=0,
        description="Positive rental-listing ID.",
    )


class ManagerRentSummaryArguments(ToolArguments):
    property_manager_id: int = Field(
        gt=0,
        description="Positive property-manager ID.",
    )


@dataclass(frozen=True)
class ToolContract:
    description: str
    arguments_model: type[ToolArguments]


TOOL_CONTRACTS: dict[str, ToolContract] = {
    "search_listings": ToolContract(
        description=(
            "Search rental listings by code, title, address, "
            "or property type."
        ),
        arguments_model=SearchListingsArguments,
    ),
    "listing_details": ToolContract(
        description=(
            "Return one rental listing and its property manager."
        ),
        arguments_model=ListingDetailsArguments,
    ),
    "manager_rent_summary": ToolContract(
        description=(
            "Return listing-count and rent statistics for one "
            "property manager."
        ),
        arguments_model=ManagerRentSummaryArguments,
    ),
}


def _tool_schema(
    name: str,
    contract: ToolContract,
) -> dict[str, Any]:
    parameters = contract.arguments_model.model_json_schema()
    parameters.pop("title", None)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": contract.description,
            "parameters": parameters,
        },
    }


TOOL_SCHEMAS = [
    _tool_schema(name, contract)
    for name, contract in TOOL_CONTRACTS.items()
]


class UnknownToolError(ValueError):
    """Raised before execution when the tool name is unknown."""


class ToolSchemaValidationError(ValueError):
    """Raised before execution when arguments violate the schema."""


def _schema_error_message(
    name: str,
    inputs: dict[str, Any],
    exc: ValidationError,
) -> str:
    """Return stable, useful validation text for logs and repair."""

    allowed_fields = set(
        TOOL_CONTRACTS[name].arguments_model.model_fields
    )
    extra_fields = sorted(set(inputs) - allowed_fields)

    if extra_fields:
        return (
            f"schema validation failed for {name}: "
            "unknown field(s): "
            + ", ".join(extra_fields)
        )

    if name == "search_listings":
        query = inputs.get("query")
        limit = inputs.get("limit", 5)

        if not isinstance(query, str) or not query.strip():
            return "query must be a non-empty string"

        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 25
        ):
            return "limit must be an integer between 1 and 25"

    if name == "listing_details":
        listing_id = inputs.get("listing_id")

        if (
            not isinstance(listing_id, int)
            or isinstance(listing_id, bool)
            or listing_id <= 0
        ):
            return "listing_id must be a positive integer"

    if name == "manager_rent_summary":
        manager_id = inputs.get("property_manager_id")

        if (
            not isinstance(manager_id, int)
            or isinstance(manager_id, bool)
            or manager_id <= 0
        ):
            return (
                "property_manager_id must be a positive integer"
            )

    first_error = exc.errors(include_url=False)[0]
    location = ".".join(
        str(part)
        for part in first_error.get("loc", ())
    )
    detail = first_error.get("msg", "invalid value")

    return (
        f"schema validation failed for {name}: "
        f"{location or 'arguments'}: {detail}"
    )


def validate_tool_inputs(
    name: str,
    inputs: Any,
) -> dict[str, Any]:
    """Strictly validate and normalize arguments before execution."""

    if name not in TOOL_CONTRACTS:
        raise UnknownToolError(f"unknown tool: {name}")

    if not isinstance(inputs, dict):
        raise ToolSchemaValidationError(
            "tool inputs must be a JSON object"
        )

    contract = TOOL_CONTRACTS[name]

    try:
        arguments = contract.arguments_model.model_validate(inputs)
    except ValidationError as exc:
        raise ToolSchemaValidationError(
            _schema_error_message(name, inputs, exc)
        ) from exc

    return arguments.model_dump()


DEFAULT_TOOL_HANDLERS: dict[str, ToolHandler] = {
    "search_listings": search_listings,
    "listing_details": listing_details,
    "manager_rent_summary": manager_rent_summary,
}

BLOCKED_HOUSING_SEARCH_PHRASES = (
    "no children",
    "no kids",
    "no families",
    "families not allowed",
    "adults only",
    "christians only",
    "no muslims",
    "no disabled tenants",
)

SAFETY_ERROR_MESSAGE = (
    "Safety rule blocked a discriminatory "
    "housing search."
)


def _check_safety_rule(
    name: str,
    inputs: dict[str, Any],
) -> str | None:
    """Block discriminatory rental-housing searches."""

    if name != "search_listings":
        return None

    query = inputs.get("query")

    if not isinstance(query, str):
        return None

    normalized_query = " ".join(
        query.lower().split()
    )

    if any(
        phrase in normalized_query
        for phrase in BLOCKED_HOUSING_SEARCH_PHRASES
    ):
        return SAFETY_ERROR_MESSAGE

    return None


def _has_valid_envelope(result: Any) -> bool:
    return (
        isinstance(result, dict)
        and isinstance(result.get("ok"), bool)
        and "data" in result
        and "error" in result
    )


def execute_tool(
    name: str,
    inputs: Any,
    *,
    handlers: dict[str, ToolHandler] | None = None,
) -> str:
    """Execute one domain tool and return a JSON string."""

    registry = (
        DEFAULT_TOOL_HANDLERS
        if handlers is None
        else handlers
    )

    if not isinstance(name, str) or not name.strip():
        return json.dumps(
            error_response(
                "tool name must be a non-empty string"
            )
        )

    try:
        validated_inputs = validate_tool_inputs(
            name,
            inputs,
        )
    except (
        UnknownToolError,
        ToolSchemaValidationError,
    ) as exc:
        return json.dumps(error_response(str(exc)))

    safety_error = _check_safety_rule(
        name,
        validated_inputs,
    )

    if safety_error is not None:
        return json.dumps(
            error_response(safety_error)
        )

    handler = registry.get(name)

    if handler is None:
        return json.dumps(
            error_response(
                f"unknown tool: {name}"
            )
        )

    try:
        result = handler(**validated_inputs)
    except TypeError as exc:
        return json.dumps(
            error_response(
                f"invalid inputs for {name}: {exc}"
            )
        )
    except Exception:
        logger.exception(
            "Unexpected tool failure: %s",
            name,
        )
        return json.dumps(
            error_response(
                f"{name} failed unexpectedly"
            )
        )

    if not _has_valid_envelope(result):
        logger.error(
            "Tool returned an invalid envelope: %s",
            name,
        )
        result = error_response(
            f"{name} returned an invalid result"
        )

    return json.dumps(
        result,
        ensure_ascii=False,
        default=str,
    )
