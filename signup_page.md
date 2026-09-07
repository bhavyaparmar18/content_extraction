# Signup Page — Full Backend and Frontend Technical Specification

**Project:** Governance Procedure (SOP) Document Automator  
**Module:** Identity and Access Management  
**Feature:** First-Time User Signup  
**Document Type:** Full-Stack Functional, API, Data, Security, and UI Integration Specification  
**Version:** 2.0  
**Status:** Development Reference  
**Last Updated:** 4 August 2026  
**Deployment Platform:** Amazon Web Services (AWS)  
**Backend:** Python, FastAPI, PostgreSQL  
**Frontend:** React, TypeScript, Tailwind CSS  
**Authentication:** JSON Web Token (JWT)  
**API Base Path:** `/api/v1/auth`

---

## 1. Purpose

This specification defines the complete backend and frontend implementation contract for the signup page of the Governance Procedure (SOP) Document Automator.

It covers:

- Signup-page fields and user experience.
- React and TypeScript component mapping.
- Tailwind CSS presentation requirements.
- Frontend form state, validation, API integration, and error handling.
- FastAPI endpoint contracts and processing behavior.
- PostgreSQL tables, constraints, indexes, and relationships.
- Password and secret-answer security.
- Default role assignment.
- JWT generation and frontend authentication initialization.
- Correlation IDs, idempotency, auditing, rate limiting, and observability.
- End-to-end request, response, and failure flows.
- Acceptance criteria and test scenarios.

The public signup flow creates a user with the server-controlled `REGULAR_USER` role. The browser must never be allowed to submit or override roles, account status, email-verification state, or other administrative attributes.

---

## 2. Project Context

The Governance Procedure Document Automator is an enterprise application that migrates PDF and DOCX SOP documents into approved DOCX templates, supports OCR, translation, controlled natural-language modifications, versioning, evaluation, review workflows, and auditability.

The platform supports three primary application roles:

- `ADMIN`: Full application and administrative access.
- `POWER_USER`: Broad operational access without protected delete permissions.
- `REGULAR_USER`: Standard access to permitted or owned resources.

Public signup always creates a `REGULAR_USER`. Authorization for document, template, job, version, evaluation, and administrative operations must be enforced by protected backend APIs after authentication.

The signup feature establishes the initial identity required for later access to the document workspace and related application workflows.

---

## 3. Scope

### 3.1 In Scope

- Roles table and standard application roles.
- Users table for user profile, role, status, and lifecycle attributes.
- Secret questions master table.
- User security table for password and recovery credentials.
- Audit event storage for registration and security events.
- Public API to retrieve active secret questions.
- Public API to create an account.
- Password and secret-answer hashing.
- Server-side default role assignment.
- JWT issuance after successful registration.
- React signup page and component structure.
- TypeScript request, response, and error types.
- Tailwind CSS layout and state styling.
- Frontend and backend validation mapping.
- API client behavior, correlation IDs, and idempotency keys.
- Loading, empty, success, and error states.
- Client-side authentication initialization after signup.
- Accessibility, responsive behavior, and secure browser handling.
- Unit, integration, component, API, and end-to-end test requirements.

### 3.2 Out of Scope

- Login API and login page.
- Refresh-token API and refresh-token storage.
- Email verification implementation.
- Forgot-password and reset-password APIs.
- Administrative management APIs for secret questions.
- Multi-factor authentication.
- Enterprise federation or SSO.
- Final organization identity-provider integration.
- Document workspace implementation.
- Assignment of `ADMIN` or `POWER_USER` through public signup.

---

## 4. Design Principles

1. **Backend authority:** The backend is authoritative for validation, role assignment, uniqueness, account creation, and authorization.
2. **No privilege input:** The frontend does not send role, permissions, status, or administrative fields.
3. **Atomic account creation:** A user record must never exist without the related security record.
4. **No plaintext credential persistence:** Passwords and secret answers must never be stored or logged in plaintext.
5. **Managed secret questions:** The UI obtains active questions from the backend and does not hard-code them.
6. **Typed integration:** Request and response contracts are represented as TypeScript types.
7. **Accessible UX:** Inputs, errors, loading states, and focus behavior must support keyboard and assistive-technology users.
8. **Traceable requests:** Correlation IDs connect frontend failures, API activity, audit events, logs, and traces.
9. **Safe retries:** Signup submissions use idempotency keys to reduce duplicate account creation after network timeouts.
10. **Progressive architecture:** Authentication state and API abstractions should support later login, refresh-token, and enterprise identity decisions without coupling the signup form to those implementations.

---

## 5. User Story

As a first-time user, I want to create an account using my BI email address, profile details, password, and a managed secret question so that I can securely access the SOP Document Automator with the default Regular User permissions.

---

## 6. Signup Page Fields

| UI Label | Frontend Field | API Field | HTML Control | Required | Description |
|---|---|---|---|---:|---|
| First Name | `firstName` | `firstName` | Text input | Yes | User's given name. |
| Last Name | `lastName` | `lastName` | Text input | Yes | User's family name. |
| BI Email | `biEmail` | `biEmail` | Email input | Yes | Unique organization email address. |
| Password | `password` | `password` | Password input | Yes | New account password. |
| Confirm Password | `confirmPassword` | `confirmPassword` | Password input | Yes | Must exactly match the password. |
| Secret Question | `secretQuestionId` | `secretQuestionId` | Select/dropdown | Yes | UUID of an active question retrieved from the API. |
| Secret Answer | `secretAnswer` | `secretAnswer` | Password or masked text input | Yes | Recovery answer for a future password-recovery flow. |

### 6.1 UI Behavior

- Load active secret questions when the page is opened.
- Show a loading state while questions are being retrieved.
- Use `questionId` as the option value and `questionText` as the displayed label.
- Never submit the question text.
- Disable signup while secret questions are loading, unavailable, or empty.
- Disable repeated submission while the signup request is in progress.
- Display frontend validation messages next to the relevant fields.
- Map backend field errors to the corresponding frontend controls.
- Show safe form-level messages for non-field errors.
- Move focus to the first invalid field after validation failure.
- Clear `password`, `confirmPassword`, and `secretAnswer` after security-sensitive server failures where re-entry is appropriate.
- Do not persist credentials in browser storage, URL state, analytics, logs, or telemetry.
- Provide password visibility controls with accessible labels.
- Redirect authenticated users away from the signup page according to the application's routing policy.

---

# Part I — Backend Specification

## 7. Backend Technology and Service Boundary

The backend is implemented with Python and FastAPI and uses PostgreSQL for durable identity, role, security, and audit data.

