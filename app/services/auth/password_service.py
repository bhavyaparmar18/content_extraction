"""Password and secret-answer hashing service using Argon2id."""

import re
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, VerificationError


class PasswordService:
    """Provides secure hashing and verification for passwords and recovery secret answers."""

    def __init__(self):
        # Argon2id parameters: RFC 9106 recommended defaults
        self._password_hasher = PasswordHasher(
            time_cost=2,
            memory_cost=19456,
            parallelism=1,
            hash_len=32,
            type=Type.ID,
        )
        # Independent hasher instance for secret answers
        self._answer_hasher = PasswordHasher(
            time_cost=2,
            memory_cost=19456,
            parallelism=1,
            hash_len=32,
            type=Type.ID,
        )

    def hash_password(self, password: str) -> str:
        """Hash a plaintext password using Argon2id."""
        return self._password_hasher.hash(password)

    def verify_password(self, password_hash: str, candidate_password: str) -> bool:
        """Verify candidate password against Argon2id hash."""
        try:
            return self._password_hasher.verify(password_hash, candidate_password)
        except (VerifyMismatchError, VerificationError):
            return False

    def normalize_secret_answer(self, answer: str) -> str:
        """Normalize secret answer for deterministic comparison (strip, lowercase, collapse whitespace)."""
        if not answer:
            return ""
        # Strip and convert to lowercase
        norm = answer.strip().lower()
        # Collapse multiple internal spaces to a single space
        norm = re.sub(r"\s+", " ", norm)
        return norm

    def hash_secret_answer(self, answer: str) -> str:
        """Normalize and hash secret answer using Argon2id."""
        normalized = self.normalize_secret_answer(answer)
        return self._answer_hasher.hash(normalized)

    def verify_secret_answer(self, answer_hash: str, candidate_answer: str) -> bool:
        """Verify candidate secret answer against normalized hash."""
        normalized = self.normalize_secret_answer(candidate_answer)
        try:
            return self._answer_hasher.verify(answer_hash, normalized)
        except (VerifyMismatchError, VerificationError):
            return False
