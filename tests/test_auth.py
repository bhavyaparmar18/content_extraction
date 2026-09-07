"""Unit and integration tests for authentication and signup."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config.settings import Settings
from app.stores.auth_store import AuthStore
from app.services.auth import PasswordService, TokenService


@pytest.fixture
def test_auth_store(tmp_path):
    """Isolated SQLite AuthStore in a temporary directory."""
    db_file = tmp_path / "test_auth.db"
    return AuthStore(db_path=db_file)


def test_secret_questions_endpoint():
    """Test GET /api/v1/auth/secret-questions."""
    client = TestClient(app)
    response = client.get("/api/v1/auth/secret-questions")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    items = data["data"]["items"]
    assert len(items) >= 5
    assert all("questionId" in q and "questionText" in q for q in items)
    assert "meta" in data
    assert "correlationId" in data["meta"]


def test_signup_success_flow(test_auth_store, monkeypatch):
    """Test successful user registration flow."""
    # Seed question
    questions = test_auth_store.get_active_secret_questions()
    assert len(questions) > 0
    question_id = questions[0]["questionId"]

    # Use test client
    client = TestClient(app)
    app.state.auth_store = test_auth_store

    correlation_id = str(uuid.uuid4())
    signup_payload = {
        "firstName": "Alice",
        "lastName": "Smith",
        "biEmail": "alice.smith@example.com",
        "password": "SuperSecurePassword#1234",
        "confirmPassword": "SuperSecurePassword#1234",
        "secretQuestionId": question_id,
        "secretAnswer": "Blue Dragon School",
    }

    response = client.post(
        "/api/v1/auth/signup",
        json=signup_payload,
        headers={"X-Correlation-ID": correlation_id},
    )

    assert response.status_code == 201
    resp_json = response.json()
    assert resp_json["success"] is True
    assert resp_json["message"] == "User registered successfully."

    # Validate User Data
    user_data = resp_json["data"]["user"]
    assert user_data["firstName"] == "Alice"
    assert user_data["lastName"] == "Smith"
    assert user_data["biEmail"] == "alice.smith@example.com"
    assert user_data["role"] == "REGULAR_USER"
    assert user_data["status"] == "ACTIVE"
    assert user_data["emailVerified"] is False

    # Validate Authentication Tokens
    auth_data = resp_json["data"]["authentication"]
    assert "accessToken" in auth_data
    assert auth_data["tokenType"] == "Bearer"
    assert auth_data["expiresIn"] == 900

    # Validate JWT Decodes correctly
    settings = Settings()
    token_service = TokenService(settings)
    decoded = token_service.decode_access_token(auth_data["accessToken"])
    assert decoded["sub"] == user_data["userId"]
    assert decoded["email"] == "alice.smith@example.com"
    assert decoded["role"] == "REGULAR_USER"

    # Validate Database Record & Password Hashing
    db_user = test_auth_store.get_user_by_email("alice.smith@example.com")
    assert db_user is not None
    assert db_user["userId"] == user_data["userId"]


def test_signup_validation_errors():
    """Test validation errors for invalid payload."""
    client = TestClient(app)

    # 1. Password too short & passwords don't match
    payload = {
        "firstName": "Bob",
        "lastName": "Jones",
        "biEmail": "bob@example.com",
        "password": "short",
        "confirmPassword": "different",
        "secretQuestionId": str(uuid.uuid4()),
        "secretAnswer": "a",
    }
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"
    field_errors = {fe["field"]: fe["code"] for fe in data["error"]["fieldErrors"]}
    assert "password" in field_errors
    assert "confirmPassword" in field_errors
    assert "secretAnswer" in field_errors


def test_signup_password_equals_email():
    """Test that password matching email is rejected."""
    client = TestClient(app)
    payload = {
        "firstName": "Charlie",
        "lastName": "Brown",
        "biEmail": "charlie.brown@company.com",
        "password": "charlie.brown@company.com",
        "confirmPassword": "charlie.brown@company.com",
        "secretQuestionId": str(uuid.uuid4()),
        "secretAnswer": "Valid Answer",
    }
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 422
    data = response.json()
    field_errors = {fe["field"]: fe["code"] for fe in data["error"]["fieldErrors"]}
    assert "password" in field_errors
    assert field_errors["password"] == "PASSWORD_EQUALS_EMAIL"


def test_signup_duplicate_email(test_auth_store):
    """Test 409 conflict when email is already registered."""
    app.state.auth_store = test_auth_store
    client = TestClient(app)

    questions = test_auth_store.get_active_secret_questions()
    question_id = questions[0]["questionId"]

    payload = {
        "firstName": "David",
        "lastName": "Miller",
        "biEmail": "david.miller@company.com",
        "password": "ComplexPassword@9876",
        "confirmPassword": "ComplexPassword@9876",
        "secretQuestionId": question_id,
        "secretAnswer": "Favorite Cat",
    }

    # First registration
    r1 = client.post("/api/v1/auth/signup", json=payload)
    assert r1.status_code == 201

    # Second registration with same email (case variation)
    payload_dup = dict(payload)
    payload_dup["biEmail"] = "DAVID.MILLER@company.com"
    r2 = client.post("/api/v1/auth/signup", json=payload_dup)
    assert r2.status_code == 409
    data = r2.json()
    assert data["success"] is False
    assert data["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_password_service_argon2id():
    """Test Argon2id hashing and verification."""
    ps = PasswordService()
    raw = "MySecretP@ssw0rd!"
    hashed = ps.hash_password(raw)
    assert hashed.startswith("$argon2id$")
    assert ps.verify_password(hashed, raw) is True
    assert ps.verify_password(hashed, "wrong") is False

    ans_hashed = ps.hash_secret_answer("  My Childhood Nickname  ")
    assert ps.verify_secret_answer(ans_hashed, "my childhood nickname") is True
    assert ps.verify_secret_answer(ans_hashed, "MY CHILDHOOD NICKNAME") is True
