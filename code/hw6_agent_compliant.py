import re


def normalize_listing_title(value: str) -> str:
    """Return a clean rental-listing title of at most 100 characters."""

    if not isinstance(value, str):
        raise TypeError("listing title must be a string")

    cleaned = re.sub(r"\s+", " ", value).strip()

    if not cleaned:
        raise ValueError("listing title cannot be blank")

    if len(cleaned) > 100:
        raise ValueError("listing title cannot exceed 100 characters")

    return cleaned
