# Translation workflow for migrated documents (text only)

## Context

Migration v2 produces a reviewed English SOP in the company template. The next step is translating that document into 8 languages: Chinese (Simplified), French, German, Italian, Japanese, Portuguese (Brazil), Spanish and Greek.

Requirements:
- **Glossary (optional):** each language can have its own term glossary. When one exists the translation must follow it; when none exists the LLM translates freely. No glossaries exist yet.
- **Language template (optional):** a language can have a template `.docx`. Only its **first page, headers and footers** are used: they replace the English ones unchanged and are never translated. The rest of that file is ignored. Without a language template, the English first page, headers and footers are kept as they are. Only one or two exist today.
- **Scope:** only the migrated document's text is translated. Text inside images is the next plan.

Decisions taken with the user:
- **Trigger:** translation runs on a **completed** migration. The user picks one or more languages, and each language gets its own translation job.
- **Engine:** the existing LLM path (`ChainFactory`, `LLMRateLimiter`, versioned prompts, audit events).
- **Review:** every translation is **reviewed and approved** by a human before it can be exported.

What exists today:
- **Mock UI only.** `TranslationReviewMode.tsx`, `GlossaryPanel.tsx` and `TranslationQaPanel.tsx` use hard-coded French data. `app/api/review.py` hard-codes `targetLocale="fr"`. There is no `/translations` backend.
- **Translation hook left by v2:** "claims are the unit of translation" (`CONTRACTS.md:140`, `IMPLEMENTATION_PLAN.md:506`).
- **The render can be re-run from artifacts.** `render_document(template, drafts, source, …)` (`render/renderer.py:170`) depends only on stored artifacts, and `export.render_final` (`export.py:185`) already re-renders from them. The translated document can therefore be built by **re-rendering translated drafts**, not by editing the English `.docx`.

## How to use this plan across Claude Code sessions

- Each phase (T1 to T9, below) is sized for about one session and must end green: `pytest` passes and nothing old breaks.
- At the end of each phase:
  - Append to `docs/translation/PROGRESS.md`: what was done, files touched, open issues, and the next phase's first step.
  - Commit with the phase number in the message (e.g. "Translation T1: …").
- Start each session by reading this plan's relevant phase and the last `PROGRESS.md` entry. Do not re-explore the whole repo.
- New backend code lives in `app/services/translation/`, with contracts in `app/schemas/v2/translation.py`. Migration v2 modules are only touched where a phase says so: the `body_hook` in `render/renderer.py`, the header/footer source in `render/verify.py`, `w:lang` in `render/xml.py`, and `audit._PROMPTS`.
- Phases with a ★ can be split into "a" and "b" sessions if they run long.
- The cross-cutting rules of `docs/migration_v2/IMPLEMENTATION_PLAN.md` apply here too:
  - versioned prompt modules through `ChainFactory` and `LLMRateLimiter`;
  - immutable, versioned artifacts;
  - `@pytest.mark.llm` for live tests;
  - schema changes as new numbered SQL files.

## Approach

1. **Snapshot the English final document.** Take the drafts, source model, number map and assembly that the completed migration exported.
2. **Split it into segments** and translate them with the LLM, using the language's glossary.
3. **Run deterministic QA checks**, then repair the failing segments once.
4. **Re-render** with:
   - the translated `SectionDraft`s;
   - a translated copy of the source model (for table cells);
   - translated cross-reference phrases;
   - a body hook that translates the template's own fixed text.
5. **Replace the cover page, headers and footers** with the language template's.
6. **Human review**, then approval, then export.

### Segments (what gets translated)

