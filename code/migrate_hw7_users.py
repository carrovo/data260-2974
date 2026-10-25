import re
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from database import db_session_basede26
from models import User, UserRole

USERNAME_MAX_LENGTH = 100
ALLOWED_ROLES = tuple(role.value for role in UserRole)
USERNAME_INDEX_NAME = "uq_users_username"
USERNAME_CHECK_NAME = "ck_users_username_not_blank"


def _column_map(engine: Engine) -> dict[str, dict[str, Any]]:
    return {
        column["name"]: column
        for column in inspect(engine).get_columns("users")
    }


def _unique_username_exists(engine: Engine) -> bool:
    inspector = inspect(engine)

    for constraint in inspector.get_unique_constraints("users"):
        if constraint.get("column_names") == ["username"]:
            return True

    for index in inspector.get_indexes("users"):
        if (
            index.get("unique")
            and index.get("column_names") == ["username"]
        ):
            return True

    return False


def _check_constraint_exists(
    engine: Engine,
    constraint_name: str,
) -> bool:
    constraints = inspect(engine).get_check_constraints("users")

    return any(
        constraint.get("name") == constraint_name
        for constraint in constraints
    )


def _base_username(email: str) -> str:
    local_part = str(email).partition("@")[0].lower()
    normalized = re.sub(
        r"[^a-z0-9]+",
        "_",
        local_part,
    ).strip("_")

    return normalized or "user"


def generate_legacy_username(
    email: str,
    user_id: int,
    used_usernames: set[str],
) -> str:
    """Build a deterministic username without replacing existing names."""

    base = _base_username(email)
    candidate = base[:USERNAME_MAX_LENGTH]

    if candidate.casefold() not in used_usernames:
        return candidate

    suffix = f"-{user_id}"
    candidate = (
        base[: USERNAME_MAX_LENGTH - len(suffix)]
        + suffix
    )

    counter = 2

    while candidate.casefold() in used_usernames:
        suffix = f"-{user_id}-{counter}"
        candidate = (
            base[: USERNAME_MAX_LENGTH - len(suffix)]
            + suffix
        )
        counter += 1

    return candidate


def _preflight_existing_users(
    engine: Engine,
    columns: dict[str, dict[str, Any]],
) -> None:
    required_legacy_columns = {
        "id",
        "name",
        "email",
        "password_hash",
    }
    missing = required_legacy_columns - set(columns)

    if missing:
        raise RuntimeError(
            "Existing users table is missing required columns: "
            f"{sorted(missing)}"
        )

    selected_columns = ["id", "email"]

    if "username" in columns:
        selected_columns.append("username")

    if "role" in columns:
        selected_columns.append("role")

    statement = text(
        "SELECT "
        + ", ".join(f"`{name}`" for name in selected_columns)
        + " FROM users ORDER BY id"
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    seen_usernames: dict[str, int] = {}

    for row in rows:
        if "username" in columns:
            username = row["username"]

            if username is not None and str(username).strip():
                username_text = str(username)

                if len(username_text) > USERNAME_MAX_LENGTH:
                    raise RuntimeError(
                        "Existing username exceeds 100 characters "
                        f"for user id {row['id']}"
                    )

                normalized = username_text.casefold()
                previous_id = seen_usernames.get(normalized)

                if previous_id is not None:
                    raise RuntimeError(
                        "Existing usernames are not unique: "
                        f"user ids {previous_id} and {row['id']}"
                    )

                seen_usernames[normalized] = int(row["id"])

        if "role" in columns:
            role = row["role"]

            if (
                role is not None
                and str(role).strip()
                and str(role) not in ALLOWED_ROLES
            ):
                raise RuntimeError(
                    "Existing user has unsupported role "
                    f"{role!r} at user id {row['id']}"
                )


def _add_missing_columns(
    engine: Engine,
    columns: dict[str, dict[str, Any]],
) -> None:
    dialect = engine.dialect.name

    with engine.begin() as connection:
        if "username" not in columns:
            username_definition = "VARCHAR(100) NULL"

            if dialect == "sqlite":
                username_definition += (
                    " CHECK (username IS NULL OR "
                    "LENGTH(TRIM(username)) > 0)"
                )

            connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN "
                    f"username {username_definition}"
                )
            )

        if "role" not in columns:
            if dialect == "mysql":
                role_definition = (
                    "ENUM('reader','writer','moderator') "
                    "NOT NULL DEFAULT 'reader'"
                )
            else:
                role_definition = (
                    "VARCHAR(16) NOT NULL DEFAULT 'reader' "
                    "CHECK (role IN "
                    "('reader','writer','moderator'))"
                )

            connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN "
                    f"role {role_definition}"
                )
            )


def _backfill_users(engine: Engine) -> None:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                "SELECT id, email, username "
                "FROM users ORDER BY id"
            )
        ).mappings().all()

        used_usernames = {
            str(row["username"]).casefold()
            for row in rows
            if row["username"] is not None
            and str(row["username"]).strip()
        }

        for row in rows:
            if (
                row["username"] is not None
                and str(row["username"]).strip()
            ):
                continue

            username = generate_legacy_username(
                email=str(row["email"]),
                user_id=int(row["id"]),
                used_usernames=used_usernames,
            )

            connection.execute(
                text(
                    "UPDATE users SET username = :username "
                    "WHERE id = :user_id"
                ),
                {
                    "username": username,
                    "user_id": row["id"],
                },
            )
            used_usernames.add(username.casefold())

        connection.execute(
            text(
                "UPDATE users SET role = 'reader' "
                "WHERE role IS NULL OR TRIM(role) = ''"
            )
        )


