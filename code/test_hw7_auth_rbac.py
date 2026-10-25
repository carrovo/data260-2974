import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Keep all backend tests isolated from developer services and credentials.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = (
    "test-only-jwt-secret-key-2974-not-for-production"
)
os.environ["JWT_ACCESS_TOKEN_MINUTES"] = "30"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth_service import hash_password
from database import Base, get_db
from jwt_service import (
    JWT_ALGORITHM,
    create_access_token,
)
from main import app
from models import PropertyManager, User, UserRole

TEST_PASSWORD = "test-only-password-2974"
TEST_WRONG_SECRET = (
    "wrong-test-only-secret-key-2974-not-production"
)


def create_test_database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )

    return engine, test_session


def seed_database(test_session) -> dict[str, User]:
    password_hash = hash_password(TEST_PASSWORD)

    with test_session() as db:
        users = {
            role.value: User(
                name=f"Test {role.value.title()}",
                email=f"{role.value}@example.com",
                username=role.value,
                password_hash=password_hash,
                role=role,
            )
            for role in UserRole
        }
        manager = PropertyManager(
            firstName="Test",
            lastName="Manager",
            email="manager@example.com",
        )
        db.add_all([*users.values(), manager])
        db.commit()

        for user in users.values():
            db.refresh(user)
            db.expunge(user)

    return users