| Segment kind | Where the text lives | How it gets back into the document |
|---|---|---|
| `claim` | `Claim.text` in every `SectionDraft` (paragraph, bullet, step, caption, heading) | A translated `SectionDraft` copy, keeping `{{ref:…}}` tokens |
| `table_cell` / `table_header` | `SourceUnit.table_ref.cells[].text/.paragraphs`, `header_cells` (`schemas/v2/source.py:75-91`) | A translated `SourceDocument` copy, passed to `render_document` as `source` |
| `xref` | `AssembledDocument.refs[].text` (English phrase with the new number) | A translated `ref_text` callable; the number is kept as a `⟦n⟧` placeholder |
| `template_text` | Body text the renderer did not build from the drafts or source rows (as built in T4: retained labels sit inside `CC_` controls and callout labels inside built callout boxes, so "outside the slot controls" was not enough), outside the cover and the TOC entries: section headings, retained labels, callout labels, template table headers, boilerplate, TOC title | Applied by a new `body_hook` in `_Renderer.run` (after `remove_instructions`, just before the FINAL `unwrap`, and before `rebuild_toc` so the TOC shows the translated headings). Runs in other formatting are tagged `⟦k⟧…⟦/k⟧` and objects (tabs, fields, links) are a standalone `⟦k⟧`, so the formatting survives (`CONTRACTS.md`). |

Not translated: figures (next plan), the cover page, headers and footers (replaced), field codes and REF field results, numbering, and document IDs and other protected values.

Repeated source strings are translated once per job. Template text is collected by rendering the English final document in PREPARING with a "harvest" hook at the same point, so the paragraph locators match exactly when the translations are applied.

### Language templates (cover page, headers and footers)

- **Optional on the job.** Only one or two language templates exist today.
  - **With a language template:** the job replaces the cover page, headers and footers with the language template's.
  - **Without one:** the English first page, headers and footers are kept exactly as rendered, which is today's behaviour. The verify check then compares against the English template, as it does now. The job records an INFO note ("English first page, header and footer kept: no language template for de-DE") that appears in review.
- **Upload:** one `.docx` per language, as a versioned record like a GWP guide. The job names the version it uses. The start dialog preselects the ready template for that language when there is one, and offers "None (keep English first page, header and footer)".
- **Extraction** (`translation/front_matter.py`):
  - **First page:** the body blocks up to and including the first section break. If there is none, up to the first page break. The admin confirms it in a preview (the extracted pages rendered with `DocxViewer`) before marking the template *ready*.
  - **Headers and footers:** the header and footer parts referenced by the cover section's `sectPr` and by the body `sectPr`s, with their relationships (images), plus `titlePg` / `evenAndOddHeaders`.
- **Swap:** `apply_front_matter(doc, front_matter)`:
  - removes the English cover blocks and inserts deep copies of the language cover;
  - remaps the relationship IDs of images and hyperlinks;
  - copies any style the cover or headers use that is missing (by `styleId`);
  - adds the language header and footer parts and rewires each `sectPr`'s header and footer references by type (default, first, even);
  - drops the English header and footer parts.
- **Verify:** `render/verify.py:144-151` compares headers and footers byte-for-byte with the template. A new `expected_header_source` parameter makes it compare a translated render against the **language template's** parts instead.

### Language identity (built-in, `translation/languages.py`)

