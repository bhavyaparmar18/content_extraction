-- 0001: every application table in one database, with the cross-table links enforced.
-- Merged from the former auth.db, sop_records.db, template_records.db, gwp_guides.db and migrations.db.
-- File paths are stored relative to data/ (see app/db/paths.py).

-- ── Auth ─────────────────────────────────────────────────────────────

CREATE TABLE roles (
    role_id     TEXT PRIMARY KEY,
    role_code   TEXT NOT NULL UNIQUE,
    role_name   TEXT NOT NULL UNIQUE,
    description TEXT,
    is_default  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE secret_questions (
    secret_question_id TEXT PRIMARY KEY,
    question_code      TEXT NOT NULL UNIQUE,
    question_text      TEXT NOT NULL UNIQUE,
    display_order      INTEGER NOT NULL DEFAULT 0,
    is_active          INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX ix_secret_questions_active_order ON secret_questions (is_active, display_order, question_text);

CREATE TABLE users (
    user_id           TEXT PRIMARY KEY,
    first_name        TEXT NOT NULL,
    last_name         TEXT NOT NULL,
    bi_email          TEXT NOT NULL,
    role_id           TEXT NOT NULL REFERENCES roles(role_id),
    status            TEXT NOT NULL DEFAULT 'ACTIVE',
    is_email_verified INTEGER NOT NULL DEFAULT 0,
    email_verified_at TEXT,
    last_login_at     TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    deactivated_at    TEXT
);
CREATE UNIQUE INDEX uq_users_bi_email_ci ON users (lower(bi_email));
CREATE INDEX ix_users_role ON users (role_id);

CREATE TABLE user_security (
    user_id                  TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    password_hash            TEXT NOT NULL,
    secret_question_id       TEXT NOT NULL REFERENCES secret_questions(secret_question_id),
    secret_answer_hash       TEXT NOT NULL,
    failed_login_attempts    INTEGER NOT NULL DEFAULT 0,
    is_locked                INTEGER NOT NULL DEFAULT 0,
    locked_at                TEXT,
    lock_expires_at          TEXT,
    lock_reason              TEXT,
    password_changed_at      TEXT NOT NULL,
    secret_answer_changed_at TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL
);

CREATE TABLE user_sessions (
    session_id             TEXT PRIMARY KEY,
    user_id                TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    refresh_token_hash     TEXT NOT NULL UNIQUE,
    token_family_id        TEXT NOT NULL,
    remember_me            INTEGER NOT NULL DEFAULT 0,
    expires_at             TEXT NOT NULL,
    last_used_at           TEXT,
    revoked_at             TEXT,
    revoked_reason         TEXT,
    replaced_by_session_id TEXT REFERENCES user_sessions(session_id),
    ip_address             TEXT,
    user_agent             TEXT,
    created_at             TEXT NOT NULL
);
CREATE INDEX ix_user_sessions_user_active ON user_sessions (user_id, expires_at) WHERE revoked_at IS NULL;
CREATE INDEX ix_user_sessions_token_family ON user_sessions (token_family_id);

CREATE TABLE audit_events (
    audit_event_id TEXT PRIMARY KEY,
    actor_user_id  TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    event_type     TEXT NOT NULL,
    action         TEXT NOT NULL,
    resource_type  TEXT,
    resource_id    TEXT,
    outcome        TEXT NOT NULL,
    error_code     TEXT,
    correlation_id TEXT NOT NULL,
    event_details  TEXT NOT NULL DEFAULT '{}',
    ip_address     TEXT,
    user_agent     TEXT,
    occurred_at    TEXT NOT NULL
);
CREATE INDEX ix_audit_events_correlation_id ON audit_events (correlation_id);
CREATE INDEX ix_audit_events_actor_time ON audit_events (actor_user_id, occurred_at DESC);

-- ── SOP, template and GWP versions ───────────────────────────────────

CREATE TABLE sop_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           TEXT    NOT NULL,  -- the in-memory extraction batch (JobManager), not a migration job
    document_uid     TEXT    NOT NULL,
    document_number  TEXT,
    document_name    TEXT,
    document_title   TEXT,
    document_version TEXT,
    document_type    TEXT,
    file_type        TEXT,
    language         TEXT    DEFAULT 'en',
    page_count       INTEGER DEFAULT 0,
    gpdat_version    INTEGER DEFAULT 0,
    status           TEXT    NOT NULL DEFAULT 'in_review'
                             CHECK(status IN ('in_review','approved','rejected')),
    source_filename  TEXT,
    output_path      TEXT,
    units_path       TEXT,
    migrated_path    TEXT,
    migrated_job_id  TEXT    REFERENCES migration_jobs(job_id) ON DELETE SET NULL,
    migrated_at      TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(document_uid, gpdat_version)
);
CREATE INDEX idx_sop_uid ON sop_records(document_uid);
CREATE INDEX idx_sop_status ON sop_records(status);
CREATE INDEX idx_sop_job ON sop_records(job_id);
CREATE INDEX idx_sop_migrated_job ON sop_records(migrated_job_id);

CREATE TABLE template_records (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    template_uid       TEXT    NOT NULL,
    template_name      TEXT    NOT NULL,
    template_version   INTEGER DEFAULT 1,
    file_type          TEXT    DEFAULT 'docx',
    file_size_bytes    INTEGER DEFAULT 0,
    source_filename    TEXT,
    upload_path        TEXT,
    output_path        TEXT,
    total_sections     INTEGER DEFAULT 0,
    total_elements     INTEGER DEFAULT 0,
    total_instructions INTEGER DEFAULT 0,
    total_icons        INTEGER DEFAULT 0,
    total_callouts     INTEGER DEFAULT 0,
    global_rules_json  TEXT,
    status             TEXT    NOT NULL DEFAULT 'uploaded'
                               CHECK(status IN ('uploaded','extracting','ready','failed')),
    model_path         TEXT,
    normalized_path    TEXT,
    readiness_status   TEXT,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL,
    UNIQUE(template_uid, template_version)
);
CREATE INDEX idx_tpl_uid ON template_records(template_uid);
CREATE INDEX idx_tpl_status ON template_records(status);

CREATE TABLE gwp_guides (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    guide_id         TEXT    NOT NULL,
    guide_name       TEXT    NOT NULL,
    version          INTEGER NOT NULL DEFAULT 1,
    file_type        TEXT,
    file_size_bytes  INTEGER DEFAULT 0,
    source_filename  TEXT,
    upload_path      TEXT,
    units_path       TEXT,
    rules_path       TEXT,
    report_path      TEXT,
    total_units      INTEGER DEFAULT 0,
    total_rules      INTEGER DEFAULT 0,
    approved_rules   INTEGER DEFAULT 0,
    candidate_rules  INTEGER DEFAULT 0,
    prompt_version   TEXT,
    model            TEXT,
    error            TEXT,
    status           TEXT    NOT NULL DEFAULT 'uploaded'
                             CHECK(status IN ('uploaded','parsed','extracting','in_review','approved','failed')),
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(guide_id, version)
);
CREATE INDEX idx_gwp_guide ON gwp_guides(guide_id);
CREATE INDEX idx_gwp_status ON gwp_guides(status);

-- ── Migration v2 jobs ────────────────────────────────────────────────
-- An SOP, template or GWP version a job uses cannot be deleted (RESTRICT);
-- the stores check first and raise RecordInUseError with the job ids.

CREATE TABLE migration_jobs (
    job_id           TEXT PRIMARY KEY,
    sop_record_id    INTEGER NOT NULL REFERENCES sop_records(id) ON DELETE RESTRICT,
    template_id      TEXT    NOT NULL,  -- template_uid
    template_version INTEGER NOT NULL,
    gwp_id           TEXT,              -- optional: NULL means no GWP
    gwp_version      INTEGER,
    mode             TEXT    NOT NULL,
    status           TEXT    NOT NULL,
    created_by       TEXT    REFERENCES users(user_id) ON DELETE SET NULL,
    error            TEXT,
    failed_stage     TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    FOREIGN KEY (template_id, template_version)
        REFERENCES template_records(template_uid, template_version) ON DELETE RESTRICT,
    FOREIGN KEY (gwp_id, gwp_version)
        REFERENCES gwp_guides(guide_id, version) ON DELETE RESTRICT
);
CREATE INDEX idx_mig_status ON migration_jobs(status);
CREATE INDEX idx_mig_sop ON migration_jobs(sop_record_id);
CREATE INDEX idx_mig_template ON migration_jobs(template_id, template_version);
CREATE INDEX idx_mig_gwp ON migration_jobs(gwp_id, gwp_version);
CREATE INDEX idx_mig_created_by ON migration_jobs(created_by);

CREATE TABLE migration_sections (
    job_id            TEXT    NOT NULL REFERENCES migration_jobs(job_id) ON DELETE CASCADE,
    target_section_id TEXT    NOT NULL,
    position          INTEGER NOT NULL DEFAULT 0,
    status            TEXT    NOT NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    PRIMARY KEY (job_id, target_section_id)
);

-- created_by / actor stay free text: they also hold "system".
CREATE TABLE migration_artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT    NOT NULL REFERENCES migration_jobs(job_id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL,
    scope      TEXT    NOT NULL DEFAULT '',
    version    INTEGER NOT NULL,
    path       TEXT    NOT NULL,
    sha256     TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    created_by TEXT,
    UNIQUE (job_id, kind, scope, version)
);
CREATE INDEX idx_mig_art_job ON migration_artifacts(job_id);

CREATE TABLE migration_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL REFERENCES migration_jobs(job_id) ON DELETE CASCADE,
    at          TEXT NOT NULL,
    actor       TEXT,
    event       TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT,
    detail      TEXT
);
CREATE INDEX idx_mig_evt_job ON migration_events(job_id);