def bearer(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


def listing_payload(code: str) -> dict:
    return {
        "listingTitle": "JWT Test Apartment",
        "listingCode": code,
        "address": "2974 Test Avenue",
        "description": (
            "An isolated rental listing used only for HW7 tests."
        ),
        "propertyType": "Apartment",
        "monthlyRent": "2100.00",
        "availableUnits": 1,
        "termsAccepted": True,
        "propertyManagerId": 1,
    }


def check_secret_required() -> None:
    test_user = User(
        id=1,
        name="Secret Check",
        email="secret-check@example.com",
        username="secret-check",
        password_hash="test-only-unused-hash",
        role=UserRole.READER,
    )
    configured_secret = os.environ.pop("JWT_SECRET_KEY")

    try:
        try:
            create_access_token(test_user)
        except RuntimeError as exc:
            assert "JWT_SECRET_KEY" in str(exc)
        else:
            raise AssertionError(
                "JWT creation must fail without JWT_SECRET_KEY"
            )
    finally:
        os.environ["JWT_SECRET_KEY"] = configured_secret


async def run_http_checks() -> list[tuple[str, int]]:
    engine, test_session = create_test_database()
    users = seed_database(test_session)

    def override_get_db():
        db = test_session()

        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    results: list[tuple[str, int]] = []

    try:
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            login_response = await client.post(
                "/auth/login",
                json={
                    "username": "reader",
                    "password": TEST_PASSWORD,
                },
            )
            assert login_response.status_code == 200
            login_payload = login_response.json()
            assert login_payload["token_type"] == "bearer"
            assert login_payload["expires_in"] == 1800
            reader_token = login_payload["access_token"]
            results.append(("valid login returns token", 200))

            bad_login = await client.post(
                "/auth/login",
                json={
                    "username": "reader",
                    "password": "wrong-test-only-password",
                },
            )
            assert bad_login.status_code == 401
            results.append(("invalid login", 401))

            oversized_login = await client.post(
                "/auth/login",
                json={
                    "username": "reader",
                    "password": "x" * 73,
                },
            )
            assert oversized_login.status_code == 401
            results.append(("oversized invalid password", 401))

            writer_login = await client.post(
                "/auth/login",
                json={
                    "username": "writer",
                    "password": TEST_PASSWORD,
                },
            )
            moderator_login = await client.post(
                "/auth/login",
                json={
                    "username": "moderator",
                    "password": TEST_PASSWORD,
                },
            )
            assert writer_login.status_code == 200
            assert moderator_login.status_code == 200
            writer_token = writer_login.json()["access_token"]
            moderator_token = moderator_login.json()[
                "access_token"
            ]

            me_response = await client.get(
                "/auth/me",
                headers=bearer(reader_token),
            )
            assert me_response.status_code == 200
            assert me_response.json()["username"] == "reader"
            assert me_response.json()["role"] == "reader"
            results.append(("authenticated /auth/me", 200))

            missing_token = await client.get("/auth/me")
            malformed_token = await client.get(
                "/auth/me",
                headers={"Authorization": "Basic invalid"},
            )
            invalid_token = await client.get(
                "/auth/me",
                headers=bearer("not-a-jwt"),
            )
            assert missing_token.status_code == 401
            assert malformed_token.status_code == 401
            assert invalid_token.status_code == 401
            results.extend(
                [
                    ("missing token", 401),
                    ("malformed authorization", 401),
                    ("invalid token", 401),
                ]
            )

            wrong_signature = jwt.encode(
                {
                    "sub": str(users["reader"].id),
                    "username": "reader",
                    "role": "reader",
                    "type": "access",
                    "iat": 1,
                    "exp": 4102444800,
                },
                TEST_WRONG_SECRET,
                algorithm=JWT_ALGORITHM,
            )
            wrong_signature_response = await client.get(
                "/auth/me",
                headers=bearer(wrong_signature),
            )
            assert wrong_signature_response.status_code == 401
            results.append(("wrong signature token", 401))

            expired_token, _ = create_access_token(
                users["reader"],
                expires_delta=timedelta(seconds=-1),
            )
            expired_response = await client.get(
                "/auth/me",
                headers=bearer(expired_token),
            )
            assert expired_response.status_code == 401
            results.append(("expired token", 401))

            missing_user = User(
                id=99999,
                name="Deleted Test User",
                email="deleted@example.com",
                username="deleted-user",
                password_hash="test-only-unused-hash",
                role=UserRole.READER,
            )
            missing_user_token, _ = create_access_token(
                missing_user
            )
            missing_user_response = await client.get(
                "/auth/me",
                headers=bearer(missing_user_token),
            )
            assert missing_user_response.status_code == 401
            results.append(("token user no longer exists", 401))

            list_response = await client.get(
                "/api/listings",
                headers=bearer(reader_token),
            )
            assert list_response.status_code == 200
            assert list_response.json() == []
            results.append(("authenticated reader list", 200))

            unauthenticated_list = await client.get(
                "/api/listings"
            )
            assert unauthenticated_list.status_code == 401
            results.append(("unauthenticated list", 401))

            reader_create = await client.post(
                "/api/listings",
                headers=bearer(reader_token),
                json=listing_payload("S2974-JWT-READER"),
            )
            assert reader_create.status_code == 403
            results.append(("reader create", 403))

            now = datetime.now(UTC)
            elevated_claim_token = jwt.encode(
                {
                    "sub": str(users["reader"].id),
                    "username": "reader",
                    "role": "moderator",
                    "type": "access",
                    "iat": now,
                    "exp": now + timedelta(minutes=5),
                },
                os.environ["JWT_SECRET_KEY"],
                algorithm=JWT_ALGORITHM,
            )
            elevated_claim_create = await client.post(
                "/api/listings",
                headers=bearer(elevated_claim_token),
                json=listing_payload("S2974-JWT-CLAIM"),
            )
            assert elevated_claim_create.status_code == 403
            results.append(("database role overrides token claim", 403))

            writer_create = await client.post(
                "/api/listings",
                headers=bearer(writer_token),
                json=listing_payload("S2974-JWT-WRITER"),
            )
            assert writer_create.status_code == 201
            listing_id = writer_create.json()["id"]
            results.append(("writer create", 201))

            reader_update = await client.put(
                f"/api/listings/{listing_id}",
                headers=bearer(reader_token),
                json={"monthlyRent": "2200.00"},
            )
            assert reader_update.status_code == 403
            results.append(("reader update", 403))

            writer_update = await client.put(
                f"/api/listings/{listing_id}",
                headers=bearer(writer_token),
                json={"monthlyRent": "2200.00"},
            )
            assert writer_update.status_code == 200
            assert Decimal(
                writer_update.json()["monthlyRent"]
            ) == Decimal("2200.00")
            results.append(("writer update", 200))

            writer_delete = await client.delete(
                f"/api/listings/{listing_id}",
                headers=bearer(writer_token),
            )
            assert writer_delete.status_code == 403
            results.append(("writer delete", 403))

            moderator_delete = await client.delete(
                f"/api/listings/{listing_id}",
                headers=bearer(moderator_token),
            )
            assert moderator_delete.status_code == 204
            results.append(("moderator delete", 204))

            reader_manager_create = await client.post(
                "/api/property-managers",
                headers=bearer(reader_token),
                json={
                    "firstName": "Blocked",
                    "lastName": "Reader",
                    "email": "blocked-reader@example.com",
                },
            )
            assert reader_manager_create.status_code == 403
            results.append(("reader manager create", 403))

            writer_manager_create = await client.post(
                "/api/property-managers",
                headers=bearer(writer_token),
                json={
                    "firstName": "Allowed",
                    "lastName": "Writer",
                    "email": "allowed-writer@example.com",
                },
            )
            assert writer_manager_create.status_code == 201
            results.append(("writer manager create", 201))

            public_register = await client.post(
                "/auth/register",
                json={
                    "name": "Public Reader",
                    "email": "public-reader@example.com",
                    "username": "public-reader",
                    "password": TEST_PASSWORD,
                },
            )
            assert public_register.status_code == 201
            assert public_register.json()["role"] == "reader"
            results.append(("public registration creates reader", 201))

            role_injection = await client.post(
                "/auth/register",
                json={
                    "name": "Privilege Attempt",
                    "email": "attempt@example.com",
                    "username": "privilege-attempt",
                    "password": TEST_PASSWORD,
                    "role": "moderator",
                },
            )
            assert role_injection.status_code == 422
            results.append(("public role injection", 422))
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    return results


def main() -> None:
    check_secret_required()
    results = asyncio.run(run_http_checks())

    print("HW7 JWT + RBAC BACKEND TESTS")
    print("Database: isolated in-memory SQLite")
    print("JWT key: test-only environment value\n")
    print("PASS | CONFIG | missing JWT secret is rejected")

    for name, status_code in results:
        print(f"PASS | HTTP {status_code} | {name}")

    total = len(results) + 1
    print(f"\nFINAL SUMMARY: {total}/{total} PASS")


if __name__ == "__main__":
    main()
