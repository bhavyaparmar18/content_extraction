# Login Page API and Frontend Development Specification

**Document Type:** Frontend, API, Security, and Database Specification  
**Module:** Authentication and Session Management  
**Frontend:** React, TypeScript, Tailwind CSS  
**Backend API Base Path:** `/api/v1/auth`  
**Database:** PostgreSQL  
**Authentication:** Short-lived JWT access token and rotating refresh token  
**Version:** 1.1  
**Status:** Development Reference

---

## 1. Purpose

This specification defines the complete login-page implementation contract for frontend, backend, database, QA, and security teams.

The login flow must:

1. Accept the user's BI email and password.
2. Validate the request without exposing whether an email is registered.
3. retrieve the user, role, and security record.
4. check user, role, and account-lock status.
5. verify the submitted password against the stored password hash.
6. track failed login attempts and apply temporary account locking.
7. create an authenticated session after successful verification.
8. issue a short-lived JWT access token.
9. set a rotating refresh token in a secure `HttpOnly` cookie.
10. update login metadata and create audit events.
11. restore and clear authentication state correctly in the React application.

---

## 2. Scope

### Included

- Login page fields and behavior.
- Login API contract.
- User and password lookup queries.
- Password verification behavior.
- Failed-attempt and account-lock flow.
- JWT access-token generation.
- Refresh-token session storage and rotation.
- Current-user, refresh, and logout APIs.
- React and TypeScript mapping.
- Tailwind CSS and accessibility requirements.
- Audit events, error handling, and test scenarios.

### Not Included

- Signup implementation.
- Forgot-password implementation.
- Secret-question verification flow.
- Multi-factor authentication.
- SSO or enterprise identity federation.
- Administrative account-unlock API.

---

## 3. Login Page Requirements

### 3.1 Fields

| UI Label | API Field | Control | Required | Rules |
|---|---|---|---:|---|
| BI Email | `biEmail` | Email input | Yes | Trim and lowercase before sending |
| Password | `password` | Password input | Yes | Do not trim, transform, log, or persist |
| Remember Me | `rememberMe` | Checkbox | No | Default `false`; controls refresh-session lifetime only |

### 3.2 Links

- **Forgot password** navigates to `/forgot-password`.
- **Create account** navigates to `/signup`.
- A locked-account message may direct the user to password recovery or support.

### 3.3 UI states

The page must support:

- Initial state.
- Client-validation errors.
- Request in progress.
- Invalid credentials.
- Account locked.
- Account disabled.
- Rate limit exceeded.
- Server or network error.
- Successful login and redirect.

---

## 4. Required Database Entities

The login flow reads from the existing `users`, `roles`, and `user_security` tables and writes to `audit_events`. It also requires a `user_sessions` table for refresh-token management.

### 4.1 User Sessions Table

```sql
CREATE TABLE user_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    refresh_token_hash TEXT NOT NULL,
    token_family_id UUID NOT NULL,
    remember_me BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    revoked_reason VARCHAR(100),
    replaced_by_session_id UUID,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_user_sessions_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_user_sessions_replacement
        FOREIGN KEY (replaced_by_session_id)
        REFERENCES user_sessions(session_id)
);
```

```sql
CREATE UNIQUE INDEX uq_user_sessions_refresh_token_hash
    ON user_sessions (refresh_token_hash);

CREATE INDEX ix_user_sessions_user_active
    ON user_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX ix_user_sessions_token_family
    ON user_sessions (token_family_id);
```

### 4.2 Optional temporary-lock expiry

If temporary account locking is required, add this column to `user_security`:

```sql
ALTER TABLE user_security
ADD COLUMN lock_expires_at TIMESTAMPTZ;
```

The application must use one canonical lock state. In this specification, `user_security.is_locked`, `locked_at`, and `lock_expires_at` are authoritative. The `users.status` field represents broader account lifecycle state such as `ACTIVE` or `DISABLED`.

---

## 5. Login API

### 5.1 Endpoint

```http
POST /api/v1/auth/login
```

### 5.2 Authentication

