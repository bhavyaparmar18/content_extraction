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

## 2026-10-25: Phase T3 (language template front matter): done
- Done:
  - **What the real files look like** (`data/template_output/Template_Main_GP_Docs_v1_normalized.docx`, and the rendered `MIG-20261019-7BF76968/docx_final_v1.docx`):
    - the first page is the first section, ending at a next-page section break, with `titlePg` and all three header and footer types;
    - the body section names only its two headers and inherits its footers from the first page's section;
    - the rendered final keeps the template's first page and header relationships, but one empty first-page paragraph is gone, so the first page is found by its break, never by a block count.
  - **`app/services/translation/front_matter.py`:**
    - `find_cover` (the first section break that starts a new page, or the first page break when earlier; "page break before" on the next paragraph also counts; a continuous break is an error). A section break's type is read from the *following* section's `sectPr`, as Word does.
    - `section_props`, `effective_refs` (Word's inheritance), `set_refs`.
    - `extract_front_matter` writes the package, preview and report. Problems: no first page, objects other than images and links, tracked changes, footnotes. Warnings: comments (removed), several sections, data-bound controls, header lists, no Han/kana or Greek letters for zh-CN, ja-JP and el-GR, an empty first page.
    - `apply_front_matter` and `front_matter_problems`, as described in `CONTRACTS.md`.
  - **`renumber_drawings(doc)`** moved from `_Renderer` to `render/xml.py`, so the renderer and the swap share it (no behaviour change).
  - **`language_template_service.py`:** `create_version` (refuses a language change for an existing `template_id`), `extract`, `load_report`, `mark_ready`.
  - **API:** the language-template routes in `app/api/translations.py`; `_resolve` now serves both stores. Setting `language_template_allowed_extensions = [".docx"]`.
  - **Contracts:** `FrontMatterReport`, `FrontMatterPart`, `FrontMatterSwap`, `CoverEnd`, with `examples/front_matter_report.json`.
  - **Checked on the real files:** the company template's front matter swaps into the rendered migration and the check is clean. Word opens the swapped document (20 pages) and the preview (3 pages: first page, body first page, body following page).
- Files touched:
  - New: `app/services/translation/{front_matter,language_template_service}.py`, `tests/test_translation_front_matter.py`, `docs/translation/examples/front_matter_report.json`.
  - Changed: `app/api/translations.py`, `app/schemas/v2/{translation,__init__}.py`, `app/config/settings.py`, `app/services/migration_v2/render/{xml,renderer}.py`, `tests/test_translation_contracts.py`, `docs/translation/{CONTRACTS,IMPLEMENTATION_PLAN}.md`.
- Tests: 29 new (the Word one is opt-in with `SOP_RUN_WORD_TESTS=1`; it passes). Full suite in `venv`: 650 passed, 15 skipped, 1 failed (the known `test_samples_pass_inspection` on `BI-VQD-10643-S (1).docx`). `.venv` (uv) lacks `openpyxl`, so the glossary tests do not collect there until `uv sync`.
- Open issues / decisions:
  - Body sections keep the English page geometry; only headers, footers and `titlePg` come from the language template. The first page takes the language template's whole section.
  - A style id in both files with different definitions keeps the English definition (a warning). Chinese and Japanese `eastAsia` fonts are T6.
  - Header and footer XML is compared byte for byte against the package. After Word re-saves a file the bytes differ (Word rewrites the parts), so the Word test compares texts.
  - No real language template has been uploaded yet; when one arrives, upload it and open the preview in Word.
- Next step: T4. `translation/segments.py`, `translation/orchestrator.py`, `translation/stages.py`, a `body_hook` parameter on `render_document`, and the job API. PREPARING snapshots the drafts, source, number map, assembly, glossary and the `front_matter` package (only `ready` language templates and `approved` glossaries may be named).

## 2026-10-25: Phase T3 follow-up (the real German and Spanish templates): done
- Done:
  - Tried `documents/Templates/Template Main GP Docs-de.docx` and `…-es.docx`. Both have the company template's shape: the first page ends at a next-page section break (7 blocks); the first page's section has first-page and default headers and footers (no even ones); the body section has its own two headers and inherits the footers. No problems, no warnings beyond the two below.
  - Swapped into `MIG-20261019-7BF76968/docx_final_v1.docx`: the check is clean. Word renders both, and pages 1–3 match the language templates (logo, header tables, German or Spanish page numbering over the whole document, footer).
  - **Style rule changed:** the language templates define `Header` and `Footer` with other spacing (12 pt above and below) and tab stops. A style that only the first page, headers and footers use now takes the language template's definition (`FrontMatterSwap.styles_replaced`); a style the body also uses (`Normal`) keeps the document's, with a warning. Before, every differing style kept the English definition, and the headers would not have looked like the language template's.
  - **`DOCVARIABLE` warning:** both templates were saved from a Vault document. Their Scope cell is a `DOCVARIABLE vault_r:document_scope__c:0` field, and `settings.xml` holds 24 document variables of another document (`BI-VQD-29892`). They are not copied; the extraction report now warns about such fields. Until Vault fills the variable, the cell shows its saved text `${vault:document_scope__c}`, or nothing once Word refreshes fields.
- Tests: 4 new (style rule, `DOCVARIABLE` warning, the German and Spanish templates against the rendered migration).
- Open issues / decisions:
  - The Spanish first-page header "Página 1 de N" wraps when N has two digits; the German one does not. That is in the template's header, which is copied unchanged.
  - The first page's section of both templates has an **English** default header ("Page 5 of 5 Document Name"). It only shows if the first page runs onto a second page.
  - Not yet registered in the app: `data/app.db` is still at schema version 1 (the translation tables of T1 are created on the next server start).

## 2026-10-25: Phase T4 (segmentation, orchestrator, PREPARING, job API): done
- Done:
  - **Renderer body hook** (`render_document(..., body_hook=)`): called once in `_Renderer.run` after `remove_instructions`, before the FINAL unwrap and `rebuild_toc`, with the elements built from the drafts and source rows (`ContentContext.generated`: the leaf blocks of `build_blocks`, and the template-table rows and source-shaped tables of table slots; a callout box's own label is not in it). `export.render_final` passes it through and now returns the `slot_plan`. With no hook the render is unchanged.
  - **Template text** (`translation/template_text.py`): `harvest_hook` collects every body paragraph not built from the drafts, leaving out the cover (`find_cover`), the TOC field's entries and text without letters. `encode_paragraph` tags formatting: the most-used formatting is plain, other formatting is `⟦k⟧…⟦/k⟧`, spaces never open a tag, and tabs, fields, drawings, links and inline controls are a standalone `⟦k⟧`. `Encoded` keeps what each tag stands for, for T6. `parse_tags` / `strip_tags` are there for T5.
  - **Segments** (`translation/segments.py`): `build_segments` (claims, table cells, table headers once per table, xrefs with `⟦1⟧`, template text; ids in document order); `block_path` / `find_block`.
  - **Contract** `SegmentSet` (the `segments` artifact) and `Segment.scope`; `examples/segment_set.json`. The `translation_set.json` template-text example now shows a real mixed-formatting case.
  - **PREPARING** (`translation/stages.py`): checks the migration is COMPLETED or COMPLETED_WITH_WARNINGS, then calls `render_final` with the harvest hook. It snapshots source, template, slot plan, drafts, assembly and number map, the English `docx` and `render_report` (scope `english`), the glossary and front matter (only when named, each re-checked as approved / ready and of the job's language), then the `SegmentSet`. When there is no glossary or no language template, it adds notes and events. If the English render reports problems, it records `english_render_problems` and goes on.
  - **`TranslationOrchestrator`** (`translation/orchestrator.py`): the migration orchestrator's pattern (semaphore, compare-and-swap, cooperative cancel, `retry(from_stage)` with required artifacts, audited chain factory). Only PREPARING has a stage, so jobs wait at TRANSLATING; `resume_incomplete` skips statuses without a stage.
  - **Job API** (`app/api/translations.py`, after the static routes): `POST /translations` (one job per language; `job_service.resolve_request` checks every language first), list, get, cancel, retry, audit, segments. It is wired in `app/main.py`, with one rate limiter shared with the migration orchestrator.
  - **Checked on the real sample** (a scratch copy of `data/`, the German language template uploaded and marked ready): `MIG-20261019-7BF76968` → TRANSLATING with 373 segments (140 claims, 174 cells, 32 headers, 4 xrefs, 23 template texts; 325 distinct). The template text is the TOC title, the section headings and the template table headers; the cover and TOC entries are left out.
- Files touched:
  - New: `app/services/translation/{segments,template_text,stages,orchestrator,job_service}.py`, `tests/test_translation_{segments,jobs}.py`, `docs/translation/examples/segment_set.json`.
  - Changed: `app/services/migration_v2/render/{renderer,content}.py`, `app/services/migration_v2/export.py`, `app/schemas/v2/{translation,__init__}.py`, `app/api/translations.py`, `app/main.py`, `tests/test_translation_contracts.py`, `docs/translation/{CONTRACTS,IMPLEMENTATION_PLAN}.md`, `docs/translation/examples/translation_set.json`.
- Tests: 24 new. Full suite in `venv`: 674 passed, 15 skipped, 1 failed (the known `test_samples_pass_inspection` on `BI-VQD-10643-S (1).docx`).
- Open issues / decisions:
  - **Template text means "not built from the drafts"**, not "outside `CC_` controls" (retained labels and callout labels would be missed otherwise). The plan's segment table is updated.
  - **Table headers are one set per source table.** A source table that fits the template table renders the template's header, so its source header is only seen in source-shaped tables. It is still a segment (cheap, and deduplicated in T5).
  - **For T6:**
    - `TemplateTable.fits(header)` compares the *English* source header with the template's. Decide the fit on the English headers and write the translated ones, or translated tables change shape and the block paths drift.
    - `show_refs` drops lead words shared by the claim and the phrase ("described in"); after translation they may not match.
    - The apply hook re-encodes each paragraph at its `block_path` and checks that the tagged English equals `source_text` (a mismatch is a warning and the paragraph keeps its English), then rebuilds the runs from `Encoded.groups` / `objects`, keeping bookmarks.
    - Text-box paragraphs under `mc:AlternateContent` appear twice (Choice and Fallback); apply both.
  - If the English final render has post-render problems, `render_final` returns no bytes, so there is no `docx[english]` and `english_docx_sha256` is empty.
  - `data/app.db` still gets schema 2 on the next server start (no server ran during T4).
- Next step: T5. `app/services/llm/prompts/v2/translator.py` (`translator/1`, registered in `audit._PROMPTS`), and `translation/translator.py`:
  - TRANSLATING: distinct source strings packed with `planning/budget.py:pack`, glossary terms per batch from `glossary.terms_in`, `COPIED` for text without letters and for do-not-translate-only text, one `TranslationSet` per scope;
  - `translation/checks.py`: tags with `parse_tags`, `{{ref:}}` tokens, neutral values with `quality/facts.extract_values`, glossary with `target_present`;
  - CHECKING ⇄ REPAIRING stages.

## 2026-10-25: Phase T5 (translator, QA checks, repair): done
- Done:
  - **Prompt `translator/1`** (`app/services/llm/prompts/v2/translator.py`), registered in `audit._PROMPTS`. The system prompt names no language (the audit recognises a task by its exact system prompt); the target language, the glossary entries a call's texts use, the style notes and the "already translated" entries go in the user prompt. Preservation duties only: `{{ref:}}` tokens (and never new ones: a reference written out stays words), exactly the segment's own markers, digits, IDs, e-mails, URLs, obligation strength, nothing added or dropped. `audit.describe` also records `segment_ids` and names a repair call `translator_repair`.
  - **Translator** (`translation/translator.py`):
    - each distinct text translated once, its answer given to every segment that shows it; texts with nothing to translate copied (`checks.copy_only`);
    - two waves: template text, table headers and xrefs first; their short translations are the bounded memory of the section texts (as `GlossaryEntry`s, so `terms_in` sends only those a call uses);
    - blocks packed per scope with `planning/budget.pack`, concurrent; the segments an answer leaves out are asked again once, a failed call is tried once more as two halves; markers an answer adds that its English lacks are dropped;
    - `merged` (segments with their latest translations, every segment in exactly one set) and `build_sets`.
  - **Checks** (`translation/checks.py`): the table in `CONTRACTS.md` (codes `EMPTY`, `REF_TOKENS`, `TAGS`, `NUMBERS`/`REFERENCES` with the `numerical_change` gate, `GLOSSARY-n`/`DNT-n`, `UNTRANSLATED`, `SCRIPT`, `LINE_BREAKS`, `LENGTH`, `NUMBERS_ADDED`). Stable issue ids `TQ-<segment>-<code>`, resolutions carried over (`gates.carry_resolutions`).
  - **Stages:** TRANSLATING (every scope's `translation[<scope>]`), CHECKING (`quality_report[translation]`; REPAIRING when a segment needs it), REPAIRING (one retranslation per segment with its problems; `origin: repair`; the better of the two texts). Jobs now wait at RENDERING. Without an LLM, or when every call fails, the job fails technically (retryable).
  - **Orchestrator:** CHECKING, REPAIRING and RENDERING require `translation` (and REPAIRING a `quality_report`); the retry check looks at artifacts of any scope.
  - **Contracts:** `ValidationIssue.segment_ids`; `IssueCategory.TERMINOLOGY` and `LANGUAGE`; `examples/translation_quality_report.json`. Settings `translator_block_tokens`, `translator_memory_tokens`, `translation_length_min_chars`, `translation_length_bounds`.
  - **API:** `GET /{id}/segments` carries the latest translations; `GET /{id}/validation` (404 `NO_VALIDATION` before CHECKING).
  - **Live** (`tests/test_translation_live.py`, one sample SOP, 314 segments, 294 distinct): fr-FR with a 3-term glossary and ja-JP without one both pass (every segment translated or copied, no critical issue or gate after one repair round; about 20k tokens each). The first Japanese runs showed what the checks and prompt now handle: the model wrapped words in markers the English did not have, turned a written "see chapter 7, no. 1" into a `{{ref:}}` token, ran away to the 16k output limit on a long list of document references, and IDs next to Japanese text (`RD01で`) defeated `\b`.
  - **Real sample** (scratch copy of `data/`, the German job of T4 on `MIG-20261019-7BF76968`, with the German language template, no glossary): 373 segments, 325 distinct, 7 calls (about 22k tokens), then one repair call; the job waits at RENDERING with no gate open and only LOW issues left (people's names in the distribution list, a few short cells' length). Headings, table headers, cells and xrefs read correctly (`PURPOSE` → `ZWECK`, `Chapter ⟦1⟧` → `Kapitel ⟦1⟧`). In one run the model left out 87 of 318 texts without failing a call, so left-out segments are now asked again inside TRANSLATING.
- Files touched:
  - New: `app/services/llm/prompts/v2/translator.py`, `app/services/translation/{translator,checks}.py`, `tests/test_translation_{translator,checks,live}.py`, `docs/translation/examples/translation_quality_report.json`.
  - Changed: `app/services/translation/{stages,orchestrator}.py`, `app/services/migration_v2/audit.py`, `app/schemas/v2/quality.py`, `app/config/settings.py`, `app/api/translations.py`, `tests/test_translation_{jobs,contracts}.py`, `docs/translation/{CONTRACTS,IMPLEMENTATION_PLAN}.md`.
- Tests: 27 new offline, plus 2 live (opt-in with `SOP_RUN_LLM_TESTS=1`; both pass). The T4 job tests keep only PREPARING when they have no chain factory. Full suite in `venv`: 701 passed, 17 skipped, 1 failed (the known `test_samples_pass_inspection` on `BI-VQD-10643-S (1).docx`).
- Open issues / decisions:
  - **Numbers are digit runs, not `extract_values`' kinds** (a deviation from the plan's wording): its normalized forms carry English words. The digits of IDs count on both sides (the English may lack a space a translation adds, so an ID is not always recognised on both sides); digits inside names (`E2E`) do not count.
  - **No LLM, no translation:** TRANSLATING fails technically rather than copying the English.
  - **Dropping foreign markers is the one automatic edit** of an answer: they carry no text. Everything else is reported, never fixed silently.
  - The `SCRIPT` and `UNTRANSLATED` checks leave out the English's own names and acronyms; product names kept in English ("Vault Quality Document ID") and people's names are still flagged (LOW for names) for the reviewer.
  - The frontend's `IssueCategory` union (`frontend/src/features/migrations/types.ts`) needs `terminology` and `language` (T8).
  - **For T6:** a `None` target renders as its English text (the issue stays open for review); apply targets through `translator.merged`; template text's tags may come back reordered (the `TAGS` check guarantees the same set, balanced and not crossing).
- Next step: T6. `translation/render.py`: render the translated final from translated drafts (claims), a translated `SourceDocument` copy (cells and headers, the table fit decided on the English headers), a translated `ref_text`, and an apply hook for the template text at the harvest point; `w:lang` and the East Asian fonts; the language template's front matter (or the English kept); TOC rebuilt from the translated headings; `verify` against the language template's headers and footers (`expected_header_source`).
