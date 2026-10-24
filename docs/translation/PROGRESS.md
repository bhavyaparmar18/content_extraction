# Translation: Progress Log

Handoff log for `IMPLEMENTATION_PLAN.md`. Append one entry at the end of each phase or session. At the start of a session, read the plan's relevant phase and the latest entry here.

Entry format:

```
## YYYY-MM-DD: Phase TN (name): done / partial
- Done:
- Files touched:
- Open issues / decisions:
- Next step:
```

---

## 2026-10-25: Planning: done
- Done: explored the migration v2 pipeline, the frontend and the shared infrastructure, then wrote `IMPLEMENTATION_PLAN.md` (phases T1 to T9).
- Decisions (user, 2026-10-25):
  - **Languages (8):** zh-CN, fr-FR, de-DE, it-IT, ja-JP, pt-BR, es-ES, el-GR. The source is always English.
  - **Trigger:** translation runs on a **completed** migration, one translation job per language.
  - **Engine:** the existing LLM path (`ChainFactory`, `LLMRateLimiter`, versioned prompt, audit).
  - **Review:** every translation is reviewed and approved by a human before export.
  - **Language template:** a full `.docx` per language. Only its first page, headers and footers are used; the rest is ignored. It is **optional**: without one, the English first page, header and footer are kept as they are. Only one or two exist today.
  - **Glossary:** per language and **optional**. Without one, the LLM translates freely. With one, its terms are mandatory (in the prompt and in the QA check). None exist yet.
  - **Scope:** text inside images is out of scope (the next plan).
- Open issues / decisions:
  - Confirm Spanish = `es-ES` (Spain).
  - Template fixed text (headings, labels) is translated by the LLM.
  - There is no cross-job translation memory yet.
- Next step: T1. Write `app/schemas/v2/translation.py` and `app/db/migrations/0002_translation.sql`. Before saving the SQL file, check whether `uvicorn --reload` is running.

## 2026-10-25: Phase T1 (contracts, schema, stores): done
- Done:
  - **Contracts** (`app/schemas/v2/translation.py`, exported from `app.schemas.v2`): `LanguageCode`, `GlossaryEntry`/`Glossary`, `Segment`/`SegmentLocator`/`SegmentKind`/`SegmentOrigin`, `TranslationSet`, `TranslationJob`/`TranslationStatus`. The glossary and the language template are optional on a job. Rules and conventions are in `docs/translation/CONTRACTS.md`; the examples are in `docs/translation/examples/`.
  - **New `ArtifactKind`s:** `segments`, `translation`, `glossary`, `front_matter`.
  - **Languages** (`app/services/translation/languages.py`): identity only, i.e. name, Word code, script and East Asian flag. There are no style rules.
  - **Schema** `0002_translation.sql`: `glossaries`, `language_templates`, `translation_jobs` (nullable, RESTRICT foreign keys to the glossary and the language template; RESTRICT to `migration_jobs`), `translation_artifacts` and `translation_events`.
  - **Stores:**
    - `VersionedRecordStore` (`app/stores/versioned_store.py`) is the GWP-style versioned upload table: race-free versions, relative paths, column whitelists, and delete blocked while a translation job uses the version.
    - `GlossaryStore` and `LanguageTemplateStore` build on it.
    - `TranslationStore` mirrors `MigrationStore`: jobs, compare-and-swap `set_status`, `approve` (only from REVIEW_PENDING, records who and when), artifacts and events.
  - `ArtifactWriter` now takes any store with `add_next_artifact` (the `ArtifactIndex` protocol), so translation jobs reuse it over `settings.translation_dir`.
  - `RecordInUseError` takes `job_kind` ("migration" or "translation").
  - **Settings:** `translation_dir`, `glossary_dir`, `glossary_upload_dir`, `glossary_allowed_extensions` (`.csv`, `.xlsx`), `language_template_dir`, `language_template_upload_dir`.
- Files touched:
  - New: `app/schemas/v2/translation.py`, `app/services/translation/{__init__,languages}.py`, `app/db/migrations/0002_translation.sql`, `app/stores/{versioned_store,glossary_store,language_template_store,translation_store}.py`, `docs/translation/{CONTRACTS.md,examples/*}`, `tests/test_translation_{contracts,stores}.py`.
  - Changed: `app/schemas/v2/{__init__,job}.py`, `app/services/migration_v2/artifacts.py`, `app/db/__init__.py`, `app/config/settings.py`, `tests/test_app_db.py` (schema version 2, new tables).