No JWT is required. This public endpoint must use HTTPS, rate limiting, request-size limits, and abuse monitoring.

### 5.3 Request Headers

```http
Content-Type: application/json
Accept: application/json
X-Correlation-ID: <optional-uuid>
```

The server generates a correlation ID if the client does not provide one.

### 5.4 Request Body

```json
{
  "biEmail": "john.doe@company.com",
  "password": "Password@123",
  "rememberMe": false
}
```

### 5.5 Request Validation

**BI email**

- Required string.
- Valid email format.
- Maximum 320 characters.
- Trim leading and trailing whitespace.
- Normalize to lowercase before lookup.

**Password**

- Required string.
- Maximum 128 characters or the centrally configured password limit.
- Do not trim, normalize, transform, log, or store the submitted value.

**Remember me**

- Optional Boolean.
- Defaults to `false`.
- Must affect only the refresh-session duration, not the access-token lifetime.

Unknown request properties should be rejected with a validation error.

---

## 6. Complete Backend Login Flow

### Step 1: Validate and normalize the request

```text
Input email:  John.Doe@Company.com
Stored lookup: john.doe@company.com
```

The password must remain byte-for-byte equivalent to the submitted value.

### Step 2: Apply rate limits

Apply limits by IP address and normalized email. Rate limiting is separate from account locking so an attacker cannot easily lock an account by repeatedly submitting its email.

Recommended configurable starting values:

```text
Per IP:     10 attempts per 15 minutes
Per email:   5 failed attempts before temporary lock
Lock time:  15 minutes
```

### Step 3: Retrieve the user and security data

Use one parameterized query:

```sql
SELECT
    u.user_id,
    u.first_name,
    u.last_name,
    u.bi_email,
    u.status,
    u.is_email_verified,
    u.last_login_at,
    r.role_id,
    r.role_code,
    r.is_active AS role_is_active,
    us.password_hash,
    us.failed_login_attempts,
    us.is_locked,
    us.locked_at,
    us.lock_expires_at
FROM users u
INNER JOIN roles r
    ON r.role_id = u.role_id
INNER JOIN user_security us
    ON us.user_id = u.user_id
WHERE lower(u.bi_email) = lower(:bi_email)
LIMIT 1;
```

The query returns no row when the email is unknown. The API must not tell the caller whether the email exists.

### Step 4: Handle an unknown email safely

When no user is found:

1. Perform a verification operation against a pre-generated dummy Argon2id hash.
2. create a failed-login audit event without a user ID.
3. return the same `INVALID_CREDENTIALS` response used for an incorrect password.

The dummy verification reduces observable timing differences between an unknown email and an incorrect password.

### Step 5: Check account and role status

Before accepting the password, evaluate:

```text
users.status == ACTIVE
roles.is_active == true
user_security.is_locked == false
```

If email verification becomes mandatory, also require:

```text
users.is_email_verified == true
```

Account behavior:

- `DISABLED`: reject login.
- Inactive role: reject login.
- Active temporary lock: reject login.
- Expired temporary lock: clear the lock atomically and continue.

### Step 6: Clear an expired temporary lock

```sql
UPDATE user_security
SET
    is_locked = FALSE,
    failed_login_attempts = 0,
    locked_at = NULL,
    lock_expires_at = NULL,
    lock_reason = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = :user_id
  AND is_locked = TRUE
  AND lock_expires_at IS NOT NULL
  AND lock_expires_at <= CURRENT_TIMESTAMP;
```

After this query, use the returned/updated state or re-read under the transaction. Do not clear administrative or indefinite locks where `lock_expires_at` is `NULL`.

### Step 7: Verify the password

Passwords are never queried by plaintext comparison. The application retrieves `password_hash` and calls the Argon2id library's verify function.

Conceptual backend logic:

```python
password_is_valid = password_hasher.verify(
    stored_password_hash,
    submitted_password
)
```

Do not use SQL like this:

```sql
-- Never do this
SELECT * FROM user_security
WHERE password_hash = :submitted_password;
```