Recommended module structure:

```text
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── auth.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── rate_limit.py
│   │   └── observability.py
│   ├── schemas/
│   │   └── auth.py
│   ├── models/
│   │   ├── role.py
│   │   ├── user.py
│   │   ├── user_security.py
│   │   ├── secret_question.py
│   │   └── audit_event.py
│   ├── repositories/
│   │   ├── role_repository.py
│   │   ├── user_repository.py
│   │   ├── secret_question_repository.py
│   │   └── audit_repository.py
│   ├── services/
│   │   ├── signup_service.py
│   │   ├── password_service.py
│   │   ├── token_service.py
│   │   └── audit_service.py
│   └── main.py
└── tests/
```

The signup business transaction should be implemented in a service independent of the FastAPI route handler so it can be unit-tested without HTTP concerns.

---

## 8. PostgreSQL Prerequisite

UUID generation uses `gen_random_uuid()` from `pgcrypto`.

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

---

## 9. Roles Table

```sql
CREATE TABLE roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_code VARCHAR(50) NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    description TEXT,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_roles_role_code UNIQUE (role_code),
    CONSTRAINT uq_roles_role_name UNIQUE (role_name)
);
```

Only one role may be marked as the default:

```sql
CREATE UNIQUE INDEX uq_roles_one_default
    ON roles (is_default)
    WHERE is_default = TRUE;
```

Seed roles:

```sql
INSERT INTO roles (
    role_code,
    role_name,
    description,
    is_default
)
VALUES
    ('ADMIN', 'Administrator', 'Full application and administrative access.', FALSE),
    ('POWER_USER', 'Power User', 'Broad operational access without protected delete permissions.', FALSE),
    ('REGULAR_USER', 'Regular User', 'Standard access to permitted and owned resources.', TRUE)
ON CONFLICT (role_code) DO NOTHING;
```

### 9.1 Role Rules

- Public signup must load the active default `REGULAR_USER` role on the server.
- `role`, `roleId`, `roleCode`, and permissions are prohibited request properties.
- The client cannot promote a user through request manipulation.
- If the required default role is missing or inactive, signup must return a safe `503` configuration error.

---

## 10. Users Table

```sql
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    bi_email VARCHAR(320) NOT NULL,
    role_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deactivated_at TIMESTAMPTZ,
    CONSTRAINT fk_users_role
        FOREIGN KEY (role_id)
        REFERENCES roles(role_id),
    CONSTRAINT ck_users_status
        CHECK (status IN ('PENDING_VERIFICATION', 'ACTIVE', 'LOCKED', 'DISABLED')),
    CONSTRAINT ck_users_first_name_not_blank
        CHECK (length(btrim(first_name)) >= 1),
    CONSTRAINT ck_users_last_name_not_blank
        CHECK (length(btrim(last_name)) >= 1),
    CONSTRAINT ck_users_email_lowercase
        CHECK (bi_email = lower(bi_email))
);
```

Case-insensitive email uniqueness:

```sql
CREATE UNIQUE INDEX uq_users_bi_email_ci
    ON users (lower(bi_email));
```

---

## 11. Secret Questions Table

```sql
CREATE TABLE secret_questions (
    secret_question_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_code VARCHAR(100) NOT NULL,
    question_text VARCHAR(300) NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_secret_questions_code UNIQUE (question_code),
    CONSTRAINT uq_secret_questions_text UNIQUE (question_text),
    CONSTRAINT ck_secret_questions_text_not_blank
        CHECK (length(btrim(question_text)) >= 5),
    CONSTRAINT ck_secret_questions_display_order
        CHECK (display_order >= 0)
);
```

```sql
CREATE INDEX ix_secret_questions_active_order
    ON secret_questions (is_active, display_order, question_text);
```

Example seed data:

```sql
INSERT INTO secret_questions (
    question_code,
    question_text,
    display_order
)
VALUES
    ('FIRST_SCHOOL', 'What was the name of your first school?', 10),
    ('CHILDHOOD_NICKNAME', 'What was your childhood nickname?', 20),
    ('FIRST_PET', 'What was the name of your first pet?', 30),
    ('BIRTH_CITY', 'In which city were you born?', 40),
    ('FAVORITE_TEACHER', 'What was the surname of your favorite teacher?', 50)
ON CONFLICT (question_code) DO NOTHING;
```

### 11.1 Management Rules

- Do not physically delete a referenced question.
- Set `is_active = FALSE` to remove it from future signup selections.
- Existing users may retain references to inactive questions.
- `question_code` remains stable even if display text changes.
- Changes must be controlled and audited because the text is also relevant to recovery workflows.

---

## 12. User Security Table

```sql
CREATE TABLE user_security (
    user_id UUID PRIMARY KEY,
    password_hash TEXT NOT NULL,
    secret_question_id UUID NOT NULL,
    secret_answer_hash TEXT NOT NULL,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    lock_reason VARCHAR(100),
    password_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    secret_answer_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_security_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_user_security_secret_question
        FOREIGN KEY (secret_question_id)
        REFERENCES secret_questions(secret_question_id),
    CONSTRAINT ck_user_security_failed_attempts
        CHECK (failed_login_attempts >= 0)
);
```

### 12.1 Credential Storage Rules

- Never store plaintext passwords.
- Never store plaintext secret answers.
- Never store `confirmPassword`.
- Hash the password with approved Argon2id parameters.
- Normalize and hash the secret answer independently.
- Never reuse password hashes, salts, or hash inputs for secret answers.
- Keep hashing configuration centrally managed and version-aware.
- Ensure recovery verification uses exactly the same normalization rules.

---

## 13. Audit Events Table

```sql
CREATE TABLE audit_events (
    audit_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID,
    event_type VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    outcome VARCHAR(30) NOT NULL,
    error_code VARCHAR(100),
    correlation_id UUID NOT NULL,
    event_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_events_actor
        FOREIGN KEY (actor_user_id)
        REFERENCES users(user_id)
        ON DELETE SET NULL,
    CONSTRAINT ck_audit_events_outcome
        CHECK (outcome IN ('SUCCESS', 'FAILURE', 'DENIED'))
);
```

```sql
CREATE INDEX ix_audit_events_actor_time
    ON audit_events (actor_user_id, occurred_at DESC);

CREATE INDEX ix_audit_events_correlation_id
    ON audit_events (correlation_id);

CREATE INDEX ix_audit_events_resource
    ON audit_events (resource_type, resource_id, occurred_at DESC);
```

Safe successful event shape:

