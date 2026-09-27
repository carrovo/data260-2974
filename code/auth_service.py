import secrets
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import SessionToken, User
from schemas import UserCreate


SESSION_TTL_MINUTES = 30


def hash_password(password: str) -> str:
    """Create a bcrypt hash for a plain-text password."""

    password_bytes = password.encode("utf-8")
    hashed_bytes = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(),
    )

    return hashed_bytes.decode("utf-8")


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """Compare a plain password with its stored bcrypt hash."""

    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def create_user(
    db: Session,
    payload: UserCreate,
) -> User:
    """Create a user while storing only the password hash."""

    user = User(
        name=payload.name.strip(),
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def get_user_by_email(
    db: Session,
    email: str,
) -> User | None:
    """Find one user by normalized email address."""

    statement = select(User).where(
        User.email == email.lower()
    )

    return db.scalar(statement)


def create_session(
    db: Session,
    user_id: int,
) -> SessionToken:
    """
    Create an opaque server-side session token.

    Only the token ID will be sent to the browser.
    The user ID and expiration time remain in MySQL.
    """

    # Generate an opaque random token for the HTTP-only cookie.
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.utcnow()
        + timedelta(minutes=SESSION_TTL_MINUTES)
    )

    session = SessionToken(
        id=token,
        user_id=user_id,
        expires_at=expires_at,
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def get_valid_session(
    db: Session,
    token: str,
) -> SessionToken | None:
    """Return a session only when its token exists and has not expired."""

    session = db.get(SessionToken, token)

    if session is None:
        return None

    if session.expires_at < datetime.utcnow():
        db.delete(session)
        db.commit()
        return None

    return session


def delete_session(
    db: Session,
    token: str,
) -> bool:
    """Delete one server-side session."""

    session = db.get(SessionToken, token)

    if session is None:
        return False

    db.delete(session)
    db.commit()

    return True