The stored encoded Argon2id hash contains the algorithm parameters and salt required by the verification library.

### Step 8: Handle an invalid password

Increment failed attempts atomically and determine whether the threshold has been reached.

```sql
UPDATE user_security
SET
    failed_login_attempts = failed_login_attempts + 1,
    is_locked = CASE
        WHEN failed_login_attempts + 1 >= :max_failed_attempts THEN TRUE
        ELSE is_locked
    END,
    locked_at = CASE
        WHEN failed_login_attempts + 1 >= :max_failed_attempts
            THEN CURRENT_TIMESTAMP
        ELSE locked_at
    END,
    lock_expires_at = CASE
        WHEN failed_login_attempts + 1 >= :max_failed_attempts
            THEN CURRENT_TIMESTAMP + (:lock_minutes * INTERVAL '1 minute')
        ELSE lock_expires_at
    END,
    lock_reason = CASE
        WHEN failed_login_attempts + 1 >= :max_failed_attempts
            THEN 'FAILED_LOGIN_THRESHOLD'
        ELSE lock_reason
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = :user_id
RETURNING
    failed_login_attempts,
    is_locked,
    lock_expires_at;
```

Then:

1. Write `LOGIN_FAILED` to `audit_events`.
2. If the account became locked, also write `ACCOUNT_LOCKED`.
3. return `401 INVALID_CREDENTIALS`, or the approved generic locked response.

The response should not reveal the number of remaining attempts unless approved by security.

### Step 9: Handle a valid password

After successful verification:

1. Optionally rehash the password if Argon2id parameters are outdated.
2. reset failed attempts and temporary lock fields.
3. update `last_login_at`.
4. generate a cryptographically secure refresh token.
5. hash the refresh token before database storage.
6. create the `user_sessions` record.
7. create a `LOGIN_SUCCEEDED` audit event.
8. commit the transaction.
9. generate the access JWT.
10. set the raw refresh token in a secure cookie.

### Step 10: Reset security state

```sql
UPDATE user_security
SET
    failed_login_attempts = 0,
    is_locked = FALSE,
    locked_at = NULL,
    lock_expires_at = NULL,
    lock_reason = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = :user_id;
```

### Step 11: Update login timestamp

```sql
UPDATE users
SET
    last_login_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = :user_id;
```

### Step 12: Create the session

Generate these values in the application:

```text
raw_refresh_token  = secure random value
refresh_token_hash = one-way hash of raw token
token_family_id    = new UUID
session_id         = new UUID
```

Set expiry according to `rememberMe`:

```text
rememberMe = false → recommended 24-hour refresh session
rememberMe = true  → recommended 30-day refresh session
```

These durations must be configurable.

```sql
INSERT INTO user_sessions (
    session_id,
    user_id,
    refresh_token_hash,
    token_family_id,
    remember_me,
    expires_at,
    ip_address,
    user_agent
)
VALUES (
    :session_id,
    :user_id,
    :refresh_token_hash,
    :token_family_id,
    :remember_me,
    :expires_at,
    :ip_address,
    :user_agent
);
```

### Step 13: Create the success audit event

```sql
INSERT INTO audit_events (
    actor_user_id,
    event_type,
    action,
    resource_type,
    resource_id,
    outcome,
    correlation_id,
    event_details,
    ip_address,
    user_agent
)
VALUES (
    :user_id,
    'AUTHENTICATION',
    'LOGIN_SUCCEEDED',
    'USER',
    :user_id,
    'SUCCESS',
    :correlation_id,
    jsonb_build_object('sessionId', :session_id),
    :ip_address,
    :user_agent
);
```

### Step 14: Transaction boundary

The successful login database operations should be atomic:

```text
BEGIN
  reset failed-attempt state
  update last_login_at
  insert refresh-token session
  insert success audit event
COMMIT

generate JWT response
set refresh cookie
```

If session creation fails, do not return a successful login response.

---

## 7. Successful Login Response

**Status:** `200 OK`

