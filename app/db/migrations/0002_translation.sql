-- Translation of completed migrations (docs/translation/IMPLEMENTATION_PLAN.md).
-- Glossaries and language templates are versioned like GWP guides and are both
-- optional on a translation job. A version a job uses cannot be deleted (RESTRICT);
-- the stores check first and raise RecordInUseError with the job ids.

CREATE TABLE glossaries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    glossary_id      TEXT    NOT NULL,
    name             TEXT    NOT NULL,
    language         TEXT    NOT NULL,
    version          INTEGER NOT NULL DEFAULT 1,
    file_type        TEXT,
    file_size_bytes  INTEGER DEFAULT 0,
    source_filename  TEXT,
    upload_path      TEXT,
    entries_path     TEXT,              -- the Glossary JSON: the source of truth after review
    total_entries    INTEGER DEFAULT 0,
    error            TEXT,
    status           TEXT    NOT NULL DEFAULT 'uploaded'
                             CHECK(status IN ('uploaded','in_review','approved','failed')),
    created_by       TEXT    REFERENCES users(user_id) ON DELETE SET NULL,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(glossary_id, version)
);
CREATE INDEX idx_gls_glossary ON glossaries(glossary_id);
CREATE INDEX idx_gls_language ON glossaries(language, status);

-- Only the first page, headers and footers of a language template are used.
CREATE TABLE language_templates (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id       TEXT    NOT NULL,
    name              TEXT    NOT NULL,
    language          TEXT    NOT NULL,
    version           INTEGER NOT NULL DEFAULT 1,
    file_size_bytes   INTEGER DEFAULT 0,
    source_filename   TEXT,
    upload_path       TEXT,
    front_matter_path TEXT,             -- the extracted first page, headers and footers
    preview_path      TEXT,             -- a .docx of the extracted parts, for the admin's check
    report_path       TEXT,
    error             TEXT,
    status            TEXT    NOT NULL DEFAULT 'uploaded'
                              CHECK(status IN ('uploaded','extracted','ready','failed')),
    created_by        TEXT    REFERENCES users(user_id) ON DELETE SET NULL,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    UNIQUE(template_id, version)
);
CREATE INDEX idx_ltpl_template ON language_templates(template_id);
CREATE INDEX idx_ltpl_language ON language_templates(language, status);

CREATE TABLE translation_jobs (
    job_id                    TEXT PRIMARY KEY,
    migration_job_id          TEXT    NOT NULL REFERENCES migration_jobs(job_id) ON DELETE RESTRICT,
    language                  TEXT    NOT NULL,
    glossary_id               TEXT,     -- optional: NULL means no glossary (free translation)
    glossary_version          INTEGER,
    language_template_id      TEXT,     -- optional: NULL keeps the English first page, headers and footers
    language_template_version INTEGER,
    status                    TEXT    NOT NULL,
    created_by                TEXT    REFERENCES users(user_id) ON DELETE SET NULL,
    approved_by               TEXT    REFERENCES users(user_id) ON DELETE SET NULL,
    approved_at               TEXT,
    error                     TEXT,
    failed_stage              TEXT,
    cancel_requested          INTEGER NOT NULL DEFAULT 0,
    created_at                TEXT    NOT NULL,
    updated_at                TEXT    NOT NULL,
    FOREIGN KEY (glossary_id, glossary_version)
        REFERENCES glossaries(glossary_id, version) ON DELETE RESTRICT,
    FOREIGN KEY (language_template_id, language_template_version)
        REFERENCES language_templates(template_id, version) ON DELETE RESTRICT
);
CREATE INDEX idx_trn_status ON translation_jobs(status);
CREATE INDEX idx_trn_migration ON translation_jobs(migration_job_id);
CREATE INDEX idx_trn_glossary ON translation_jobs(glossary_id, glossary_version);
CREATE INDEX idx_trn_ltpl ON translation_jobs(language_template_id, language_template_version);
CREATE INDEX idx_trn_created_by ON translation_jobs(created_by);

CREATE TABLE translation_artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT    NOT NULL REFERENCES translation_jobs(job_id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL,
    scope      TEXT    NOT NULL DEFAULT '',
    version    INTEGER NOT NULL,
    path       TEXT    NOT NULL,
    sha256     TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    created_by TEXT,
    UNIQUE (job_id, kind, scope, version)
);
CREATE INDEX idx_trn_art_job ON translation_artifacts(job_id);

CREATE TABLE translation_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL REFERENCES translation_jobs(job_id) ON DELETE CASCADE,
    at          TEXT NOT NULL,
    actor       TEXT,
    event       TEXT NOT NULL,
    from_status TEXT,
    to_status   TEXT,
    detail      TEXT
);
CREATE INDEX idx_trn_evt_job ON translation_events(job_id);
