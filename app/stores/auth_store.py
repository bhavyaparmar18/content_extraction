"""Authentication SQLite Store — identity, credentials, roles, and audit persistence."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Any
from loguru import logger

from app.config.settings import Settings


class AuthStore:
    """Manages SQLite storage for authentication, user profiles, credentials, and audit events."""

    def __init__(self, db_path: Optional[Path] = None, settings: Optional[Settings] = None):
        if db_path is None:
            if settings:
                db_path = settings.auth_db_path or (settings.project_root / "data" / "auth.db")
            else:
                db_path = Path("data/auth.db")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        """Create tables, indexes, and seed initial roles and secret questions if needed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Roles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    role_id TEXT PRIMARY KEY,
                    role_code TEXT NOT NULL UNIQUE,
                    role_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # 2. Secret Questions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS secret_questions (
                    secret_question_id TEXT PRIMARY KEY,
                    question_code TEXT NOT NULL UNIQUE,
                    question_text TEXT NOT NULL UNIQUE,
                    display_order INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_secret_questions_active_order
                ON secret_questions (is_active, display_order, question_text);
            """)

            # 3. Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    bi_email TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    is_email_verified INTEGER NOT NULL DEFAULT 0,
                    email_verified_at TEXT,
                    last_login_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deactivated_at TEXT,
                    FOREIGN KEY (role_id) REFERENCES roles(role_id)
                );
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_users_bi_email_ci
                ON users (lower(bi_email));
            """)

            # 4. User Security table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_security (
                    user_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    secret_question_id TEXT NOT NULL,
                    secret_answer_hash TEXT NOT NULL,
                    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                    is_locked INTEGER NOT NULL DEFAULT 0,
                    locked_at TEXT,
                    lock_expires_at TEXT,
                    lock_reason TEXT,
                    password_changed_at TEXT NOT NULL,
                    secret_answer_changed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (secret_question_id) REFERENCES secret_questions(secret_question_id)
                );
            """)

            # Safe migration: ensure lock_expires_at column exists for existing databases
            try:
                cursor.execute("ALTER TABLE user_security ADD COLUMN lock_expires_at TEXT;")
            except sqlite3.OperationalError:
                pass

            # 5. User Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    refresh_token_hash TEXT NOT NULL UNIQUE,
                    token_family_id TEXT NOT NULL,
                    remember_me INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT,
                    revoked_reason TEXT,
                    replaced_by_session_id TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (replaced_by_session_id) REFERENCES user_sessions(session_id)
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_user_sessions_user_active
                ON user_sessions (user_id, expires_at)
                WHERE revoked_at IS NULL;
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_user_sessions_token_family
                ON user_sessions (token_family_id);
            """)

            # 6. Audit Events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_event_id TEXT PRIMARY KEY,
                    actor_user_id TEXT,
                    event_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT,
                    resource_id TEXT,
                    outcome TEXT NOT NULL,
                    error_code TEXT,
                    correlation_id TEXT NOT NULL,
                    event_details TEXT NOT NULL DEFAULT '{}',
                    ip_address TEXT,
                    user_agent TEXT,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY (actor_user_id) REFERENCES users(user_id) ON DELETE SET NULL
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_audit_events_correlation_id
                ON audit_events (correlation_id);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS ix_audit_events_actor_time
                ON audit_events (actor_user_id, occurred_at DESC);
            """)

            # 6. Seed initial roles
            now_str = datetime.now(timezone.utc).isoformat()
            roles_to_seed = [
                (str(uuid.uuid4()), "ADMIN", "Administrator", "Full application and administrative access.", 0, 1, now_str, now_str),
                (str(uuid.uuid4()), "POWER_USER", "Power User", "Broad operational access without protected delete permissions.", 0, 1, now_str, now_str),
                (str(uuid.uuid4()), "REGULAR_USER", "Regular User", "Standard access to permitted and owned resources.", 1, 1, now_str, now_str),
            ]
            for r in roles_to_seed:
                cursor.execute("""
                    INSERT OR IGNORE INTO roles (role_id, role_code, role_name, description, is_default, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, r)

            # 7. Seed initial secret questions
            questions_to_seed = [
                (str(uuid.uuid4()), "FIRST_SCHOOL", "What was the name of your first school?", 10, 1, now_str, now_str),
                (str(uuid.uuid4()), "CHILDHOOD_NICKNAME", "What was your childhood nickname?", 20, 1, now_str, now_str),
                (str(uuid.uuid4()), "FIRST_PET", "What was the name of your first pet?", 30, 1, now_str, now_str),
                (str(uuid.uuid4()), "BIRTH_CITY", "In which city were you born?", 40, 1, now_str, now_str),
                (str(uuid.uuid4()), "FAVORITE_TEACHER", "What was the surname of your favorite teacher?", 50, 1, now_str, now_str),
            ]
            for q in questions_to_seed:
                cursor.execute("""
                    INSERT OR IGNORE INTO secret_questions (secret_question_id, question_code, question_text, display_order, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, q)

            conn.commit()

    def get_active_secret_questions(self) -> list[dict[str, Any]]:
        """Retrieve all active secret questions sorted by display order and question text."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT secret_question_id AS questionId, question_text AS questionText
                FROM secret_questions
                WHERE is_active = 1
                ORDER BY display_order ASC, question_text ASC;
            """)
            rows = cursor.fetchall()
            return [{"questionId": row["questionId"], "questionText": row["questionText"]} for row in rows]

    def get_secret_question_by_id(self, question_id: str) -> Optional[dict[str, Any]]:
        """Fetch a secret question by its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT secret_question_id AS questionId, question_code AS questionCode, question_text AS questionText, is_active AS isActive
                FROM secret_questions
                WHERE secret_question_id = ?;
            """, (question_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_default_role(self) -> Optional[dict[str, Any]]:
        """Fetch the active default role (usually REGULAR_USER)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role_id AS roleId, role_code AS roleCode, role_name AS roleName, is_default AS isDefault, is_active AS isActive
                FROM roles
                WHERE is_default = 1 AND is_active = 1
                LIMIT 1;
            """)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        """Retrieve user record by email (case-insensitive)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.user_id AS userId, u.first_name AS firstName, u.last_name AS lastName,
                       u.bi_email AS biEmail, u.role_id AS roleId, r.role_code AS role,
                       u.status, u.is_email_verified AS emailVerified, u.created_at AS createdAt
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                WHERE lower(u.bi_email) = lower(?);
            """, (email.strip(),))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def create_user_with_security(
        self,
        first_name: str,
        last_name: str,
        bi_email: str,
        role_id: str,
        password_hash: str,
        secret_question_id: str,
        secret_answer_hash: str,
        correlation_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "ACTIVE",
    ) -> dict[str, Any]:
        """Atomically create user, user_security, and audit_event records."""
        user_id = str(uuid.uuid4())
        audit_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        normalized_email = bi_email.strip().lower()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Insert user
            cursor.execute("""
                INSERT INTO users (
                    user_id, first_name, last_name, bi_email, role_id, status,
                    is_email_verified, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?);
            """, (
                user_id, first_name.strip(), last_name.strip(), normalized_email,
                role_id, status, now_str, now_str
            ))

            # Insert user_security
            cursor.execute("""
                INSERT INTO user_security (
                    user_id, password_hash, secret_question_id, secret_answer_hash,
                    failed_login_attempts, is_locked, password_changed_at,
                    secret_answer_changed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?);
            """, (
                user_id, password_hash, secret_question_id, secret_answer_hash,
                now_str, now_str, now_str, now_str
            ))

            # Insert audit_event (SUCCESS)
            event_details = json.dumps({
                "eventType": "IDENTITY",
                "action": "USER_SIGNUP",
                "resourceType": "USER",
                "outcome": "SUCCESS"
            })
            cursor.execute("""
                INSERT INTO audit_events (
                    audit_event_id, actor_user_id, event_type, action,
                    resource_type, resource_id, outcome, correlation_id,
                    event_details, ip_address, user_agent, occurred_at
                ) VALUES (?, ?, 'IDENTITY', 'USER_SIGNUP', 'USER', ?, 'SUCCESS', ?, ?, ?, ?, ?);
            """, (
                audit_id, user_id, user_id, correlation_id,
                event_details, ip_address, user_agent, now_str
            ))

            conn.commit()

        return {
            "userId": user_id,
            "firstName": first_name.strip(),
            "lastName": last_name.strip(),
            "biEmail": normalized_email,
            "status": status,
            "emailVerified": False,
            "createdAt": now_str,
        }

    def record_audit_event(
        self,
        event_type: str,
        action: str,
        outcome: str,
        correlation_id: str,
        actor_user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        error_code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Record an independent audit event."""
        try:
            audit_id = str(uuid.uuid4())
            now_str = datetime.now(timezone.utc).isoformat()
            event_details = json.dumps(details or {})

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_events (
                        audit_event_id, actor_user_id, event_type, action,
                        resource_type, resource_id, outcome, error_code,
                        correlation_id, event_details, ip_address, user_agent, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    audit_id, actor_user_id, event_type, action,
                    resource_type, resource_id, outcome, error_code,
                    correlation_id, event_details, ip_address, user_agent, now_str
                ))
                conn.commit()
        except Exception as exc:
            logger.error(f"Failed to record audit event: {exc}")

    def get_user_with_security_by_email(self, email: str) -> Optional[dict[str, Any]]:
        """Retrieve user, role, and security record by case-insensitive bi_email."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    u.user_id AS userId,
                    u.first_name AS firstName,
                    u.last_name AS lastName,
                    u.bi_email AS biEmail,
                    u.status AS status,
                    u.is_email_verified AS emailVerified,
                    u.last_login_at AS lastLoginAt,
                    r.role_id AS roleId,
                    r.role_code AS role,
                    r.is_active AS roleIsActive,
                    us.password_hash AS passwordHash,
                    us.failed_login_attempts AS failedLoginAttempts,
                    us.is_locked AS isLocked,
                    us.locked_at AS lockedAt,
                    us.lock_expires_at AS lockExpiresAt,
                    us.lock_reason AS lockReason
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                JOIN user_security us ON us.user_id = u.user_id
                WHERE lower(u.bi_email) = lower(?)
                LIMIT 1;
            """, (email.strip(),))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_user_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        """Retrieve user profile and role by user_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    u.user_id AS userId,
                    u.first_name AS firstName,
                    u.last_name AS lastName,
                    u.bi_email AS biEmail,
                    u.status AS status,
                    u.is_email_verified AS emailVerified,
                    u.last_login_at AS lastLoginAt,
                    r.role_code AS role,
                    r.is_active AS roleIsActive
                FROM users u
                JOIN roles r ON u.role_id = r.role_id
                WHERE u.user_id = ?
                LIMIT 1;
            """, (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def clear_expired_lock(self, user_id: str) -> bool:
        """Clear temporary lock atomically if lock_expires_at has passed."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_security
                SET
                    is_locked = 0,
                    failed_login_attempts = 0,
                    locked_at = NULL,
                    lock_expires_at = NULL,
                    lock_reason = NULL,
                    updated_at = ?
                WHERE user_id = ?
                  AND is_locked = 1
                  AND lock_expires_at IS NOT NULL
                  AND lock_expires_at <= ?;
            """, (now_str, user_id, now_str))
            conn.commit()
            return cursor.rowcount > 0

    def record_failed_login(
        self,
        user_id: str,
        max_failed_attempts: int = 5,
        lock_minutes: int = 15,
    ) -> dict[str, Any]:
        """Atomically increment failed_login_attempts and apply temporary lock if threshold is reached."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        lock_expires_at = (now + timedelta(minutes=lock_minutes)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT failed_login_attempts, is_locked, lock_expires_at
                FROM user_security
                WHERE user_id = ?;
            """, (user_id,))
            row = cursor.fetchone()
            if not row:
                return {"failedLoginAttempts": 0, "isLocked": False, "newlyLocked": False, "lockExpiresAt": None}

            current_attempts = row["failed_login_attempts"] + 1
            will_lock = current_attempts >= max_failed_attempts

            if will_lock:
                cursor.execute("""
                    UPDATE user_security
                    SET
                        failed_login_attempts = ?,
                        is_locked = 1,
                        locked_at = ?,
                        lock_expires_at = ?,
                        lock_reason = 'FAILED_LOGIN_THRESHOLD',
                        updated_at = ?
                    WHERE user_id = ?;
                """, (current_attempts, now_str, lock_expires_at, now_str, user_id))
            else:
                cursor.execute("""
                    UPDATE user_security
                    SET
                        failed_login_attempts = ?,
                        updated_at = ?
                    WHERE user_id = ?;
                """, (current_attempts, now_str, user_id))

            conn.commit()
            return {
                "failedLoginAttempts": current_attempts,
                "isLocked": will_lock or bool(row["is_locked"]),
                "newlyLocked": will_lock and not bool(row["is_locked"]),
                "lockExpiresAt": lock_expires_at if will_lock else row["lock_expires_at"],
            }

    def reset_failed_attempts_and_update_login(self, user_id: str) -> None:
        """Reset failed attempts/lock and update last_login_at on successful authentication."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_security
                SET
                    failed_login_attempts = 0,
                    is_locked = 0,
                    locked_at = NULL,
                    lock_expires_at = NULL,
                    lock_reason = NULL,
                    updated_at = ?
                WHERE user_id = ?;
            """, (now_str, user_id))
            cursor.execute("""
                UPDATE users
                SET
                    last_login_at = ?,
                    updated_at = ?
                WHERE user_id = ?;
            """, (now_str, now_str, user_id))
            conn.commit()

    def create_session(
        self,
        session_id: str,
        user_id: str,
        refresh_token_hash: str,
        token_family_id: str,
        remember_me: bool,
        expires_at: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Insert a new refresh token session."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_sessions (
                    session_id, user_id, refresh_token_hash, token_family_id,
                    remember_me, expires_at, ip_address, user_agent, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                session_id, user_id, refresh_token_hash, token_family_id,
                1 if remember_me else 0, expires_at, ip_address, user_agent, now_str
            ))
            conn.commit()

    def get_session_by_token_hash(self, refresh_token_hash: str) -> Optional[dict[str, Any]]:
        """Retrieve active or revoked session by refresh token hash with user and role details."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    s.session_id AS sessionId,
                    s.user_id AS userId,
                    s.token_family_id AS tokenFamilyId,
                    s.remember_me AS rememberMe,
                    s.expires_at AS expiresAt,
                    s.revoked_at AS revokedAt,
                    s.revoked_reason AS revokedReason,
                    s.replaced_by_session_id AS replacedBySessionId,
                    u.bi_email AS biEmail,
                    u.first_name AS firstName,
                    u.last_name AS lastName,
                    u.status AS userStatus,
                    r.role_code AS role,
                    r.is_active AS roleIsActive
                FROM user_sessions s
                JOIN users u ON u.user_id = s.user_id
                JOIN roles r ON r.role_id = u.role_id
                WHERE s.refresh_token_hash = ?
                LIMIT 1;
            """, (refresh_token_hash,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def rotate_session(
        self,
        old_session_id: str,
        new_session_id: str,
        user_id: str,
        new_refresh_token_hash: str,
        token_family_id: str,
        remember_me: bool,
        new_expires_at: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Atomically revoke old session and create a replacement session in the same token family."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Insert new replacement session first so that foreign key references exist
            cursor.execute("""
                INSERT INTO user_sessions (
                    session_id, user_id, refresh_token_hash, token_family_id,
                    remember_me, expires_at, ip_address, user_agent, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                new_session_id, user_id, new_refresh_token_hash, token_family_id,
                1 if remember_me else 0, new_expires_at, ip_address, user_agent, now_str
            ))
            # 2. Revoke old session and link to replacement session
            cursor.execute("""
                UPDATE user_sessions
                SET
                    revoked_at = ?,
                    revoked_reason = 'ROTATED',
                    last_used_at = ?,
                    replaced_by_session_id = ?
                WHERE session_id = ?
                  AND revoked_at IS NULL;
            """, (now_str, now_str, new_session_id, old_session_id))
            conn.commit()

    def revoke_token_family(self, token_family_id: str, reason: str = "REUSE_DETECTED") -> int:
        """Revoke all active sessions belonging to a compromised token family."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_sessions
                SET
                    revoked_at = ?,
                    revoked_reason = ?
                WHERE token_family_id = ?
                  AND revoked_at IS NULL;
            """, (now_str, reason, token_family_id))
            conn.commit()
            return cursor.rowcount

    def revoke_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        reason: str = "USER_LOGOUT"
    ) -> bool:
        """Revoke a specific active session."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("""
                    UPDATE user_sessions
                    SET
                        revoked_at = ?,
                        revoked_reason = ?
                    WHERE session_id = ?
                      AND user_id = ?
                      AND revoked_at IS NULL;
                """, (now_str, reason, session_id, user_id))
            else:
                cursor.execute("""
                    UPDATE user_sessions
                    SET
                        revoked_at = ?,
                        revoked_reason = ?
                    WHERE session_id = ?
                      AND revoked_at IS NULL;
                """, (now_str, reason, session_id))
            conn.commit()
            return cursor.rowcount > 0