```json
{
  "success": true,
  "data": {
    "user": {
      "userId": "fc60cb42-17dc-4c74-b127-1d734fc6110d",
      "firstName": "John",
      "lastName": "Doe",
      "biEmail": "john.doe@company.com",
      "role": "REGULAR_USER"
    },
    "authentication": {
      "accessToken": "<signed-jwt-access-token>",
      "tokenType": "Bearer",
      "expiresIn": 900
    }
  },
  "meta": {
    "correlationId": "51f62a7c-8242-4a57-954c-9ac5b8535df0"
  }
}
```

### Refresh Cookie

```http
Set-Cookie: refresh_token=<opaque-token>; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth; Max-Age=<configured-seconds>
```

Use `SameSite=Strict` where the deployment and navigation flow permit it. If cross-site cookies are required, use `SameSite=None; Secure` and implement appropriate CSRF protection.

---

## 8. JWT Access Token

### Required Claims

```json
{
  "iss": "governance-sop-api",
  "aud": "governance-sop-web",
  "sub": "fc60cb42-17dc-4c74-b127-1d734fc6110d",
  "email": "john.doe@company.com",
  "role": "REGULAR_USER",
  "sid": "295c1b94-04b1-49f3-b210-6237900f075c",
  "jti": "595094f6-d177-4ac7-9139-e46ab654062e",
  "iat": 1785826800,
  "nbf": 1785826800,
  "exp": 1785827700
}
```

### Token Rules

- Recommended access-token lifetime: 15 minutes.
- Use approved asymmetric signing such as RS256 or ES256.
- Do not include passwords, hashes, secret-question information, or unnecessary personal data.
- Protected APIs must verify signature, issuer, audience, expiry, not-before, and required claims.
- The backend must still enforce role and resource-level authorization.

---

## 9. Error Responses

### 9.1 Standard Error Shape

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Safe user-facing message.",
    "fieldErrors": []
  },
  "meta": {
    "correlationId": "51f62a7c-8242-4a57-954c-9ac5b8535df0"
  }
}
```

### 9.2 Error Summary

| Status | Code | UI Behavior |
|---:|---|---|
| `400` | `INVALID_REQUEST` | Show general request error |
| `401` | `INVALID_CREDENTIALS` | Show general email/password error |
| `403` | `ACCOUNT_DISABLED` | Show contact-support message |
| `423` | `ACCOUNT_LOCKED` | Show locked message and recovery link |
| `429` | `RATE_LIMIT_EXCEEDED` | Temporarily disable retry |
| `500` | `INTERNAL_SERVER_ERROR` | Show retry message |

### Invalid Credentials

```json
{
  "success": false,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "The email address or password is incorrect."
  },
  "meta": {
    "correlationId": "51f62a7c-8242-4a57-954c-9ac5b8535df0"
  }
}
```

Use the same response for an unknown email and incorrect password.

### Account Locked

```json
{
  "success": false,
  "error": {
    "code": "ACCOUNT_LOCKED",
    "message": "This account is temporarily locked. Use password recovery or try again later."
  },
  "meta": {
    "correlationId": "51f62a7c-8242-4a57-954c-9ac5b8535df0"
  }
}
```

A security review may require returning `INVALID_CREDENTIALS` instead to avoid revealing account existence.

---

## 10. Refresh API

### Endpoint

```http
POST /api/v1/auth/refresh
```

The frontend sends no refresh token in JSON. The browser sends the `HttpOnly` cookie using `credentials: 'include'`.

### Refresh Flow

1. Read the raw refresh token from the cookie.
2. hash it using the same token-hashing approach used during login.
3. retrieve the active session by token hash.
4. reject missing, expired, or revoked sessions.
5. verify the associated user and role are active.
6. rotate the refresh token.
7. revoke the used session and link it to the replacement session.
8. issue a new access JWT and refresh cookie.
9. create `TOKEN_REFRESHED` audit event.

### Session Lookup Query

```sql
SELECT
    s.session_id,
    s.user_id,
    s.token_family_id,
    s.remember_me,
    s.expires_at,
    s.revoked_at,
    u.bi_email,
    u.status,
    r.role_code,
    r.is_active AS role_is_active
