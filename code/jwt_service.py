import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from models import User, UserRole

# The signing key is intentionally read from the environment at call time.
JWT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_MINUTES = 30


class AccessTokenError(ValueError):
    """Raised when a bearer token cannot be trusted."""


def _secret_key() -> str:
    secret = os.getenv("JWT_SECRET_KEY")

    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set in the environment"
        )

    if len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must contain at least 32 characters"
        )

    return secret


def access_token_minutes() -> int:
    raw_value = os.getenv(
        "JWT_ACCESS_TOKEN_MINUTES",
        str(DEFAULT_ACCESS_TOKEN_MINUTES),
    )

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_MINUTES must be an integer"
        ) from exc

    if value < 1:
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_MINUTES must be positive"
        )

    return value


def _role_value(role: UserRole | str) -> str:
    if isinstance(role, UserRole):
        return role.value

    return UserRole(role).value


def create_access_token(
    user: User,
    *,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Create one signed access token and return its lifetime."""

    now = datetime.now(UTC)
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=access_token_minutes())
    )
    expires_at = now + lifetime
    lifetime_seconds = max(
        0,
        int(lifetime.total_seconds()),
    )
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": _role_value(user.role),
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(
        payload,
        _secret_key(),
        algorithm=JWT_ALGORITHM,
    )

    return token, lifetime_seconds


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate one access token and return its trusted claims."""

    try:
        payload = jwt.decode(
            token,
            _secret_key(),
            algorithms=[JWT_ALGORITHM],
            options={
                "require": [
                    "sub",
                    "username",
                    "role",
                    "type",
                    "iat",
                    "exp",
                ],
            },
        )
    except ExpiredSignatureError as exc:
        raise AccessTokenError(
            "Access token has expired"
        ) from exc
    except InvalidTokenError as exc:
        raise AccessTokenError(
            "Access token is invalid"
        ) from exc

    if payload.get("type") != "access":
        raise AccessTokenError(
            "Token is not an access token"
        )

    try:
        user_id = int(payload["sub"])
        UserRole(str(payload["role"]))
    except (TypeError, ValueError) as exc:
        raise AccessTokenError(
            "Access token claims are invalid"
        ) from exc

    if user_id < 1:
        raise AccessTokenError(
            "Access token subject is invalid"
        )

    payload["user_id"] = user_id

    return payload
