"""Pydantic schemas for authentication and signup."""

from typing import Optional
from pydantic import BaseModel, Field


# ── Meta ────────────────────────────────────────────────────────────────

class ApiMeta(BaseModel):
    """Metadata envelope for API responses."""
    correlationId: str


# ── Secret Questions ────────────────────────────────────────────────────

class SecretQuestionItem(BaseModel):
    """Single active secret question."""
    questionId: str
    questionText: str


class SecretQuestionsData(BaseModel):
    items: list[SecretQuestionItem] = Field(default_factory=list)


class SecretQuestionsResponse(BaseModel):
    success: bool = True
    data: SecretQuestionsData
    meta: ApiMeta


# ── Signup Request ──────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    """Payload submitted by user on signup."""
    firstName: str
    lastName: str
    biEmail: str
    password: str
    confirmPassword: str
    secretQuestionId: str
    secretAnswer: str

    model_config = {
        "extra": "forbid"  # Reject unknown or administrative properties
    }


# ── User & Auth Result ──────────────────────────────────────────────────

class AuthenticatedUser(BaseModel):
    """User summary returned after successful signup/auth."""
    userId: str
    firstName: str
    lastName: str
    biEmail: str
    role: str
    status: str
    emailVerified: bool = False


class AuthenticationResult(BaseModel):
    """JWT Token result."""
    accessToken: str
    tokenType: str = "Bearer"
    expiresIn: int = 900


class SignupSuccessData(BaseModel):
    user: AuthenticatedUser
    authentication: AuthenticationResult


class SignupSuccessResponse(BaseModel):
    success: bool = True
    message: str = "User registered successfully."
    data: SignupSuccessData
    meta: ApiMeta


# ── Login Schemas ───────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Payload submitted on login."""
    biEmail: str
    password: str
    rememberMe: bool = False

    model_config = {
        "extra": "forbid"
    }


class LoginUser(BaseModel):
    """Authenticated user info returned on login."""
    userId: str
    firstName: str
    lastName: str
    biEmail: str
    role: str


class LoginSuccessData(BaseModel):
    user: LoginUser
    authentication: AuthenticationResult


class LoginSuccessResponse(BaseModel):
    success: bool = True
    data: LoginSuccessData
    meta: ApiMeta


class CurrentUserData(BaseModel):
    userId: str
    firstName: str
    lastName: str
    biEmail: str
    role: str
    status: str
    emailVerified: bool = False


class CurrentUserResponse(BaseModel):
    success: bool = True
    data: CurrentUserData
    meta: Optional[ApiMeta] = None


# ── Error Contracts ─────────────────────────────────────────────────────

class ApiFieldError(BaseModel):
    """Field-specific validation error."""
    field: str
    code: str
    message: str


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    fieldErrors: Optional[list[ApiFieldError]] = None


class ApiErrorResponse(BaseModel):
    success: bool = False
    error: ApiErrorDetail
    meta: ApiMeta
