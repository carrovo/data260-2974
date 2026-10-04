import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from domain_tools import (
    listing_details as listing_details_operation,
)
from domain_tools import (
    manager_rent_summary as manager_rent_summary_operation,
)
from domain_tools import (
    search_listings as search_listings_operation,
)


logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

mcp = FastMCP(
    "s2974_rel",
    dependencies=[
        "mcp==1.9.4",
        "SQLAlchemy==2.0.54",
        "PyMySQL==1.2.3",
        "python-dotenv==1.2.3",
    ],
)


@mcp.tool()
def search_listings(
    query: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Search rental listings using a keyword."""

    return search_listings_operation(query, limit)


@mcp.tool()
def listing_details(
    listing_id: int,
) -> dict[str, Any]:
    """Return one rental listing and its property manager."""

    return listing_details_operation(listing_id)


@mcp.tool()
def manager_rent_summary(
    property_manager_id: int,
) -> dict[str, Any]:
    """Return aggregate rental statistics for one manager."""

    return manager_rent_summary_operation(
        property_manager_id
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")