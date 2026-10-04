import logging
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


API_BASE_URL = "https://www.themealdb.com/api/json/v1/1"
REQUEST_TIMEOUT_SECONDS = 10.0

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("meals")

mcp = FastMCP(
    "meals",
    dependencies=[
        "mcp==1.9.4",
        "httpx==0.28.1",
    ],
)


def _validate_text(value: str, field_name: str) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")

    return cleaned


def _validate_limit(limit: int) -> int:
    if not 1 <= limit <= 25:
        raise ValueError("limit must be between 1 and 25")

    return limit


def _normalize_meal_id(meal_id: str | int) -> str:
    normalized = str(meal_id).strip()

    if not normalized.isdigit() or int(normalized) <= 0:
        raise ValueError("id must be a positive numeric meal ID")

    return normalized


async def _request_meals(
    endpoint: str,
    params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    url = f"{API_BASE_URL}/{endpoint}"

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        logger.error("TheMealDB request timed out: %s", endpoint)
        raise RuntimeError(
            "TheMealDB request timed out"
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.error(
            "TheMealDB returned HTTP %s for %s",
            exc.response.status_code,
            endpoint,
        )
        raise RuntimeError(
            "TheMealDB returned an unsuccessful response"
        ) from exc
    except httpx.RequestError as exc:
        logger.error(
            "TheMealDB network request failed: %s",
            endpoint,
        )
        raise RuntimeError(
            "Unable to reach TheMealDB"
        ) from exc
    except ValueError as exc:
        logger.error(
            "TheMealDB returned invalid JSON: %s",
            endpoint,
        )
        raise RuntimeError(
            "TheMealDB returned invalid JSON"
        ) from exc

    meals = payload.get("meals")

    if meals is None:
        return []

    if not isinstance(meals, list):
        raise RuntimeError(
            "TheMealDB returned an unexpected response shape"
        )

    return meals


def _meal_details(meal: dict[str, Any]) -> dict[str, Any]:
    ingredients: list[dict[str, str]] = []

    for number in range(1, 21):
        ingredient = (
            meal.get(f"strIngredient{number}") or ""
        ).strip()
        measure = (
            meal.get(f"strMeasure{number}") or ""
        ).strip()

        if ingredient:
            ingredients.append(
                {
                    "name": ingredient,
                    "measure": measure,
                }
            )

    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource") or None,
        "youtube": meal.get("strYoutube") or None,
        "ingredients": ingredients,
    }


@mcp.tool()
async def search_meals_by_name(
    query: str,
    limit: int = 5,
) -> Any:
    """Search TheMealDB for meals whose names match a query."""

    cleaned_query = _validate_text(query, "query")
    safe_limit = _validate_limit(limit)

    meals = await _request_meals(
        "search.php",
        {"s": cleaned_query},
    )

    if not meals:
        return {
            "message": "no matches",
            "results": [],
        }

    return [
        {
            "id": meal.get("idMeal"),
            "name": meal.get("strMeal"),
            "area": meal.get("strArea"),
            "category": meal.get("strCategory"),
            "thumb": meal.get("strMealThumb"),
        }
        for meal in meals[:safe_limit]
    ]


@mcp.tool()
async def meals_by_ingredient(
    ingredient: str,
    limit: int = 12,
) -> Any:
    """Return meals that use the requested main ingredient."""

    cleaned_ingredient = _validate_text(
        ingredient,
        "ingredient",
    )
    safe_limit = _validate_limit(limit)

    meals = await _request_meals(
        "filter.php",
        {"i": cleaned_ingredient},
    )

    if not meals:
        return {
            "message": "no matches",
            "results": [],
        }

    return [
        {
            "id": meal.get("idMeal"),
            "name": meal.get("strMeal"),
            "thumb": meal.get("strMealThumb"),
        }
        for meal in meals[:safe_limit]
    ]


@mcp.tool()
async def meal_details(id: str | int) -> Any:
    """Look up the complete recipe for one meal ID."""

    meal_id = _normalize_meal_id(id)

    meals = await _request_meals(
        "lookup.php",
        {"i": meal_id},
    )

    if not meals:
        return {
            "message": "no matches",
            "meal": None,
        }

    return _meal_details(meals[0])


@mcp.tool()
async def random_meal() -> Any:
    """Return one random meal with its complete recipe."""

    meals = await _request_meals("random.php")

    if not meals:
        return {
            "message": "no matches",
            "meal": None,
        }

    return _meal_details(meals[0])


if __name__ == "__main__":
    mcp.run(transport="stdio")