```json
{
  "eventType": "IDENTITY",
  "action": "USER_SIGNUP",
  "resourceType": "USER",
  "outcome": "SUCCESS"
}
```

Safe failed event shape:

```json
{
  "eventType": "IDENTITY",
  "action": "USER_SIGNUP",
  "resourceType": "USER",
  "outcome": "FAILURE",
  "errorCode": "VALIDATION_ERROR"
}
```

Audit data must never contain passwords, confirmation passwords, secret answers, hashes, JWTs, or complete signup request bodies.

---

## 14. Entity Relationships

```text
roles (1) --------------------< users (many)
                                  |
                                  | 1:1
                                  v
                             user_security
                                  |
                                  | many:1
                                  v
                         secret_questions

users (0..1 as actor) --------< audit_events (many)
```

---

## 15. API 1 — Retrieve Secret Questions

### 15.1 Endpoint

```http
GET /api/v1/auth/secret-questions
```

This is a public endpoint and does not require a JWT.

### 15.2 Request Headers

```http
Accept: application/json
X-Correlation-ID: <optional-uuid>
```

If `X-Correlation-ID` is absent, the server generates one. The response must include the effective correlation ID.

### 15.3 Query Parameters

None in version 1.

### 15.4 Retrieval Query

```sql
SELECT
    secret_question_id,
    question_text
FROM secret_questions
WHERE is_active = TRUE
ORDER BY display_order ASC, question_text ASC;
```

### 15.5 Success Response

**Status:** `200 OK`

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "questionId": "d851a7fd-37a1-4f14-8e19-d3e30efdc20b",
        "questionText": "What was the name of your first school?"
      }
    ]
  },
  "meta": {
    "correlationId": "a9192bf2-312b-41f4-b3f5-f877ff88e270"
  }
}
```

An empty `items` array is valid. The frontend must then disable signup and display a safe configuration message.

### 15.6 Error Response

**Status:** `500 Internal Server Error`

```json
{
  "success": false,
  "error": {
    "code": "SECRET_QUESTIONS_UNAVAILABLE",
    "message": "Secret questions are temporarily unavailable. Please try again later."
  },
  "meta": {
    "correlationId": "a9192bf2-312b-41f4-b3f5-f877ff88e270"
  }
}
```

### 15.7 Caching

The API may use short-lived caching:

```http
Cache-Control: public, max-age=300
```

Only active question IDs and display text may be returned. Internal codes, timestamps, and activation flags must not be exposed.

---

## 16. API 2 — User Signup

### 16.1 Endpoint

```http
POST /api/v1/auth/signup
```

### 16.2 Authentication

No existing JWT is required. The endpoint is public and must be protected through HTTPS, rate limiting, request-size limits, abuse monitoring, and secure validation.

### 16.3 Request Headers

```http
Content-Type: application/json
Accept: application/json
X-Correlation-ID: <optional-uuid>
Idempotency-Key: <recommended-unique-value>
```

The server must not store raw credentials as part of idempotency processing.

### 16.4 Request Body

```json
{
  "firstName": "John",
  "lastName": "Doe",
  "biEmail": "john.doe@company.com",
  "password": "Password@123",
  "confirmPassword": "Password@123",
  "secretQuestionId": "d851a7fd-37a1-4f14-8e19-d3e30efdc20b",
  "secretAnswer": "Example answer"
}
```

Unknown properties should be rejected. The request must not contain role, permission, status, verification, audit, or administrative properties.

---

## 17. Backend Validation Rules

### 17.1 First and Last Name

- Required strings.
- Trim leading and trailing whitespace.
- Minimum 1 and maximum 100 characters after trimming.
- Reject control characters.
- Support Unicode names, spaces, apostrophes, and hyphens.

### 17.2 BI Email

- Required valid email address.
- Maximum 320 characters.
- Trim and normalize to lowercase.
- Enforce configured organization-domain policy when enabled.
- Enforce case-insensitive uniqueness.
- Treat the database unique index as the final authority.

### 17.3 Password

- Required string.
- Minimum 12 and maximum 128 characters.
- Must not equal the normalized email address.
- Permit spaces and a broad character set.
- Do not silently truncate.
- Apply approved compromised-password checks when configured.
- Keep policy centrally configurable.

### 17.4 Confirm Password

- Required string.
- Must exactly match `password`.
- Used only for validation.
- Never stored or logged.

### 17.5 Secret Question ID

- Required UUID.
- Must reference an existing active question at transaction processing time.

### 17.6 Secret Answer

- Required string.
- Trim before validation.
- Minimum 2 and maximum 255 characters after normalization.
- Never return the answer through an API.
- Normalize and hash with approved security settings.

---

## 18. Signup Processing Flow

1. Generate or validate the correlation ID.
2. Enforce HTTPS at the deployment boundary.
3. Enforce content type, request-size, rate-limit, and abuse controls.
4. Parse the JSON body.
5. Reject unknown or administrative properties.
6. Validate the request schema.
7. Normalize names, email, and secret answer.
8. Verify that the password and confirmation match.
9. Apply the configured password policy.
10. Verify that the selected secret question exists and is active.
11. Load the active default `REGULAR_USER` role.
12. Hash the password with Argon2id.
13. Hash the normalized secret answer independently.
14. Start a database transaction.
15. Insert the `users` record.
16. Insert the `user_security` record.
17. Insert the successful `audit_events` record.
18. Commit the transaction.
19. Generate a signed access JWT only after commit.
20. Return `201 Created` with safe user and token information.
21. Remove plaintext credential references from application memory as far as the runtime allows.

If a database operation fails, the complete transaction must roll back.

### 18.1 Transaction Pseudocode

```text
BEGIN
  validate request
  normalize values
  verify active secret question
  load default REGULAR_USER role
  calculate password hash
  calculate secret-answer hash
  INSERT users
  INSERT user_security
  INSERT audit_events (SUCCESS)
COMMIT