FROM user_sessions s
INNER JOIN users u
    ON u.user_id = s.user_id
INNER JOIN roles r
    ON r.role_id = u.role_id
WHERE s.refresh_token_hash = :refresh_token_hash
LIMIT 1;
```

### Rotate Session

Within one transaction:

```sql
UPDATE user_sessions
SET
    revoked_at = CURRENT_TIMESTAMP,
    revoked_reason = 'ROTATED',
    last_used_at = CURRENT_TIMESTAMP,
    replaced_by_session_id = :new_session_id
WHERE session_id = :old_session_id
  AND revoked_at IS NULL;
```

```sql
INSERT INTO user_sessions (
    session_id,
    user_id,
    refresh_token_hash,
    token_family_id,
    remember_me,
    expires_at,
    ip_address,
    user_agent
)
VALUES (
    :new_session_id,
    :user_id,
    :new_refresh_token_hash,
    :token_family_id,
    :remember_me,
    :new_expires_at,
    :ip_address,
    :user_agent
);
```

If a revoked refresh token is reused, revoke all active sessions in its token family and create `REFRESH_TOKEN_REUSE_DETECTED`.

---

## 11. Current User API

### Endpoint

```http
GET /api/v1/auth/me
Authorization: Bearer <access-token>
```

### Query

```sql
SELECT
    u.user_id,
    u.first_name,
    u.last_name,
    u.bi_email,
    u.status,
    u.is_email_verified,
    r.role_code
FROM users u
INNER JOIN roles r
    ON r.role_id = u.role_id
WHERE u.user_id = :jwt_subject
LIMIT 1;
```

### Response

```json
{
  "success": true,
  "data": {
    "userId": "fc60cb42-17dc-4c74-b127-1d734fc6110d",
    "firstName": "John",
    "lastName": "Doe",
    "biEmail": "john.doe@company.com",
    "role": "REGULAR_USER",
    "status": "ACTIVE",
    "emailVerified": false
  }
}
```

---

## 12. Logout API

### Endpoint

```http
POST /api/v1/auth/logout
Authorization: Bearer <access-token>
```

### Behavior

1. Identify the session using the JWT `sid` claim or refresh cookie.
2. revoke the session.
3. create a `LOGOUT` audit event.
4. clear the refresh cookie.
5. return `204 No Content`.

```sql
UPDATE user_sessions
SET
    revoked_at = CURRENT_TIMESTAMP,
    revoked_reason = 'USER_LOGOUT'
WHERE session_id = :session_id
  AND user_id = :user_id
  AND revoked_at IS NULL;
```

Because JWT access tokens remain valid until expiry, access tokens must remain short-lived.

---

## 13. TypeScript Contracts

```ts
export interface LoginFormValues {
  biEmail: string;
  password: string;
  rememberMe: boolean;
}

export type UserRole = 'ADMIN' | 'POWER_USER' | 'REGULAR_USER';

export interface AuthenticatedUser {
  userId: string;
  firstName: string;
  lastName: string;
  biEmail: string;
  role: UserRole;
}

export interface LoginResponse {
  success: true;
  data: {
    user: AuthenticatedUser;
    authentication: {
      accessToken: string;
      tokenType: 'Bearer';
      expiresIn: number;
    };
  };
  meta: {
    correlationId: string;
  };
}

export interface ApiFieldError {
  field: string;
  code: string;
  message: string;
}

