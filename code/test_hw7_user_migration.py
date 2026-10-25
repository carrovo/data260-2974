import os
from collections.abc import Callable

# Keep this validation isolated from any developer MySQL configuration.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from migrate_hw7_users import (
    ALLOWED_ROLES,
    generate_legacy_username,
    migrate_user_schema,
)
from models import User

TEST_PASSWORD_HASH = "test-only-not-a-real-password-hash"


def create_memory_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )


def assert_integrity_error(
    engine,
    statement: str,
    parameters: dict,
) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(
                text(statement),
                parameters,
            )
    except IntegrityError:
        return

    raise AssertionError(
        "Expected the database constraint to reject the row"
    )


def create_legacy_users_table(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL
            )
            """
        )


def test_username_generation() -> None:
    used = {"alice"}

    generated = generate_legacy_username(
        "Alice+student@example.com",
        7,
        used,
    )
    assert generated == "alice_student"

    used.add(generated.casefold())
    collision = generate_legacy_username(
        "alice.student@example.org",
        8,
        used,
    )
    assert collision == "alice_student-8"

    fallback = generate_legacy_username(
        "+++@example.net",
        9,
        used,
    )
    assert fallback == "user"


def test_mysql_model_ddl() -> None:
    ddl = str(
        CreateTable(User.__table__).compile(
            dialect=mysql.dialect(),
        )
    )

    assert "username VARCHAR(100) NOT NULL" in ddl
    assert "UNIQUE (username)" in ddl
    assert (
        "`role` ENUM('reader','writer','moderator') "
        "NOT NULL DEFAULT 'reader'"
    ) in ddl
    assert "ck_users_username_not_blank" in ddl


def test_fresh_schema_constraints() -> None:
    engine = create_memory_engine()

    try:
        summary = migrate_user_schema(engine)
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("users")
        }

        assert set(columns) == {
            "id",
            "name",
            "email",
            "username",
            "password_hash",
            "role",
        }
        assert columns["username"]["nullable"] is False
        assert columns["role"]["nullable"] is False
        assert tuple(User.__table__.c.role.type.enums) == (
            ALLOWED_ROLES
        )
        assert summary["user_count"] == 0

        with Session(engine) as session:
            legacy_caller_user = User(
                name="Legacy ORM Caller",
                email="legacy-caller@example.com",
                password_hash=TEST_PASSWORD_HASH,
            )
            session.add(legacy_caller_user)
            session.commit()
            session.refresh(legacy_caller_user)

            assert legacy_caller_user.username.startswith(
                "legacy_caller-"
            )
            assert legacy_caller_user.role.value == "reader"

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(name, email, username, password_hash) "
                    "VALUES (:name, :email, :username, :hash)"
                ),
                {
                    "name": "Reader One",
                    "email": "reader1@example.com",
                    "username": "reader1",
                    "hash": TEST_PASSWORD_HASH,
                },
            )

            role = connection.execute(
                text(
                    "SELECT role FROM users "
                    "WHERE username = 'reader1'"
                )
            ).scalar_one()

        assert role == "reader"

        insert_statement = (
            "INSERT INTO users "
            "(name, email, username, password_hash, role) "
            "VALUES (:name, :email, :username, :hash, :role)"
        )

        assert_integrity_error(
            engine,
            insert_statement,
            {
                "name": "Duplicate Username",
                "email": "reader2@example.com",
                "username": "reader1",
                "hash": TEST_PASSWORD_HASH,
                "role": "reader",
            },
        )
        assert_integrity_error(
            engine,
            insert_statement,
            {
                "name": "Invalid Role",
                "email": "invalid-role@example.com",
                "username": "invalid-role",
                "hash": TEST_PASSWORD_HASH,
                "role": "administrator",
            },
        )
        assert_integrity_error(
            engine,
            insert_statement,
            {
                "name": "Blank Username",
                "email": "blank@example.com",
                "username": "   ",
                "hash": TEST_PASSWORD_HASH,
                "role": "reader",
            },
        )
    finally:
        engine.dispose()


def test_legacy_migration_is_repeatable() -> None:
    engine = create_memory_engine()

    try:
        create_legacy_users_table(engine)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, name, email, password_hash) VALUES "
                    "(1, 'First Alice', 'Alice@example.com', :hash), "
                    "(2, 'Second Alice', 'alice@other.example', :hash), "
                    "(3, 'Fallback User', '+++@example.net', :hash)"
                ),
                {"hash": TEST_PASSWORD_HASH},
            )

        first_summary = migrate_user_schema(engine)

        with engine.connect() as connection:
            first_rows = connection.execute(
                text(
                    "SELECT id, username, role "
                    "FROM users ORDER BY id"
                )
            ).mappings().all()

        second_summary = migrate_user_schema(engine)

        with engine.connect() as connection:
            second_rows = connection.execute(
                text(
                    "SELECT id, username, role "
                    "FROM users ORDER BY id"
                )
            ).mappings().all()

        expected = [
            {
                "id": 1,
                "username": "alice",
                "role": "reader",
            },
            {
                "id": 2,
                "username": "alice-2",
                "role": "reader",
            },
            {
                "id": 3,
                "username": "user",
                "role": "reader",
            },
        ]

        assert [dict(row) for row in first_rows] == expected
        assert [dict(row) for row in second_rows] == expected
        assert first_summary == second_summary
        assert first_summary["role_counts"] == {
            "reader": 3,
            "writer": 0,
            "moderator": 0,
        }

        assert_integrity_error(
            engine,
            (
                "INSERT INTO users "
                "(id, name, email, password_hash, username, role) "
                "VALUES (4, :name, :email, :hash, :username, :role)"
            ),
            {
                "name": "Duplicate",
                "email": "duplicate@example.com",
                "hash": TEST_PASSWORD_HASH,
                "username": "alice",
                "role": "reader",
            },
        )
    finally:
        engine.dispose()


def test_invalid_existing_role_stops() -> None:
    engine = create_memory_engine()

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    username VARCHAR(100),
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(16)
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, name, email, username, password_hash, role) "
                    "VALUES (1, :name, :email, :username, :hash, :role)"
                ),
                {
                    "name": "Ambiguous User",
                    "email": "ambiguous@example.com",
                    "username": "ambiguous",
                    "hash": TEST_PASSWORD_HASH,
                    "role": "administrator",
                },
            )

        try:
            migrate_user_schema(engine)
        except RuntimeError as exc:
            assert "unsupported role" in str(exc)
        else:
            raise AssertionError(
                "Migration should stop on an unknown existing role"
            )
    finally:
        engine.dispose()


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("username generation", test_username_generation),
    ("MySQL model DDL", test_mysql_model_ddl),
    ("fresh schema constraints", test_fresh_schema_constraints),
    ("repeatable legacy migration", test_legacy_migration_is_repeatable),
    ("invalid existing role stops", test_invalid_existing_role_stops),
]


def main() -> None:
    passed = 0

    print("HW7 USER MIGRATION OFFLINE TESTS")
    print("Database: isolated in-memory SQLite fixtures\n")

    for name, test_function in TESTS:
        try:
            test_function()
        except Exception as exc:
            print(f"FAIL | {name} | {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS | {name}")

    print(f"\nFINAL SUMMARY: {passed}/{len(TESTS)} PASS")

    if passed != len(TESTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