generate access JWT
return 201
```

A rejected attempt may be audited separately outside the rolled-back transaction if no credential data is recorded.

---

## 19. Successful Signup Response

**Status:** `201 Created`

```json
{
  "success": true,
  "message": "User registered successfully.",
  "data": {
    "user": {
      "userId": "fc60cb42-17dc-4c74-b127-1d734fc6110d",
      "firstName": "John",
      "lastName": "Doe",
      "biEmail": "john.doe@company.com",
      "role": "REGULAR_USER",
      "status": "ACTIVE",
      "emailVerified": false
    },
    "authentication": {
      "accessToken": "<signed-jwt>",
      "tokenType": "Bearer",
      "expiresIn": 900
    }
  },
  "meta": {
    "correlationId": "51f62a7c-8242-4a57-954c-9ac5b8535df0"
  }
}
```

If email verification becomes mandatory in a future version, create the account in `PENDING_VERIFICATION` state and do not issue an access token until verification succeeds.

---

## 20. JWT Requirements

Recommended claims:

```json
{
  "iss": "governance-sop-api",
  "aud": "governance-sop-web",
  "sub": "fc60cb42-17dc-4c74-b127-1d734fc6110d",
  "email": "john.doe@company.com",
  "role": "REGULAR_USER",
  "jti": "f88cdcee-405e-4755-9bd9-50fac9f26df7",
  "iat": 1785826800,
  "nbf": 1785826800,
  "exp": 1785827700
}
```

Rules:

- Prefer asymmetric signing such as RS256 or ES256.
- Initial access-token lifetime is 15 minutes.
- Do not include password or recovery information.
- Validate signature, issuer, audience, expiry, and not-before claims.
- Use backend authorization checks; hidden frontend controls are not security enforcement.
- Return tokens only over HTTPS.
- Token storage strategy must be finalized with the login and refresh-token architecture. An in-memory access token is preferred over persistent browser storage for this scope.

---

## 21. Error Contract

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Safe user-facing message.",
    "fieldErrors": [
      {
        "field": "fieldName",
        "code": "FIELD_ERROR_CODE",
        "message": "Field-specific message."
      }
    ]
  },
  "meta": {
    "correlationId": "51f62a7c-8242-4a57-954c-9ac5b8535df0"
  }
}
```

### 21.1 Required Error Cases

| HTTP Status | Error Code | Frontend Treatment |
|---:|---|---|
| 400 | `BAD_REQUEST` | Show safe form-level request error. |
| 409 | `EMAIL_ALREADY_REGISTERED` | Attach message to BI Email. |
| 409 | `IDEMPOTENCY_CONFLICT` | Prevent duplicate retry and show safe message. |
| 422 | `VALIDATION_ERROR` | Map `fieldErrors` to controls. |
| 422 | `INVALID_SECRET_QUESTION` | Refresh questions and attach error to dropdown. |
| 429 | `RATE_LIMIT_EXCEEDED` | Show retry message; honor `Retry-After`. |
| 500 | `INTERNAL_SERVER_ERROR` | Show generic error and correlation ID support reference. |
| 503 | `SIGNUP_CONFIGURATION_ERROR` | Disable submission and show temporary-unavailability message. |

Validation example:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "One or more fields are invalid.",
    "fieldErrors": [
      {
        "field": "confirmPassword",
        "code": "PASSWORDS_DO_NOT_MATCH",
        "message": "Password and confirm password must match."
      }
    ]
  },
  "meta": {
    "correlationId": "51f62a7c-8242-4a57-954c-9ac5b8535df0"
  }
}
```

---

## 22. HTTP Status Summary

| Status | Endpoint | Condition |
|---:|---|---|
| 200 | Secret questions | Active questions returned, including an empty list. |
| 201 | Signup | User and security records created successfully. |
| 400 | Both | Malformed JSON, invalid content type, or invalid syntax. |
| 409 | Signup | Email already registered or idempotency conflict. |
| 422 | Signup | Field validation or secret-question validation failed. |
| 429 | Both | Rate limit exceeded. |
| 500 | Both | Unexpected server error. |
| 503 | Signup | Required signup configuration unavailable. |

---

## 23. Backend Security and Operational Requirements

- Require HTTPS.
- Use Argon2id with centrally approved parameters.
- Never log signup request bodies.
- Redact authorization headers, cookies, JWTs, and credential data.
- Use parameterized SQL or a safe ORM.
- Assign `REGULAR_USER` only on the server.
- Enforce database uniqueness for normalized email.
- Rate-limit both public endpoints.
- Consider CAPTCHA or equivalent controls after risk assessment.
- Never expose stack traces, SQL details, or constraint names.
- Record meaningful success and failure audit events.
- Treat all request input as untrusted.
- Use AWS Secrets Manager or an approved equivalent for secrets.
- Emit structured metrics and traces with correlation IDs.
- Keep application timestamps in UTC using `TIMESTAMPTZ`.

Suggested initial limits:

- Secret questions: 60 requests per minute per IP.
- Signup: 5 attempts per 15 minutes per IP, plus controls per normalized email.
- Return `Retry-After` with `429` responses.

---

# Part II — Frontend Specification

## 24. Frontend Technology

Required stack:

- React.
- TypeScript with strict type checking.
- Tailwind CSS.

Recommended supporting libraries:

- React Router for routing.
- React Hook Form for controlled form state and accessibility-friendly validation.
- Zod for shared client-side schema validation.
- TanStack Query for server-state loading and mutation handling, or a small typed custom hook if the project avoids an additional dependency.
- A typed `fetch` wrapper or Axios for HTTP communication.
- Zustand, Redux Toolkit, or React Context for authentication state; the project should standardize on one approach.

Recommendations are not new backend requirements. The API contract remains library-neutral.

---

## 25. Frontend Folder Structure

```text
src/
├── app/
│   ├── router.tsx
│   └── providers.tsx
├── api/
│   ├── apiClient.ts
│   └── authApi.ts
├── components/
│   ├── common/
│   │   ├── Alert.tsx
│   │   ├── Button.tsx
│   │   ├── FormField.tsx
│   │   ├── LoadingSpinner.tsx
│   │   ├── PasswordInput.tsx
│   │   ├── SelectField.tsx
│   │   └── TextInput.tsx
│   └── auth/
│       └── SignupForm.tsx
├── features/
│   └── auth/
│       ├── hooks/
│       │   ├── useSecretQuestions.ts
│       │   └── useSignup.ts
│       ├── schemas/
│       │   └── signupSchema.ts
│       ├── services/
│       │   └── authService.ts
│       ├── store/
│       │   └── authStore.ts
│       └── types/
│           └── auth.types.ts
├── pages/
│   └── SignupPage.tsx
└── utils/
    ├── correlationId.ts
    ├── idempotencyKey.ts
    └── apiErrors.ts
```

---

## 26. TypeScript Domain Types

```typescript
export interface SignupFormValues {
  firstName: string;
  lastName: string;
  biEmail: string;
  password: string;
  confirmPassword: string;
  secretQuestionId: string;
  secretAnswer: string;
}

export type SignupRequest = SignupFormValues;

export interface SecretQuestion {
  questionId: string;
  questionText: string;
}