- Tests: 29 new tests (`test_translation_contracts.py`, `test_translation_stores.py`). Full suite: 593 passed, 14 skipped, 1 failed. The failure is the known `test_samples_pass_inspection` on `BI-VQD-10643-S (1).docx` (Text completeness WARN, an extraction issue recorded in the migration v2 PROGRESS; unrelated).
- Open issues / decisions:
  - The real `data/app.db` gets schema 2 (new tables only, nothing existing changes) the next time the server starts. The dev server was not running during T1.
  - The stores are not yet wired in `app/main.py`; T2 does that with the glossary API.
- Next step: T2. `app/services/translation/glossary.py`: parse CSV/XLSX with the columns `source_term`, `target_term`, `note`, `case_sensitive`, `do_not_translate`, plus an optional "style notes" sheet or column (add `openpyxl`). Then the term matcher (case, word boundaries, plurals; substring for zh/ja), the upload/edit/approve API under `/api/v1/translations/glossaries`, and store wiring in `main.py`.

## 2026-10-25: Phase T2 (glossary management): done
- Done:
  - **`app/services/translation/glossary.py`**, file reading:
    - Reads CSV (comma, semicolon or tab; UTF-8 with or without BOM, UTF-16 from Excel's "Unicode text", or Windows-1252) and XLSX.
    - XLSX: the terms come from a sheet named Glossary or Terms (otherwise the first sheet). An optional "Style notes" sheet becomes `Glossary.style_notes`.
    - The header map is tolerant: `source`/`English`; `target`/`translation`/the language's name or code; `notes`/`comment`; `dnt`… Flags accept yes/no, true/false, 1/0 and x.
    - A file with any bad row is refused as a whole. `GlossaryInvalid.problems` lists every reason with its spreadsheet row (missing target, bad flag, duplicate term, do-not-translate with a different target).
    - Export to CSV (with a UTF-8 BOM, so Excel reads it) or XLSX; both round-trip.
  - **Matching** (in the same file):
    - `match_terms` / `terms_in` find terms in the English source: whole words, case-insensitive unless case-sensitive, any whitespace between words, English plurals including -ies, longer terms first, no overlaps.
    - `target_present` checks a translation:
      - Chinese and Japanese: substring, whitespace ignored.
      - Latin languages and Greek: whole words, case- and accent-insensitive, and the last word may change its ending (`Abweichung`/`Abweichungen`, `απόκλιση`/`αποκλίσεις`; `Zweck` does not match `Zwei`).
      - Do-not-translate terms must appear exactly.
  - **`glossary_service.py`:**
    - `create_version` validates before writing, keeps the uploaded file, and refuses a language change for an existing `glossary_id` (409 `GLOSSARY_LANGUAGE_MISMATCH`).
    - `save_entries` edits in place while in review; on an approved version it creates the next version, so approved versions never change.
    - `approve` and `load` (the Glossary JSON at `entries_path` is the source of truth).
  - **API `app/api/translations.py`** (`/api/v1/translations`): `GET /languages` plus the glossary routes (listed in the plan's API section, as built). It is mounted in `app/main.py`, and the glossary, language-template and translation stores are on `app.state`.
  - **Dependency:** `openpyxl==3.1.5` in `pyproject.toml`, `uv.lock` and `requirements.txt`, installed in `venv`. `uv add` had stripped the blank lines in `pyproject.toml`; it was restored and the line added by hand, and `uv lock --check` is clean.
- Files touched:
  - New: `app/services/translation/{glossary,glossary_service}.py`, `app/api/translations.py`, `tests/test_translation_glossary.py`.
  - Changed: `app/main.py`, `pyproject.toml`, `uv.lock`, `requirements.txt`, `docs/translation/IMPLEMENTATION_PLAN.md` (API section).
- Tests: 29 new. Full suite: 622 passed, 14 skipped, 1 failed (the known `test_samples_pass_inspection` on `BI-VQD-10643-S (1).docx`).
- Open issues / decisions:
  - A glossary is optional on a job; a job may name only an **approved** version. This check comes with the job API in T4.
  - The matcher is a heuristic. Its misses on translations become HIGH issues for the reviewer (T5), never automatic edits.
  - German compounds that embed the term in the middle of a word (e.g. "Herstellungschargenprotokoll") are not found; the reviewer resolves those.
- Next step: T3. `app/services/translation/front_matter.py`:
  - extract the first page (up to the first section break, else the first page break) and the header and footer parts, with their images, from a language template `.docx`;
  - write a preview `.docx`;
  - `apply_front_matter(doc, front_matter)`;
  - language-template upload and preview API, with a ready status.