- One entry per language: code, display name, Word `w:lang` (`zh-CN`, `fr-FR`, `de-DE`, `it-IT`, `ja-JP`, `pt-BR`, `es-ES`, `el-GR`), and whether it is East Asian.
- Translated runs get `w:lang` (`xml.add_runs` / `base_rpr` currently copies the template's `lang`, `xml.py:99`), and the document `docDefaults` are set to the target language.
- **Chinese and Japanese fonts:** the `eastAsia` font comes from the language template's `docDefaults` / Normal style, with a per-language fallback in settings.
- **No writing-style rules in code.** The only built-in rules are preservation rules, same as the GWP memory rule. A glossary file may carry an optional "style notes" sheet, which is passed to the prompt verbatim.

### Glossary

- **Upload:** CSV or XLSX (add `openpyxl`) per language, with columns `source_term`, `target_term`, `note`, `case_sensitive`, `do_not_translate`. Versioned by `glossary_id` like `gwp_guides`, and editable in the UI (each save makes a new version).
- **Status:** `uploaded → in_review → approved`. Deleting a version a job uses returns 409 `RECORD_IN_USE`, through a foreign key with `ON DELETE RESTRICT` plus a store check, as in `gwp_store.py:125`.
- **Job snapshot:** the job copies its glossary into a `glossary` artifact, so later edits never change a running job.
- **Optional on the job,** as GWP is. No glossaries exist yet. The UI preselects the newest approved glossary for the chosen language, if there is one.
  - **Without a glossary,** the LLM translates freely. The prompt has no glossary section and the glossary QA checks do not run. The preservation rules (tokens, numbers, IDs) still apply.
  - **With a glossary,** its terms are mandatory. The prompt says to use the supplied target term exactly, and the QA check enforces it.
- **Prompt and QA:** each batch's prompt gets only the entries whose source term occurs in that batch (case-insensitive, word boundary, simple plurals). The QA check flags a source term whose target term is missing from the translation; for Chinese and Japanese it matches substrings.

### Translation job

- **New tables** in `app/db/migrations/0002_translation.sql`:
  - `glossaries` and `language_templates`, each keyed `(id, version)`;
  - `translation_jobs`, with a foreign key `ON DELETE RESTRICT` to `migration_jobs`, and nullable foreign keys (also `ON DELETE RESTRICT`) to the glossary version and the language template version;
  - `translation_artifacts` and `translation_events`, mirroring the migration tables.
- **Files** go in `data/translations/{TRN-id}/`, through `ArtifactWriter` (generalised to take a store with `add_next_artifact`).
- **`TranslationOrchestrator`** (`translation/orchestrator.py`) follows the `migration_v2/orchestrator.py` pattern: one asyncio task per job behind a semaphore, compare-and-swap status, cooperative cancel, `resume_incomplete` at startup, and `retry(from_stage)`.
- **Stages:**
  1. `PENDING`
  2. `PREPARING`: the migration must be COMPLETED or COMPLETED_WITH_WARNINGS. Snapshot the English drafts, source, number map, assembly and accepted gaps; snapshot the glossary and front matter; produce the `segments` artifact.
  3. `TRANSLATING`: blocks packed with `planning/budget.py:pack`, run concurrently behind `llm_max_concurrent`, with a bounded memory of the previous segments.
  4. `CHECKING` ⇄ `REPAIRING`: one retranslation with the issue as feedback. A segment that still fails is left for the reviewer.
  5. `RENDERING`: final mode, then the language front matter (skipped when the job has no language template), then verify.
  6. `REVIEW_PENDING`
  7. `APPROVED`
- A reviewer's segment edit makes a new artifact version (origin `human`) and re-runs CHECKING and RENDERING.
- **Prompt:** a new module `app/services/llm/prompts/v2/translator.py` (`PROMPT_VERSION = "translator/1"`), registered in `migration_v2/audit.py:_PROMPTS`. The structured output is `[{segment_id, translation}]`.
  - Fixed duties: translate en → target; keep `{{ref:…}}`, `⟦n⟧` and `⟦k⟧…⟦/k⟧` markers; never change numbers, units, dates, IDs, emails or URLs; never add or drop content; use the supplied glossary terms exactly.
  - The glossary entries and the style notes go into the user prompt.

### QA checks (`translation/checks.py`, deterministic)

- **Blocking:**
  - empty translation;
  - a `{{ref:}}` token, number placeholder or run tag lost or changed;
  - table cell count changed (this cannot happen by construction, but it is asserted).
- **Gate (`NUMERICAL_CHANGE`):** language-neutral protected values differ. These are found with `quality/facts.py:extract_values` restricted to neutral kinds: document IDs, emails, URLs, digits with units or %, ISO and numeric dates, times. English-only kinds (number words, month names, modal verbs) are excluded.
- **High:** a glossary target is missing, or a `do_not_translate` term was altered.
- **Warning:**
  - text identical to the source (when it has letters and is not on the glossary's do-not-translate list);
  - for Chinese, Japanese and Greek, mostly Latin script;
  - length ratio outside the per-language bounds (in settings).

Issues use the existing `ValidationIssue` and `QualityReport` shapes, so the frontend issue components can be reused.

### API (`app/api/translations.py`, prefix `/api/v1/translations`)

- **Languages:** `GET /languages`.
- **Glossaries** (as built in T2). `{glossary}` is the record id or the `glossary_id`; `?version=` picks a version, and the latest is the default, as in the GWP API.
  - `POST /glossaries` (multipart: `language`, an optional `file`, `name`, `glossary_id` and `style_notes`; without a file it starts an empty glossary)
  - `GET /glossaries?language=&status=&glossary_id=`
  - `GET /glossaries/{glossary}` (the record)
  - `GET /glossaries/{glossary}/entries` (the Glossary JSON)
  - `PUT /glossaries/{glossary}/entries` (edits in place while in review; on an approved version, creates the next version)
  - `POST /glossaries/{glossary}/approve`
  - `GET /glossaries/{glossary}/export?format=csv|xlsx`
  - `DELETE /glossaries/{glossary}` (409 `RECORD_IN_USE` when a translation job uses the version)
- **Language templates** (as built in T3; `{t}` is a record id or a `template_id`, with `?version=`):
  - `POST /language-templates` (multipart: `language`, `.docx` file, optional `name` and `template_id`): saves the next version and extracts its front matter at once; the result is `extracted`, or `failed` with the reason. The response carries the report.
  - `GET /language-templates?language=&status=&template_id=`
  - `GET /language-templates/{t}`, `GET …/{t}/report`
  - `GET …/{t}/preview` (`.docx`: the first page and two placeholder body pages)
  - `POST …/{t}/ready` (409 `LANGUAGE_TEMPLATE_NOT_READY` while the report has problems)
  - `DELETE …/{t}` (409 `RECORD_IN_USE` when a job uses it)
- **Jobs** (the first five as built in T4; `{id}` is a `TRN-…` job id):
  - `POST /translations {migration_job_id, languages:[{language, glossary_id?, glossary_version?, language_template_id?, language_template_version?}]}`: one job per language; both resources are optional. Without a version, the newest approved glossary or ready language template of that id is used. Every language is checked before any job is created: 404 `MIGRATION_NOT_FOUND`, `GLOSSARY_NOT_FOUND`, `LANGUAGE_TEMPLATE_NOT_FOUND`; 409 `MIGRATION_NOT_COMPLETED`, `GLOSSARY_NOT_APPROVED`, `LANGUAGE_TEMPLATE_NOT_READY`; 422 `NO_LANGUAGES`, `UNSUPPORTED_LANGUAGE`, `DUPLICATE_LANGUAGE`, `…_LANGUAGE_MISMATCH`, `…_ID_REQUIRED`.
  - `GET` list (`?migration_job_id=&language=&status=`)
  - `GET /{id}`, `POST /{id}/cancel`, `POST /{id}/retry?from_stage=`, `GET /{id}/audit`
  - `GET /{id}/segments?section=` (the `SegmentSet`; `section` is a target section id, `xrefs` or `template`)
  - `PATCH /{id}/segments/{segment_id}`
  - `GET /{id}/validation`
  - `POST /{id}/issues/{iid}/resolve`
  - `POST /{id}/approve`
  - `GET /{id}/export/preview`
  - `GET /{id}/export/word` (only once approved; recorded as an event)
- **Retire** the `review.py` translation stub and the dead `/translations` vite proxy target.

### Frontend (`frontend/src/features/translations/`)

- **Language resources page** (sidebar "Glossary" and "Translation" links, which currently go nowhere):
  - **Glossaries tab:** upload, editable term table, versions, approve.
  - **Language templates tab:** upload, a front-matter preview with `DocxViewer`, mark ready.
- **"Translate" button** on a completed migration (`FinalDocument.tsx` / `JobHeader.tsx`). It opens `StartTranslationDialog`, which offers a multi-select of the 8 languages and, per language, two optional pickers:
  - **Glossary:** preselected when an approved one exists, otherwise "None (free translation)".
  - **Language template:** preselected when a ready one exists, otherwise "None (keep English first page, header and footer)".
- **Migration page:** a panel listing that migration's translation jobs and the status of each.
- **Translation workspace `/translations/:id`:**
  - steps: Preparing, Translating, Review, Final (reusing `StageStepper` and `ReviewShell`);
  - per-section review: English segments on the left, editable target segments on the right;
  - the existing issue panel components;
  - the glossary and QA panels, rewritten on real data (replacing the mocks);
  - approve;
  - final preview and download through `DocxViewer` and `useDownloads`.
- Point `SopTable`'s "Start Translation" at this flow, and delete the mock `TranslationReviewMode` path.
- Polling follows `features/migrations/hooks.ts`. Pure-logic tests go in vitest, like `migrations.test.ts`.

## Phases

Phases follow the `docs/migration_v2/IMPLEMENTATION_PLAN.md` conventions: one session each, `pytest` green at the end, a PROGRESS entry and a commit per phase.

**First step:** write this plan as `docs/translation/IMPLEMENTATION_PLAN.md` and start `docs/translation/PROGRESS.md`.

| # | Phase | Main files | Done when |
|---|---|---|---|
| T1 | Contracts, schema, stores | `app/schemas/v2/translation.py` (Segment, TranslationSet, Glossary, LanguageTemplate, TranslationJob), `translation/languages.py`, `app/db/migrations/0002_translation.sql`, `app/stores/glossary_store.py`, `language_template_store.py`, `translation_store.py`, `ArtifactKind` additions | Contract and store tests pass, including in-use delete blocked |
| T2 | Glossary management | `translation/glossary.py` (CSV/XLSX parse, validate, match), API, `requirements.txt` (+openpyxl) | Upload → edit → approve → snapshot works; matcher tested for zh/ja/el/Latin |
| T3 ★ | Language template front matter | `translation/front_matter.py` (extract, preview, `apply_front_matter`), API | A synthetic template with an image in the header and a cover section break swaps correctly; Word opens the result |
| T4 | Segmentation, orchestrator, PREPARING | `translation/segments.py`, `translation/orchestrator.py`, `translation/stages.py`, `body_hook` param on `render_document`, `app/main.py` wiring | A job on a fixture migration produces a complete `segments` artifact (claims, cells, xrefs, template text) |
| T5 ★ | Translator, QA, repair | `prompts/v2/translator.py`, `translation/translator.py`, `translation/checks.py`, `audit._PROMPTS` | Offline tests with `FakeChain` pass; a live `@pytest.mark.llm` run on one sample for fr and ja |
| T6 ★ | Translated render and export | `translation/render.py` (translated drafts, source copy, ref_text, template-text hook, `w:lang`/fonts, front matter, TOC), `verify.py` param, export | The rendered `.docx` has a translated body, a correct TOC, and `verify` clean, both with a language template (its cover/header/footer) and without one (English cover/header/footer kept) |
| T7 | Review API | segment PATCH → new version → re-check and re-render, issue resolve, approve gate, export | Edit → approve → export end-to-end through the API |
| T8 ★ | Frontend | resources page, start dialog, workspace, review, final; remove mocks | A reviewer goes from a completed migration to a downloaded translated `.docx` in the UI |
| T9 | Evaluation | `scripts/inspect_translation.py` (HTML report like `inspect_sop.py`) | All 8 languages run on the samples; reports reviewed |

Before T1's schema file is saved: the user's `uvicorn --reload` applies new migrations to the real `data/app.db` on every save. Check whether it is running, and stage the change or ask the user to stop the server.

## Assumptions to confirm during T1

- Spanish is `es-ES` (Spain), not Latin American Spanish.
- The source language is always English.
- The template's fixed body text (section headings, labels) is translated by the LLM, with the glossary.
- Every job re-translates from scratch; there is no translation memory across jobs (a follow-up).

## Verification

- **Each phase:** `venv/Scripts/python -m pytest` is green. Offline tests mock the LLM (`FakeChain` / `FakeFactory`, `tests/test_v2_drafter.py:123`); renderer tests build synthetic templates as in `tests/test_v2_renderer.py`.
- **Live:** `SOP_RUN_LLM_TESTS=1 pytest -m llm tests/test_translation_live.py -s`.
- **End to end:**
  1. Upload the available language templates, and a small test glossary for one language.
  2. Start translations on a completed sample migration (`data/migrations/MIG-20261019-7BF76968/`). Cover all four cases:
     - with a language template and a glossary;
     - with a language template and no glossary;
     - with a glossary and no language template;
     - with neither.
  3. Review the issues, edit a segment and approve.
  4. Export, then open the `.docx` in Word and check:
     - the body is in the target language;
     - with a glossary, its terms are used;
     - numbers and IDs are unchanged;
     - the cover, header and footer come from the language template when there is one, and are the English ones otherwise;
     - the TOC shows the translated headings;
     - the Chinese and Japanese fonts render.