export interface ApiMeta {
  correlationId: string;
}

export interface SecretQuestionsResponse {
  success: true;
  data: {
    items: SecretQuestion[];
  };
  meta: ApiMeta;
}

export interface AuthenticatedUser {
  userId: string;
  firstName: string;
  lastName: string;
  biEmail: string;
  role: "REGULAR_USER" | "POWER_USER" | "ADMIN";
  status: "PENDING_VERIFICATION" | "ACTIVE" | "LOCKED" | "DISABLED";
  emailVerified: boolean;
}

export interface AuthenticationResult {
  accessToken: string;
  tokenType: "Bearer";
  expiresIn: number;
}

export interface SignupSuccessResponse {
  success: true;
  message: string;
  data: {
    user: AuthenticatedUser;
    authentication: AuthenticationResult;
  };
  meta: ApiMeta;
}

export interface ApiFieldError {
  field: keyof SignupFormValues | string;
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
  meta: ApiMeta;
}
```

---

## 27. Frontend Field Mapping

| Frontend Field | API Field | Input Type | Autocomplete | Normalization Before Request |
|---|---|---|---|---|
| `firstName` | `firstName` | `text` | `given-name` | Trim. |
| `lastName` | `lastName` | `text` | `family-name` | Trim. |
| `biEmail` | `biEmail` | `email` | `email` | Trim and lowercase. |
| `password` | `password` | `password` | `new-password` | Do not trim automatically. |
| `confirmPassword` | `confirmPassword` | `password` | `new-password` | Do not trim automatically. |
| `secretQuestionId` | `secretQuestionId` | `select` | Off | Send selected UUID. |
| `secretAnswer` | `secretAnswer` | `password` or masked text | Off | Trim according to documented recovery rules. |

The frontend must not add fields that are not present in the request contract.

---

## 28. Frontend Validation Schema

Example using Zod:

```typescript
import { z } from "zod";

const noControlCharacters = /^[^\u0000-\u001F\u007F]*$/u;

export const signupSchema = z
  .object({
    firstName: z
      .string()
      .trim()
      .min(1, "First name is required.")
      .max(100, "First name must not exceed 100 characters.")
      .regex(noControlCharacters, "First name contains unsupported characters."),

    lastName: z
      .string()
      .trim()
      .min(1, "Last name is required.")
      .max(100, "Last name must not exceed 100 characters.")
      .regex(noControlCharacters, "Last name contains unsupported characters."),

    biEmail: z
      .string()
      .trim()
      .email("Enter a valid BI email address.")
      .max(320, "Email must not exceed 320 characters."),

    password: z
      .string()
      .min(12, "Password must contain at least 12 characters.")
      .max(128, "Password must not exceed 128 characters."),

    confirmPassword: z.string().min(1, "Confirm your password."),

    secretQuestionId: z
      .string()
      .uuid("Select a valid secret question."),

    secretAnswer: z
      .string()
      .trim()
      .min(2, "Secret answer must contain at least 2 characters.")
      .max(255, "Secret answer must not exceed 255 characters.")
  })
  .superRefine((values, context) => {
    if (values.password !== values.confirmPassword) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["confirmPassword"],
        message: "Password and confirm password must match."
      });
    }

    if (values.password.toLocaleLowerCase() === values.biEmail.trim().toLocaleLowerCase()) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["password"],
        message: "Password must not be the same as your email address."
      });
    }
  });
```

Frontend validation improves feedback but does not replace backend validation.

---

## 29. Typed API Client

```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiErrorResponse
  ) {
    super(body.error.message);
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init.headers
    }
  });

  const body = await response.json();

  if (!response.ok) {
    throw new ApiError(response.status, body as ApiErrorResponse);
  }

  return body as T;
}
```

The client should safely handle non-JSON responses from gateways without exposing raw response content to users.

---

## 30. Correlation and Idempotency Utilities

```typescript
export function createCorrelationId(): string {
  return crypto.randomUUID();
}

export function createIdempotencyKey(): string {
  return crypto.randomUUID();
}
```

Rules:

- Generate a correlation ID for each logical page-load/API operation if one is not already available.
- Generate one idempotency key for a single logical signup attempt.
- Reuse that key only when retrying the same submission after a transport uncertainty.
- Generate a new key after the user changes the request data or explicitly starts a new attempt.
- Never derive keys from email, password, secret answer, or other personal data.

---

## 31. Auth API Functions

```typescript
export function getSecretQuestions(
  correlationId: string,
  signal?: AbortSignal
): Promise<SecretQuestionsResponse> {
  return apiRequest<SecretQuestionsResponse>(
    "/api/v1/auth/secret-questions",
    {
      method: "GET",
      signal,
      headers: {
        "X-Correlation-ID": correlationId
      }
    }
  );
}

export function signup(
  request: SignupRequest,
  correlationId: string,
  idempotencyKey: string,
  signal?: AbortSignal
): Promise<SignupSuccessResponse> {
  return apiRequest<SignupSuccessResponse>(
    "/api/v1/auth/signup",
    {
      method: "POST",
      signal,
      headers: {
        "Content-Type": "application/json",
        "X-Correlation-ID": correlationId,
        "Idempotency-Key": idempotencyKey
      },
      body: JSON.stringify(request)
    }
  );
}
```

---

## 32. Secret Question Loading Hook

The hook must expose loading, success, empty, and error states.

```typescript
export interface UseSecretQuestionsResult {
  questions: SecretQuestion[];
  isLoading: boolean;
  isError: boolean;
  isEmpty: boolean;
  errorMessage?: string;
  correlationId?: string;
  reload: () => void;
}
```

Behavior:

1. Request questions when the page loads.
2. Abort the request when the component unmounts.
3. Prevent stale responses from replacing newer state.
4. Do not render stale inactive questions after a reload failure unless the product explicitly accepts cached data.
5. Disable signup if the returned list is empty.
6. Provide a retry action for retryable failures.

---

## 33. Signup Submission Hook

```typescript
export interface UseSignupResult {
  submitSignup: (values: SignupFormValues) => Promise<void>;
  isSubmitting: boolean;
  formError?: string;
  correlationId?: string;
}
```

Responsibilities:

- Build the normalized request payload.
- Generate correlation and idempotency values.
- Prevent duplicate clicks.
- Call the signup endpoint.
- Map server field errors into React Hook Form.
- Clear sensitive fields after selected failures.
- Initialize authentication state after success.
- Navigate to the configured post-signup route.
- Preserve the correlation ID for support-facing error display.

---

## 34. Request Payload Mapping

```typescript
function toSignupRequest(values: SignupFormValues): SignupRequest {
  return {
    firstName: values.firstName.trim(),
    lastName: values.lastName.trim(),
    biEmail: values.biEmail.trim().toLocaleLowerCase(),
    password: values.password,
    confirmPassword: values.confirmPassword,
    secretQuestionId: values.secretQuestionId,
    secretAnswer: values.secretAnswer.trim()
  };
}
```

Do not include `role`, `status`, `emailVerified`, IDs generated by the server, or UI-only values.

---

## 35. Server Error Mapping

```typescript
const supportedFields = new Set<keyof SignupFormValues>([
  "firstName",
  "lastName",
  "biEmail",
  "password",
  "confirmPassword",
  "secretQuestionId",
  "secretAnswer"
]);