export interface ApiErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    fieldErrors?: ApiFieldError[];
  };
  meta?: {
    correlationId: string;
  };
}
```

---

## 14. React Frontend Structure

```text
src/
├── features/auth/
│   ├── api/authApi.ts
│   ├── components/LoginForm.tsx
│   ├── hooks/useAuth.ts
│   ├── pages/LoginPage.tsx
│   ├── schemas/loginSchema.ts
│   └── types/auth.types.ts
├── routes/ProtectedRoute.tsx
├── stores/authStore.ts
└── lib/apiClient.ts
```

### Responsibilities

- `LoginPage.tsx`: Page layout and links.
- `LoginForm.tsx`: Inputs, validation messages, submission, and loading state.
- `loginSchema.ts`: Client validation schema.
- `authApi.ts`: Login, refresh, current-user, and logout calls.
- `authStore.ts`: In-memory access token and authenticated user.
- `useAuth.ts`: Authentication actions and state selectors.
- `apiClient.ts`: Authorization header, refresh handling, and retry guard.
- `ProtectedRoute.tsx`: Blocks unauthenticated navigation.

---

## 15. Frontend Form Mapping

```ts
const payload: LoginFormValues = {
  biEmail: values.biEmail.trim().toLowerCase(),
  password: values.password,
  rememberMe: values.rememberMe ?? false,
};
```

Do not trim or normalize `password`.

### Submit Flow

```text
Validate fields
  → set submitting state
  → clear previous API error
  → POST /auth/login with credentials included
  → store access token in memory
  → store user in auth state
  → redirect to authorized landing page
  → on failure map API error to UI
  → clear submitting state
```

API request example:

```ts
export async function login(
  payload: LoginFormValues,
): Promise<LoginResponse> {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify(payload),
  });

  const body = await response.json();

  if (!response.ok) {
    throw body as ApiErrorResponse;
  }

  return body as LoginResponse;
}
```

---

## 16. Authentication State

```ts
export interface AuthState {
  user: AuthenticatedUser | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isInitializing: boolean;
}
```

Rules:

- Store the access token in memory only.
- Store the refresh token only in the backend-managed `HttpOnly` cookie.
- Never store the password, refresh token, or secret answer in React state beyond the active form.
- Do not put tokens in `localStorage` or `sessionStorage`.
- Clear the password field after an unsuccessful submission where appropriate.

---

## 17. Application Startup and Token Refresh

When the application loads:

```text
Set isInitializing = true
  → POST /auth/refresh with credentials included
  → if successful, store new access token
  → GET /auth/me
  → store current user
  → set isInitializing = false
```

If refresh fails because no valid session exists:

```text
Clear authentication state
  → set isInitializing = false
  → allow public routes
  → redirect protected routes to /login
