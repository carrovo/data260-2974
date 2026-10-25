from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth_service import (
    create_user,
    get_user_by_email,
    get_user_by_username,
    verify_password,
)
from database import get_db
from jwt_service import (
    AccessTokenError,
    create_access_token,
    decode_access_token,
)
from models import User, UserRole
from schemas import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserOut,
)

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)
bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def _bearer_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    if credentials is None:
        raise unauthorized("Bearer token is required")

    token = credentials.credentials.strip()

    if not token:
        raise unauthorized("Bearer token is required")

    return token


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate a bearer token and load its current database user."""

    token = _bearer_token(credentials)

    try:
        payload = decode_access_token(token)
    except AccessTokenError as exc:
        raise unauthorized(str(exc)) from exc

    user = db.get(User, payload["user_id"])

    if user is None:
        raise unauthorized(
            "Access token user no longer exists"
        )

    return user


def require_roles(*allowed_roles: UserRole):
    """Create a dependency that rejects authenticated users with 403."""

    allowed_values = {
        role.value
        for role in allowed_roles
    }

    def dependency(
        user: User = Depends(get_current_user),
    ) -> User:
        role = (
            user.role.value
            if isinstance(user.role, UserRole)
            else str(user.role)
        )

        if role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this operation",
            )

        return user

    return dependency


require_writer = require_roles(
    UserRole.WRITER,
    UserRole.MODERATOR,
)
require_moderator = require_roles(
    UserRole.MODERATOR,
)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    """Create a reader account; public callers cannot select a role."""

    if get_user_by_username(db, payload.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already registered",
        )

    if get_user_by_email(db, str(payload.email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    try:
        return create_user(db, payload)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Verify username/password credentials and return a JWT."""

    user = get_user_by_username(db, payload.username)

    if user is None or not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise unauthorized(
            "Invalid username or password"
        )

    token, expires_in = create_access_token(user)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
    )


@router.get(
    "/me",
    response_model=UserOut,
)
def me(
    user: User = Depends(get_current_user),
) -> User:
    """Return the identity and current role for a bearer token."""

    return user
