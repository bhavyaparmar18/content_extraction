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
