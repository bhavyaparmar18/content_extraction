"""Tests for Login Page API, Session Management, Rotation, and Security Contracts."""

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config.settings import Settings
from app.stores.auth_store import AuthStore
from app.services.auth import PasswordService, TokenService, LoginService


@pytest.fixture
def isolated_auth_store(tmp_path):
    """Isolated SQLite AuthStore in a temporary directory."""
    db_file = tmp_path / "test_login_auth.db"
    settings = Settings()
    return AuthStore(db_path=db_file, settings=settings)


@pytest.fixture(autouse=True)
def reset_login_rate_limits():
    """Reset in-memory IP rate limiter between test cases."""
    LoginService.reset_rate_limits()
    yield
    LoginService.reset_rate_limits()


@pytest.fixture
def registered_user(isolated_auth_store):
    """Seed a test registered user with known password."""
    password_service = PasswordService()
    pw_hash = password_service.hash_password("SuperSecurePassword#1234")
    ans_hash = password_service.hash_secret_answer("Springfield High")

    default_role = isolated_auth_store.get_default_role()
    assert default_role is not None

    questions = isolated_auth_store.get_active_secret_questions()
    assert len(questions) > 0

    user_info = isolated_auth_store.create_user_with_security(
        first_name="Jane",
        last_name="Doe",
        bi_email="jane.doe@company.com",
        role_id=default_role["roleId"],
        password_hash=pw_hash,
        secret_question_id=questions[0]["questionId"],
        secret_answer_hash=ans_hash,
        correlation_id=str(uuid.uuid4()),
    )
    return user_info


def test_login_success(isolated_auth_store, registered_user):
    """Scenario 1: Successful login with valid credentials."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    correlation_id = str(uuid.uuid4())
    payload = {
        "biEmail": "jane.doe@company.com",
        "password": "SuperSecurePassword#1234",
        "rememberMe": False,
    }

    response = client.post(
        "/api/v1/auth/login",
        json=payload,
        headers={"X-Correlation-ID": correlation_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["meta"]["correlationId"] == correlation_id

    # Verify user data
    user = data["data"]["user"]
    assert user["userId"] == registered_user["userId"]
    assert user["firstName"] == "Jane"
    assert user["lastName"] == "Doe"
    assert user["biEmail"] == "jane.doe@company.com"
    assert user["role"] == "REGULAR_USER"

    # Verify JWT data
    auth = data["data"]["authentication"]
    assert "accessToken" in auth
    assert auth["tokenType"] == "Bearer"
    assert auth["expiresIn"] == 900

    # Verify refresh_token cookie
    assert "refresh_token" in response.cookies
    cookie = response.cookies["refresh_token"]
    assert len(cookie) > 20

    # Verify database session created
    user_with_sec = isolated_auth_store.get_user_with_security_by_email("jane.doe@company.com")
    assert user_with_sec["lastLoginAt"] is not None
    assert user_with_sec["failedLoginAttempts"] == 0


def test_login_mixed_case_email(isolated_auth_store, registered_user):
    """Scenario 2: Successful login with mixed-case email."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    payload = {
        "biEmail": "JANE.DOE@Company.COM",
        "password": "SuperSecurePassword#1234",
        "rememberMe": True,
    }

    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["user"]["biEmail"] == "jane.doe@company.com"


def test_login_unknown_email(isolated_auth_store):
    """Scenario 3: Unknown email returns generic INVALID_CREDENTIALS."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    payload = {
        "biEmail": "nonexistent.user@company.com",
        "password": "AnyPassword123!",
    }

    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_CREDENTIALS"
    assert data["error"]["message"] == "The email address or password is incorrect."


def test_login_incorrect_password(isolated_auth_store, registered_user):
    """Scenario 4: Incorrect password returns INVALID_CREDENTIALS and increments counter."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    payload = {
        "biEmail": "jane.doe@company.com",
        "password": "WrongPassword#1234",
    }

    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_CREDENTIALS"

    user_sec = isolated_auth_store.get_user_with_security_by_email("jane.doe@company.com")
    assert user_sec["failedLoginAttempts"] == 1
    assert user_sec["isLocked"] == 0