export function applyApiFieldErrors(
  error: ApiErrorResponse,
  setError: (
    name: keyof SignupFormValues,
    error: { type: string; message: string }
  ) => void
): void {
  for (const fieldError of error.error.fieldErrors ?? []) {
    if (supportedFields.has(fieldError.field as keyof SignupFormValues)) {
      setError(fieldError.field as keyof SignupFormValues, {
        type: "server",
        message: fieldError.message
      });
    }
  }
}
```

Recommended top-level mapping:

```typescript
switch (apiError.body.error.code) {
  case "EMAIL_ALREADY_REGISTERED":
    setError("biEmail", {
      type: "server",
      message: apiError.body.error.message
    });
    break;

  case "INVALID_SECRET_QUESTION":
    setError("secretQuestionId", {
      type: "server",
      message: apiError.body.error.message
    });
    reloadSecretQuestions();
    break;

  case "RATE_LIMIT_EXCEEDED":
  case "SIGNUP_CONFIGURATION_ERROR":
  case "INTERNAL_SERVER_ERROR":
    setFormError(apiError.body.error.message);
    break;

  default:
    applyApiFieldErrors(apiError.body, setError);
    setFormError(apiError.body.error.message);
}
```

Never display raw stack traces, HTML gateway pages, SQL errors, or untrusted response content.

---

## 36. Authentication State Initialization

Recommended state shape:

```typescript
export interface AuthState {
  isAuthenticated: boolean;
  user: AuthenticatedUser | null;
  accessToken: string | null;
  expiresAt: number | null;
  setAuthenticatedSession: (
    user: AuthenticatedUser,
    authentication: AuthenticationResult
  ) => void;
  clearSession: () => void;
}
```

Initialization:

```typescript
const expiresAt = Date.now() + authentication.expiresIn * 1000;

authStore.setAuthenticatedSession(user, authentication);
```

For this scope:

- Keep the access token in memory unless the approved identity architecture specifies a safer cookie-based design.
- Never store tokens in URLs.
- Do not log JWTs.
- Do not decode a token and treat its content as proof of authorization; the backend remains authoritative.
- Route authorization may use user role as a UX hint, but protected APIs must enforce access.

---

## 37. React Component Responsibilities

### 37.1 `SignupPage`

- Provides page layout and title.
- Redirects already authenticated users.
- Hosts the signup form.
- Supplies navigation to the future login page.
- Applies responsive Tailwind layout.

### 37.2 `SignupForm`

- Owns React Hook Form integration.
- Connects the Zod resolver.
- Renders fields and error messages.
- Loads secret questions.
- Calls the signup mutation.
- Controls submission and disabled states.
- Focuses the first invalid field.

### 37.3 Shared Inputs

Shared input components must support:

- `id`, `name`, and associated `<label>`.
- `aria-invalid`.
- `aria-describedby` for errors and help text.
- Disabled and read-only states.
- Visible focus styling.
- Error styling.
- Forwarded refs.
- Password visibility toggles where appropriate.

---

## 38. Signup Form Skeleton

```tsx
export function SignupForm(): JSX.Element {
  const {
    register,
    handleSubmit,
    setError,
    resetField,
    formState: { errors, isSubmitting }
  } = useForm<SignupFormValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      firstName: "",
      lastName: "",
      biEmail: "",
      password: "",
      confirmPassword: "",
      secretQuestionId: "",
      secretAnswer: ""
    }
  });

  const secretQuestions = useSecretQuestions();

  const onSubmit = async (values: SignupFormValues) => {
    try {
      await submitSignup(values);
    } catch {
      resetField("password");
      resetField("confirmPassword");
      resetField("secretAnswer");
    }
  };

  const formDisabled =
    isSubmitting ||
    secretQuestions.isLoading ||
    secretQuestions.isError ||
    secretQuestions.isEmpty;

  return (
    <form
      noValidate
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-5"
    >
      {/* Render accessible fields and messages here. */}
      <button
        type="submit"
        disabled={formDisabled}
        className="inline-flex w-full items-center justify-center rounded-lg bg-blue-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isSubmitting ? "Creating account..." : "Create account"}
      </button>
    </form>
  );
}
```

The final implementation must render all fields and not leave credentials in debug output.

---

## 39. Tailwind CSS Layout

Recommended overall page layout:

```tsx
<main className="min-h-screen bg-slate-50 px-4 py-10 sm:px-6 lg:px-8">
  <div className="mx-auto w-full max-w-xl">
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">
          Create your account
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Register to access the Governance Procedure Document Automator.
        </p>
      </header>

      <SignupForm />
    </section>
  </div>