```

### Protected Request Behavior

1. Add `Authorization: Bearer <accessToken>`.
2. If the API returns `401`, call `/auth/refresh` once.
3. If refresh succeeds, retry the original request once with the new token.
4. If refresh fails, clear authentication state and redirect to `/login`.
5. Prevent multiple simultaneous refresh calls by sharing one refresh promise.
6. Never retry indefinitely.

---

## 18. Role-Based Redirect Mapping

```ts
const landingRouteByRole: Record<UserRole, string> = {
  ADMIN: '/admin',
  POWER_USER: '/workspace',
  REGULAR_USER: '/workspace',
};
```

This mapping controls navigation only. The backend must enforce permissions for every protected API and resource.

---

## 19. Tailwind CSS and Accessibility

Suggested core classes:

```text
Page:        min-h-screen flex items-center justify-center bg-slate-50 px-4
Card:        w-full max-w-md rounded-2xl bg-white p-8 shadow-lg
Heading:     text-2xl font-semibold text-slate-900
Label:       text-sm font-medium text-slate-700
Input:       w-full rounded-lg border border-slate-300 px-3 py-2
Input focus: focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200
Error:       mt-1 text-sm text-red-600
Button:      w-full rounded-lg bg-blue-600 px-4 py-2 font-medium text-white
Disabled:    disabled:cursor-not-allowed disabled:opacity-60
```

Accessibility requirements:

- Associate labels with inputs using `htmlFor` and `id`.
- Use `type="email"` and `type="password"`.
- Use `autoComplete="email"` and `autoComplete="current-password"`.
- Use `aria-invalid` and `aria-describedby` for field errors.
- Announce API errors using `role="alert"`.
- Preserve visible keyboard focus.
- The submit button must communicate loading state.
- Do not rely only on color to communicate errors.

---

## 20. Audit Events

Record:

```text
LOGIN_SUCCEEDED
LOGIN_FAILED
ACCOUNT_LOCKED
TOKEN_REFRESHED
REFRESH_TOKEN_REUSE_DETECTED
LOGOUT
SESSION_REVOKED
```

Audit records may include:

- User ID, when known.
- Session ID.
- Outcome and error code.
- Correlation ID.
- IP address.
- User agent.
- Event timestamp.

Never record:

- Submitted passwords.
- Password hashes.
- Access tokens.
- Raw refresh tokens.
- Refresh-token hashes in general application logs.
- Secret questions or answers.

---

## 21. Backend Security Requirements

- Require HTTPS.
- Use parameterized queries or an ORM.
- Verify passwords with Argon2id; never compare plaintext values in SQL.
- Use uniform invalid-credential responses.
- Use dummy hash verification for unknown emails.
- Apply both rate limiting and account locking.
- Use cryptographically secure refresh tokens.
- Store only refresh-token hashes.
- Rotate refresh tokens on every refresh.
- Revoke the token family when reuse is detected.
- Use short-lived access tokens.
- Redact authentication data from logs and traces.
- Validate account status and authorization on the backend.
- Revoke active sessions after password reset or high-risk account changes.

---

## 22. Acceptance Criteria

### API and Database

- Login retrieves the user, role, and security record using normalized email.
- Unknown email and incorrect password return the same safe response.
- Password verification uses the stored Argon2id hash.
- Failed attempts are incremented atomically.
- The account is temporarily locked at the configured threshold.
- Expired temporary locks can be cleared safely.
- Successful login resets failed attempts.
- Successful login updates `last_login_at`.
- A refresh-token session is created before success is returned.
- Only a hash of the refresh token is stored.
- Login and session events are audited.
- The access JWT contains the required claims and configured expiry.

### Frontend

- Email is trimmed and converted to lowercase.
- Password is sent unchanged.
- Duplicate submissions are prevented.
- API errors are mapped to clear UI states.
- Access token remains in memory.
- Refresh requests include credentials.
- Protected requests include the bearer token.
- Only one refresh request runs when multiple APIs return `401` together.
- Failed refresh clears auth state and redirects protected routes.
- Logout revokes the session and clears frontend state.
- The page is responsive, keyboard accessible, and screen-reader friendly.

---

## 23. Required Test Scenarios

1. Successful login with valid email and password.
2. Successful login with mixed-case email.
3. Unknown email returns `INVALID_CREDENTIALS`.
4. Incorrect password returns `INVALID_CREDENTIALS`.
5. Unknown-email and wrong-password paths have comparable behavior.
6. Failed login increments the counter.
7. Threshold attempt locks the account.
8. Locked account cannot log in before expiry.
9. Expired temporary lock is cleared and valid login succeeds.
10. Disabled user cannot log in.
11. User with inactive role cannot log in.
12. Successful login resets prior failed attempts.
13. Successful login creates one active session and audit event.
14. Session insert failure does not return successful login.
15. Refresh rotates the token and revokes the old session.
16. Reused rotated token revokes its token family.
17. Expired refresh session is rejected.
18. Logout revokes the session and clears the cookie.
19. Access token expiry causes one refresh and one request retry.
20. Failed refresh redirects protected routes to login.
21. Passwords and tokens do not appear in logs or audit details.
22. Simultaneous invalid login attempts do not lose counter updates.
23. Simultaneous `401` responses create only one frontend refresh call.
24. Keyboard and screen-reader behavior meets accessibility requirements.
25. Rate limits return `429` with `Retry-After`.

---

## 24. Endpoint Summary

```text
POST /api/v1/auth/login    Verify credentials and create session
POST /api/v1/auth/refresh  Rotate refresh token and issue access token
GET  /api/v1/auth/me       Return the authenticated user profile
POST /api/v1/auth/logout   Revoke the current session
```

This specification is the shared implementation contract for the login page, authentication APIs, database operations, JWT handling, refresh-token lifecycle, frontend state, and security behavior.
