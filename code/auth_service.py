import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User, UserRole
from schemas import UserCreate


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

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        # bcrypt rejects passwords over 72 bytes and malformed hashes.
        # Neither condition should turn invalid credentials into a 500.
        return False


def create_user(
    db: Session,
    payload: UserCreate,
) -> User:
    """Create a user while storing only the password hash."""

    user = User(
        name=payload.name.strip(),
        email=str(payload.email).lower(),
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=UserRole.READER,
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


def get_user_by_username(
    db: Session,
    username: str,
) -> User | None:
    """Find one user by normalized username."""

    statement = select(User).where(
        User.username == username.strip().lower()
    )

    return db.scalar(statement)