</main>
```

### 39.1 Responsive Behavior

- Single-column form on mobile.
- First and last name may use a two-column grid from the `sm` breakpoint.
- Maintain minimum touch-target sizes.
- Avoid horizontal scrolling at supported viewport widths.
- Keep error messages close to fields without causing layout overlap.

### 39.2 Visual States

- Default: slate borders and readable labels.
- Focus: visible ring with sufficient contrast.
- Invalid: red border and inline text, not color alone.
- Disabled: reduced opacity and `not-allowed` cursor.
- Loading: spinner plus text.
- Success: route transition or accessible success status before navigation.

---

## 40. Accessibility Requirements

- Use semantic headings and form elements.
- Every field must have a visible associated label.
- Mark required fields in text or accessible descriptions.
- Use `aria-invalid="true"` for invalid fields.
- Connect error messages with `aria-describedby`.
- Use an `aria-live="polite"` region for form-level status messages.
- Use `role="alert"` for blocking submission errors when appropriate.
- Keep keyboard focus visible.
- Ensure users can operate password toggles and dropdowns by keyboard.
- Move focus to the first invalid field on submit.
- Do not rely on placeholders as labels.
- Ensure color contrast follows the organization's accessibility standard.
- Keep logical DOM and tab order.
- Do not automatically time out or remove error messages before users can read them.

---

## 41. Frontend Security Requirements

The frontend must never persist these values:

```text
password
confirmPassword
secretAnswer
```

They must not appear in:

- `localStorage`.
- `sessionStorage`.
- Persisted Redux/Zustand state.
- URL query parameters or fragments.
- Browser history state.
- Analytics events.
- Console logs.
- Error tracking breadcrumbs.
- Request replay tools.
- Form autosave.

Additional requirements:

- Use masked fields for password and secret answer.
- Do not copy credential values into general component state unnecessarily.
- Clear sensitive fields after selected failed submissions.
- Disable credential capture in session-replay tooling.
- Prevent the API client from logging request bodies.
- Use secure deployment headers, including an appropriate Content Security Policy.
- Do not treat frontend role checks as authorization.

---

## 42. UI State Matrix

| State | Secret Question Control | Submit Button | User Message |
|---|---|---|---|
| Initial/loading | Disabled with loading option | Disabled | “Loading secret questions…” |
| Questions loaded | Enabled | Enabled when form is valid | Normal form guidance. |
| Empty question list | Disabled | Disabled | “Registration is temporarily unavailable.” |
| Question API error | Disabled | Disabled | Error plus retry action. |
| Form invalid | Enabled | May remain enabled for submit validation | Inline field errors. |
| Signup submitting | Disabled | Disabled with spinner | “Creating account…” |
| Signup success | Disabled | Disabled | Success status, then redirect. |
| Duplicate email | Enabled | Enabled after correction | Inline BI Email error. |
| Invalid question | Reloading | Disabled during reload | Inline question error. |
| Rate limited | Enabled or temporarily disabled | Disabled according to retry policy | Safe retry-time message. |
| Server/configuration failure | Disabled if non-retryable | Disabled or retry-enabled as appropriate | Safe form-level message with correlation ID. |

---

## 43. Frontend Page Flow

```text
User opens /signup
        |
        v
React renders page shell
        |
        v
GET /api/v1/auth/secret-questions
        |
        +---- loading ----> disable dropdown and submit
        |
        +---- error ------> show retry state
        |
        +---- empty ------> show configuration message; disable signup
        |
        v
Populate dropdown using questionId/questionText
        |
        v
User enters profile and credential data
        |
        v
Client validation
        |
        +---- invalid ----> show field errors; focus first invalid field
        |
        v
Normalize request-safe values
        |
        v
Generate correlation ID and idempotency key
        |
        v
POST /api/v1/auth/signup
        |
        +---- 422 --------> map field errors
        +---- 409 email --> attach BI Email error
        +---- 422 question -> reload questions
        +---- 429 --------> show retry guidance
        +---- 5xx --------> show safe general error and correlation ID
        |
        v
201 Created
        |
        v
Initialize in-memory authentication state
        |
        v
Navigate to configured authenticated landing page
```

---

## 44. Full End-to-End Sequence

```text
User          React UI        Auth API        Signup Service      PostgreSQL       Token Service
 |               |               |                  |                  |                 |
 | open signup   |               |                  |                  |                 |
 |-------------->|               |                  |                  |                 |
 |               | GET questions |                  |                  |                 |
 |               |-------------->| query active     |----------------->|                 |
 |               |               |<------------------------------------|                 |
 |               |<--------------| 200 items        |                  |                 |
 | fill form     |               |                  |                  |                 |
 |-------------->|               |                  |                  |                 |
 | submit        |               |                  |                  |                 |
 |-------------->| validate      |                  |                  |                 |
 |               | POST signup   |                  |                  |                 |
 |               |-------------->| validate/request|----------------->|                 |
 |               |               |                  | load question    |---------------->|
 |               |               |                  | load role        |---------------->|
 |               |               |                  | hash credentials |                 |
 |               |               |                  | begin transaction|---------------->|
 |               |               |                  | insert user      |---------------->|
 |               |               |                  | insert security  |---------------->|
 |               |               |                  | insert audit     |---------------->|
 |               |               |                  | commit           |---------------->|
 |               |               |                  | create JWT       |------------------------------>|
 |               |               |                  |<------------------------------|
 |               |<--------------| 201 user + token |                  |                 |
 |               | set auth state|                  |                  |                 |
 |               | redirect      |                  |                  |                 |
 |<--------------|               |                  |                  |                 |
```

---

## 45. OpenAPI Outline

```yaml
paths:
  /api/v1/auth/secret-questions:
    get:
      tags: [Authentication]
      summary: Retrieve active secret questions
      operationId: getSecretQuestions
      security: []
      responses:
        "200":
          description: Active secret questions returned
        "429":
          description: Rate limit exceeded
        "500":
          description: Secret questions unavailable

  /api/v1/auth/signup:
    post:
      tags: [Authentication]
      summary: Register a new user
      operationId: signupUser
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/SignupRequest"
      responses:
        "201":
          description: User registered successfully
        "400":
          description: Malformed request
        "409":
          description: Email already registered or idempotency conflict
        "422":
          description: Validation failed
        "429":
          description: Rate limit exceeded
        "500":
          description: Unexpected server error
        "503":
          description: Signup configuration unavailable

components:
  schemas:
    SignupRequest:
      type: object
      additionalProperties: false
      required:
        - firstName
        - lastName
        - biEmail
        - password
        - confirmPassword
        - secretQuestionId
        - secretAnswer
      properties:
        firstName:
          type: string
          minLength: 1
          maxLength: 100
        lastName:
          type: string
          minLength: 1
          maxLength: 100
        biEmail:
          type: string
          format: email
          maxLength: 320
        password:
          type: string
          format: password
          minLength: 12
          maxLength: 128
          writeOnly: true
        confirmPassword:
          type: string
          format: password
          minLength: 12
          maxLength: 128
          writeOnly: true
        secretQuestionId:
          type: string
          format: uuid
        secretAnswer:
          type: string
          minLength: 2
          maxLength: 255
          writeOnly: true
