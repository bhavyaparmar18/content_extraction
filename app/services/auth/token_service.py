"""Token service for JWT issuance and verification."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
import jwt

from app.config.settings import Settings


class TokenService:
    """Issues and validates JSON Web Tokens for authenticated sessions."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.expire_seconds = settings.jwt_access_token_expire_seconds
        self.issuer = settings.jwt_issuer
        self.audience = settings.jwt_audience

    def create_access_token(
        self,
        user_id: str,
        bi_email: str,
        role: str,
        expires_delta: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> tuple[str, int]:
        """Generate a signed JWT access token. Returns (token_str, expires_in_seconds)."""
        duration = expires_delta if expires_delta is not None else self.expire_seconds
        now = datetime.now(timezone.utc)
        exp = now + timedelta(seconds=duration)

        payload = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": str(user_id),
            "email": bi_email.lower(),
            "role": role,
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        if session_id:
            payload["sid"] = str(session_id)

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, duration

    def decode_access_token(self, token: str) -> dict[str, Any]:
        """Validate and decode a JWT access token."""
        return jwt.decode(
            token,
            self.secret_key,
            algorithms=[self.algorithm],
            issuer=self.issuer,
            audience=self.audience,
            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
        )