def _apply_mysql_constraints(engine: Engine) -> None:
    columns = _column_map(engine)
    username_type = columns["username"]["type"]

    with engine.begin() as connection:
        if (
            columns["username"].get("nullable", True)
            or getattr(username_type, "length", None)
            != USERNAME_MAX_LENGTH
        ):
            connection.execute(
                text(
                    "ALTER TABLE users MODIFY COLUMN "
                    "username VARCHAR(100) NOT NULL"
                )
            )

        role_type = columns["role"]["type"]
        role_values = tuple(getattr(role_type, "enums", ()))
        role_default = columns["role"].get("default")
        normalized_default = (
            str(role_default).strip("'\"")
            if role_default is not None
            else None
        )

        if (
            columns["role"].get("nullable", True)
            or role_values != ALLOWED_ROLES
            or normalized_default != UserRole.READER.value
        ):
            connection.execute(
                text(
                    "ALTER TABLE users MODIFY COLUMN role "
                    "ENUM('reader','writer','moderator') "
                    "NOT NULL DEFAULT 'reader'"
                )
            )

    if not _check_constraint_exists(
        engine,
        USERNAME_CHECK_NAME,
    ):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE users ADD CONSTRAINT "
                    f"{USERNAME_CHECK_NAME} "
                    "CHECK (LENGTH(TRIM(username)) > 0)"
                )
            )


def _add_unique_username_index(engine: Engine) -> None:
    if _unique_username_exists(engine):
        return

    existing_names = {
        index.get("name")
        for index in inspect(engine).get_indexes("users")
    }

    if USERNAME_INDEX_NAME in existing_names:
        raise RuntimeError(
            f"Index name {USERNAME_INDEX_NAME!r} already exists "
            "but does not uniquely cover username"
        )

    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX {USERNAME_INDEX_NAME} "
                "ON users (username)"
            )
        )


def validate_user_schema(engine: Engine) -> dict[str, Any]:
    """Validate the migrated schema without exposing user details."""

    columns = _column_map(engine)
    required_columns = {
        "id",
        "name",
        "email",
        "username",
        "password_hash",
        "role",
    }
    missing = required_columns - set(columns)

    if missing:
        raise RuntimeError(
            "User schema validation failed; missing columns: "
            f"{sorted(missing)}"
        )

    if engine.dialect.name == "mysql":
        username_length = getattr(
            columns["username"]["type"],
            "length",
            None,
        )

        if username_length != USERNAME_MAX_LENGTH:
            raise RuntimeError(
                "username must be VARCHAR(100)"
            )

        if columns["username"].get("nullable", True):
            raise RuntimeError("username must be NOT NULL")

        if columns["role"].get("nullable", True):
            raise RuntimeError("role must be NOT NULL")

        role_default = columns["role"].get("default")
        normalized_default = (
            str(role_default).strip("'\"")
            if role_default is not None
            else None
        )

        if normalized_default != UserRole.READER.value:
            raise RuntimeError(
                "role must default to reader"
            )

        role_values = tuple(
            getattr(columns["role"]["type"], "enums", ())
        )

        if role_values != ALLOWED_ROLES:
            raise RuntimeError(
                "role enum does not match the required roles"
            )

        if not _check_constraint_exists(
            engine,
            USERNAME_CHECK_NAME,
        ):
            raise RuntimeError(
                "username non-blank constraint is missing"
            )

    if not _unique_username_exists(engine):
        raise RuntimeError("username uniqueness is not enforced")

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, username, role "
                "FROM users ORDER BY id"
            )
        ).mappings().all()

    seen_usernames: set[str] = set()
    role_counts = {
        role: 0
        for role in ALLOWED_ROLES
    }

    for row in rows:
        username = row["username"]

        if username is None or not str(username).strip():
            raise RuntimeError(
                f"User id {row['id']} has no username"
            )

        normalized = str(username).casefold()

        if normalized in seen_usernames:
            raise RuntimeError(
                "Case-insensitive duplicate username found"
            )

        seen_usernames.add(normalized)

        role = str(row["role"])

        if role not in ALLOWED_ROLES:
            raise RuntimeError(
                f"User id {row['id']} has unsupported role"
            )

        role_counts[role] += 1

    return {
        "dialect": engine.dialect.name,
        "user_count": len(rows),
        "role_counts": role_counts,
        "username_unique": True,
    }


def migrate_user_schema(engine: Engine) -> dict[str, Any]:
    """Upgrade an existing users table or create a new HW7 table."""

    if engine.dialect.name not in {"mysql", "sqlite"}:
        raise RuntimeError(
            "HW7 user migration supports MySQL; SQLite is allowed "
            "only for offline validation"
        )

    if "users" not in inspect(engine).get_table_names():
        User.__table__.create(
            bind=engine,
            checkfirst=True,
        )
        return validate_user_schema(engine)

    columns = _column_map(engine)
    _preflight_existing_users(engine, columns)
    _add_missing_columns(engine, columns)
    _backfill_users(engine)

    if engine.dialect.name == "mysql":
        _apply_mysql_constraints(engine)

    _add_unique_username_index(engine)

    return validate_user_schema(engine)


def main() -> None:
    if db_session_basede26.dialect.name != "mysql":
        raise RuntimeError(
            "The command-line HW7 migration must target MySQL"
        )

    summary = migrate_user_schema(db_session_basede26)

    print("HW7 users migration complete")
    print(f"Users preserved: {summary['user_count']}")
    print(f"Role counts: {summary['role_counts']}")
    print("Username uniqueness: verified")


if __name__ == "__main__":
    main()
