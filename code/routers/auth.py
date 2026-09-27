import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth_service import (
    SESSION_TTL_MINUTES,
    create_session,
    create_user,
    delete_session,
    get_user_by_email,
    get_valid_session,
    verify_password,
)
from database import get_db
from models import SessionToken, User
from schemas import (
    LoginResponse,
    UserCreate,
    UserLogin,
    UserOut,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["authentication"],
)

SESSION_COOKIE_NAME = "session_id"

# Local development uses HTTP, so Secure must be false.
# It should be enabled in production behind HTTPS.
COOKIE_SECURE = os.getenv(
    "COOKIE_SECURE",
    "false",
).lower() in {"true", "1", "yes"}


def require_session(
    request: Request,
    db: Session = Depends(get_db),
) -> SessionToken:
    """
    Require a valid server-side session.

    The browser sends only the opaque session_id cookie.
    The actual user and expiration data are loaded from MySQL.
    """

    token = request.cookies.get(SESSION_COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Login required",
        )

    session = get_valid_session(db, token)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid",
        )

    return session


@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    """Create a new user account with a bcrypt password hash."""

    if get_user_by_email(db, str(payload.email)):
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    try:
        return create_user(db, payload)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    payload: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Verify credentials and issue an HTTP-only session cookie."""

    user = get_user_by_email(db, str(payload.email))

    if user is None or not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    session = create_session(db, user.id)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.id,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_TTL_MINUTES * 60,
        path="/",
    )

    return LoginResponse(
        message="Logged in successfully",
        user_id=user.id,
        email=user.email,
    )


@router.get(
    "/me",
    response_model=UserOut,
)
def me(
    session: SessionToken = Depends(require_session),
    db: Session = Depends(get_db),
) -> User:
    """Return the user associated with the current session."""

    user = db.get(User, session.user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Session user no longer exists",
        )

    return user


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete the server-side session and browser cookie."""

    token = request.cookies.get(SESSION_COOKIE_NAME)

    if token:
        delete_session(db, token)

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )

    return {
        "message": "Logged out successfully",
    }