```

---

## 46. Backend Acceptance Criteria

### 46.1 Secret Questions

- The endpoint returns only active questions.
- Questions are sorted by display order and then text.
- Internal fields are not exposed.
- An empty list returns `200`.
- Correlation IDs are accepted or generated and returned.
- Rate limiting is applied.

### 46.2 Signup

- A valid request creates one `users` record and one `user_security` record.
- The active default `REGULAR_USER` role is assigned.
- Client-supplied privilege fields are rejected.
- Email uniqueness is case-insensitive.
- `confirmPassword` is validated but never stored.
- Password and secret answer are independently hashed.
- Inactive or nonexistent questions are rejected.
- User and security inserts are atomic.
- Successful signup creates an audit event.
- Failed signup leaves no partial user record.
- JWT creation occurs only after transaction commit.
- The response contains no password or recovery data.
- Safe standardized errors are returned.

---

## 47. Frontend Acceptance Criteria

### 47.1 Form and Data Mapping

- All seven required controls are present.
- Field names exactly match the API contract.
- Secret question options use UUID values and text labels.
- No role or administrative input is rendered or submitted.
- Request normalization matches the documented rules.

### 47.2 User Experience

- Loading, empty, error, populated, submitting, and success states are implemented.
- Duplicate submission is prevented.
- Field-level errors are rendered next to relevant controls.
- Form-level errors are accessible.
- The first invalid field receives focus.
- Question-list errors provide a retry action.
- Invalidated questions trigger a list reload.
- Successful signup initializes auth state and redirects.

### 47.3 Security

- Credentials are never persisted in browser storage.
- Credentials and JWTs are not logged.
- Sensitive fields are masked.
- Sensitive fields are cleared after appropriate failures.
- Correlation IDs and idempotency keys contain no personal data.
- Frontend authorization checks are not treated as backend security.

### 47.4 Accessibility and Responsiveness

- All fields have visible labels.
- Errors are programmatically associated with inputs.
- Keyboard-only operation is supported.
- Focus styles are visible.
- Layout works on mobile and desktop viewports.
- Error states do not rely on color alone.

---

## 48. Test Scenarios

### 48.1 Backend Unit Tests

- Name normalization and control-character rejection.
- Email normalization and domain-policy checks.
- Password length and email-equality checks.
- Password-confirmation mismatch.
- Secret-answer normalization.
- Secret-question UUID validation.
- Default-role lookup.
- JWT claim generation.
- Safe audit-detail creation.

### 48.2 Backend Integration Tests

- Retrieve active questions in the correct order.
- Exclude inactive questions.
- Return an empty active-question list.
- Create all required records for a valid signup.
- Reject duplicate email with different letter casing.
- Reject a nonexistent question UUID.
- Reject a question deactivated after page load.
- Roll back if `user_security` insertion fails.
- Prevent role injection.
- Verify idempotent retry behavior.
- Verify rate-limit headers and `Retry-After`.
- Verify no credentials appear in logs, audit events, or traces.

### 48.3 Frontend Unit and Component Tests

- Render all form fields.
- Display secret-question loading state.
- Populate options from an API response.
- Disable form for an empty question list.
- Render question-loading failure and retry action.
- Validate required fields.
- Validate email format.
- Validate password length.
- Validate matching passwords.
- Validate secret-answer limits.
- Submit the normalized request payload.
- Include correlation and idempotency headers.
- Disable submit while processing.
- Map backend field errors.
- Handle duplicate email.
- Reload invalid secret questions.
- Clear sensitive fields after selected failures.
- Initialize auth state and navigate after success.

### 48.4 End-to-End Tests

- Complete successful signup and reach the authenticated landing route.
- Attempt duplicate signup and see the email error.
- Submit mismatched passwords and remain on the page.
- Experience a question deactivation race and select a refreshed question.
- Receive a rate-limit response and see retry guidance.
- Navigate and submit using only the keyboard.
- Verify responsive layout at mobile and desktop sizes.
- Verify credentials do not appear in browser storage.

### 48.5 Security Tests

- Reject unexpected properties and privilege injection.
- Test SQL injection strings safely.
- Test oversized JSON bodies.
- Test malformed UUIDs.
- Test script-like input rendering without XSS execution.
- Verify CSP and security-header behavior.
- Verify analytics and telemetry redaction.
- Verify session-replay masking.
- Verify token and credential absence from logs.

---

## 49. Observability

Backend telemetry should include:

- Request count and latency by endpoint and status.
- Rate-limit rejections.
- Validation-error category counts without credential values.
- Signup successes and failures.
- Database transaction failures.
- Hashing latency.
- JWT issuance failures.
- Correlation ID across logs, traces, and audit records.

Frontend telemetry may include:

- Page load outcome.
- Secret-question request success/failure.
- Signup outcome category.
- Client validation category counts.
- Navigation outcome.
- Correlation ID for failed requests.

Frontend telemetry must not include field values, email addresses, credentials, JWTs, question answers, or complete request/response bodies.

---

## 50. Deployment and Configuration

Frontend environment configuration:

```text
VITE_API_BASE_URL=https://<api-host>
VITE_POST_SIGNUP_ROUTE=/workspace
```

Backend configuration should include:

```text
DATABASE_URL
JWT_ISSUER
JWT_AUDIENCE
JWT_PRIVATE_KEY_REFERENCE
JWT_ACCESS_TOKEN_TTL_SECONDS=900
PASSWORD_HASH_CONFIGURATION
ALLOWED_BI_EMAIL_DOMAINS
SIGNUP_RATE_LIMIT
SECRET_QUESTION_RATE_LIMIT
REQUEST_BODY_SIZE_LIMIT
```

Secrets and private keys must not be embedded in source control or frontend builds.

CORS must allow only approved frontend origins and required headers, including:

- `Content-Type`
- `Accept`
- `X-Correlation-ID`
- `Idempotency-Key`
- `Authorization` for later protected API calls

---

## 51. Development Notes

- Keep the signup service independent from the FastAPI route.
- Generate frontend API types from OpenAPI when the project establishes a generation pipeline.
- Keep frontend and backend validation messages aligned, while treating backend rules as authoritative.
- Centralize error-code mapping.
- Preserve unknown error codes as safe generic failures rather than crashing the UI.
- Avoid duplicating password-policy constants across multiple frontend files.
- Add automated race-condition tests for simultaneous registration using the same email.
- Use database migrations for all schema and seed changes.
- Treat the secret-question recovery approach as a stated requirement, while allowing stronger recovery methods to be added later.
- Record architecture decisions for final token storage, identity-provider integration, CAPTCHA, and email verification.

---

## 52. Final Endpoint Summary

```http
GET  /api/v1/auth/secret-questions
POST /api/v1/auth/signup
```

The complete design separates user profile data, authorization roles, managed recovery questions, credential hashes, and audit history. The frontend provides a typed, accessible, responsive React experience, while FastAPI and PostgreSQL retain authority over validation, role assignment, account creation, security, auditing, and JWT issuance.