def test_login_account_lockout_threshold(isolated_auth_store, registered_user):
    """Scenario 5 & 6: 5 failed attempts locks the account with 423 ACCOUNT_LOCKED."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    # 4 failed attempts
    for i in range(4):
        resp = client.post(
            "/api/v1/auth/login",
            json={"biEmail": "jane.doe@company.com", "password": f"WrongPw{i}"},
        )
        assert resp.status_code == 401

    user_sec = isolated_auth_store.get_user_with_security_by_email("jane.doe@company.com")
    assert user_sec["failedLoginAttempts"] == 4
    assert user_sec["isLocked"] == 0

    # 5th failed attempt -> lock threshold
    resp = client.post(
        "/api/v1/auth/login",
        json={"biEmail": "jane.doe@company.com", "password": "WrongPw5"},
    )
    assert resp.status_code == 423
    data = resp.json()
    assert data["error"]["code"] == "ACCOUNT_LOCKED"
    assert "temporarily locked" in data["error"]["message"].lower()

    # Verify locked in DB
    user_sec = isolated_auth_store.get_user_with_security_by_email("jane.doe@company.com")
    assert user_sec["isLocked"] == 1
    assert user_sec["lockExpiresAt"] is not None

    # Even with correct password, cannot log in while locked
    resp = client.post(
        "/api/v1/auth/login",
        json={"biEmail": "jane.doe@company.com", "password": "SuperSecurePassword#1234"},
    )
    assert resp.status_code == 423


def test_login_expired_lock_cleared(isolated_auth_store, registered_user):
    """Scenario 7: Expired lock is automatically cleared on subsequent valid login."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    # Set account as locked in the past
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    with isolated_auth_store._get_connection() as conn:
        conn.execute(
            """
            UPDATE user_security
            SET is_locked = 1, failed_login_attempts = 5, locked_at = ?, lock_expires_at = ?
            WHERE user_id = ?;
            """,
            (past_time, past_time, registered_user["userId"]),
        )
        conn.commit()

    # Now attempt login with correct credentials
    resp = client.post(
        "/api/v1/auth/login",
        json={"biEmail": "jane.doe@company.com", "password": "SuperSecurePassword#1234"},
    )
    assert resp.status_code == 200

    # Verify lock and failed attempts are cleared
    user_sec = isolated_auth_store.get_user_with_security_by_email("jane.doe@company.com")
    assert user_sec["isLocked"] == 0
    assert user_sec["failedLoginAttempts"] == 0
    assert user_sec["lockExpiresAt"] is None


def test_login_disabled_account(isolated_auth_store, registered_user):
    """Scenario 8: Disabled user receives 403 ACCOUNT_DISABLED."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    with isolated_auth_store._get_connection() as conn:
        conn.execute(
            "UPDATE users SET status = 'DISABLED' WHERE user_id = ?;",
            (registered_user["userId"],),
        )
        conn.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"biEmail": "jane.doe@company.com", "password": "SuperSecurePassword#1234"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_refresh_token_rotation_and_reuse_detection(isolated_auth_store, registered_user):
    """Scenario 9 & 10: Refresh rotates token; reuse of old token revokes token family."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    # 1. Login to get initial refresh token
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"biEmail": "jane.doe@company.com", "password": "SuperSecurePassword#1234"},
    )
    assert login_resp.status_code == 200
    first_cookie = login_resp.cookies["refresh_token"]

    # 2. Call refresh using the cookie
    client.cookies.set("refresh_token", first_cookie)
    refresh_resp = client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()
    assert "accessToken" in refresh_data["data"]["authentication"]

    second_cookie = refresh_resp.cookies["refresh_token"]
    assert second_cookie != first_cookie

    # 3. Reuse the old first_cookie -> Attack simulation!
    client.cookies.set("refresh_token", first_cookie)
    reuse_resp = client.post("/api/v1/auth/refresh")
    assert reuse_resp.status_code == 401
    assert reuse_resp.json()["error"]["code"] == "SESSION_REVOKED"

    # 4. Now the active second_cookie should ALSO be revoked because the entire family was invalidated!
    client.cookies.set("refresh_token", second_cookie)
    subsequent_resp = client.post("/api/v1/auth/refresh")
    assert subsequent_resp.status_code == 401


def test_get_current_user_and_logout(isolated_auth_store, registered_user):
    """Scenario 11 & 12: Test /api/v1/auth/me and /api/v1/auth/logout."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    # 1. Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"biEmail": "jane.doe@company.com", "password": "SuperSecurePassword#1234"},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["data"]["authentication"]["accessToken"]

    # 2. Call GET /me
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    user_data = me_resp.json()["data"]
    assert user_data["userId"] == registered_user["userId"]
    assert user_data["biEmail"] == "jane.doe@company.com"
    assert user_data["role"] == "REGULAR_USER"
    assert user_data["status"] == "ACTIVE"

    # 3. Call POST /logout
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 204

    # 4. Trying to refresh with the logged out cookie should fail
    refresh_resp = client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 401


def test_ip_rate_limiting(isolated_auth_store):
    """Scenario 13: 10 failed login attempts from same IP triggers 429 RATE_LIMIT_EXCEEDED."""
    app.state.auth_store = isolated_auth_store
    client = TestClient(app)

    # Make 10 requests
    for _ in range(10):
        client.post(
            "/api/v1/auth/login",
            json={"biEmail": "somebody@company.com", "password": "WrongPassword123!"},
        )

    # 11th request triggers 429
    resp = client.post(
        "/api/v1/auth/login",
        json={"biEmail": "somebody@company.com", "password": "WrongPassword123!"},
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in resp.headers
