# Phase T8 (frontend): detailed plan

Phase T8 of `IMPLEMENTATION_PLAN.md`. **Done when** a reviewer goes from a completed migration to a downloaded translated `.docx` in the UI, and the mock translation UI is gone.

T8 is a ★ phase, split into three sessions (T8a, T8b, T8c). Each ends green (`pytest`, `npm run build`, `npm run lint`, `npm test`) with a `PROGRESS.md` entry and a commit.

## Decisions (user, 2026-10-26)

- **Review layout: a segment grid.** Sections on the left. In the middle, one row per segment, with the English on the left and the target on the right; a click edits the row. Issues, glossary, and find and replace are on the right. No document view beside the grid: the rendered document has its own step (Final).
- **Markers are locked chips.** In the editor, `⟦k⟧…⟦/k⟧`, standalone `⟦k⟧`, `⟦1⟧`, `{{ref:…}}` and `|` show as chips the reviewer cannot type into, split or delete. The server's `SEGMENT_INVALID` check stays the backstop.
- **Navigation: two pages.**
  - Sidebar "Translation" → `/translations`: every translation job.
  - Sidebar "Glossary" → `/translations/resources`: tabs for glossaries and language templates.
- **SOP entry point:** the SOP review page's Translation tab lists that SOP's translation jobs, like the Migration tab does, with "Translate…" on each completed migration. `SopTable`'s "Start Translation" already opens that tab (`/review/:id?mode=translation`), so only the tab's content changes.
- **Permissions:** any signed-in user may approve a glossary, mark a language template ready, and approve a translation, as the backend does today. The audit records who did it.
- **End-to-end check:** on a scratch copy of `data/` with its own backend, never the real `data/app.db`.

## What already exists (reuse, do not rebuild)

| Need | Reuse | Note |
|---|---|---|
| API calls, blobs, field errors | `lib/api.ts` (`request`, `requestBlob`, `saveBlob`, `apiErrorDetails`) | `request` already sends `FormData` without a JSON content type |
| Polling, artifact-stamped queries | `features/migrations/hooks.ts` (`artifactStamp`, `POLL_MS`) | Copy the pattern. Export `artifactStamp` and make it take scope into account |
| Three-pane layout | `ReviewShell` | Add a `storageKey` prop so the translation panes keep their own sizes |
| Step bar | `StageStepper` | Generalize: steps and states as props. The migration use stays unchanged |
| Status pill colours | `status.ts` `TONE_CLASSES`, `SEVERITY_CLASSES`, `humanize` | |
| Issues | `IssueRow`, `SeverityChip`, `ResolutionNote`, `JustifyDialog`, `report.ts` (`sortIssues`, `openIssues`, `actorName`) | `IssuePanel` itself is tied to migrations (slots, high-risk units); write a translation panel on these parts |
| Document view | `DocxViewer` | `fileKey` carries the `docx` version |
| Activity | `ActivityLog` | Extract a presentational `EventList(events, labels)` and use it for both job kinds |
| Dialogs, toasts, buttons | `ConfirmDialog`, `ToastStack`, `Button`, CSS classes `dashboard-card`, `field`, `filter-chip`, `chip` | |
| Rich-text editor | `@tiptap/react` + `@tiptap/starter-kit` (in `package.json`, unused so far) | Check that it is installed in `node_modules` before T8c |

## Small backend additions

These are read-only routes and one cleanup. They go in T8a, with tests in `tests/test_translation_jobs.py` / `test_translation_review.py`.

1. **`GET /translations` rows carry `running`**, as `migrations_v2.py:162` does, so the lists can poll and show spinners.
2. **`GET /{id}/glossary?scope=terms`**: the job's `glossary` snapshot (no scope) or the document terms (`glossary[terms]`), as `Glossary` JSON. Returns 404 `NO_GLOSSARY` when the job has none. The workspace's glossary tab needs it, and today there is no route for either artifact.
3. **`GET /{id}/english`**: the `docx[english]` snapshot, served inline, for "Compare with English" on the Final step. Returns 404 `NO_RENDER` when PREPARING had render problems and saved no English document.
4. **Retire the stub:** in `app/api/review.py`, the `translation` branch returns `availableActions: []`, `targetLocale: None` and links to `/api/v1/translations`. Remove `AI_TRANSLATE` and `RUN_QA`.
5. **Vite:**
   - Delete the dead `'/translations': 'http://localhost:8000'` proxy entry. It is required, not optional: with that entry, reloading the new `/translations` page would be forwarded to the backend and return 404.
   - Read the proxy target from `process.env.API_TARGET` (default `http://localhost:8000`), so the scratch backend can be used in T8c.

## Frontend module: `frontend/src/features/translations/`

| File | Contents |
|---|---|
| `types.ts` | `LanguageCode`, `Language`, `TranslationStatus`, `TranslationJob` (+ `running`, `review?: ReviewState`), `TranslationJobRow`, `ReviewState {render_current, docx_version, blockers: Blocker[], can_approve}`, `Blocker {code, message, issue_id?}`, `SegmentKind`, `SegmentOrigin`, `SegmentLocator`, `Segment`, `SegmentSet` (+ `counts`, `scopes`), `GlossaryEntry`, `Glossary`, `GlossaryRecord`, `LanguageTemplateRecord` (+ `report`), `FrontMatterReport`, `FrontMatterPart`, `EditResult`, `ReplacePreview`, `ReplaceMatch`, `ReplaceResult`, `ResolveResult`. Reuse `QualityReport`, `ValidationIssue`, `RenderReport`, `JobEvent`, `ArtifactRef` from migrations. |
| (migrations) `types.ts` | `IssueCategory` gains `'terminology' \| 'language'`; `ValidationIssue` gains `segment_ids?: string[]` (open issue in PROGRESS T5/T7) |
| `api.ts` | `translationsApi`: languages; glossaries (create multipart, list, get, entries, saveEntries, approve, export csv/xlsx, delete); language templates (create multipart, list, get, report, preview blob, ready, delete); jobs (create, list, get, cancel, retry, audit, segments, validation, renderReport, preview blob, english blob, glossary, terms); review (editSegment, replacePreview, replace, resolveIssue, render, approve, exportWord) |
| `hooks.ts` | `translationKeys`. Queries: `useLanguages` (staleTime ∞), `useTranslationJobs(filter)`, `useTranslationJob` (polled while working), `useSegments`, `useTranslationValidation`, `useTranslationRenderReport`, `useTranslationAudit`, `useJobGlossary`, `useJobTerms`, `useGlossaries(filter)`, `useGlossaryEntries`, `useLanguageTemplates(filter)`. Each mutation refreshes the job, and the artifact queries follow its new versions (the migrations pattern) |
| `status.ts` | Labels and tones per status. Steps, `stepStates`, `defaultStep`, `isWorking`, `permissions` (below) |
| `markers.ts` | Pure: `tokenize(text)` → text / `open k` / `close k` / `object k` / `number` / `ref id` / `cell` / `break` parts; `structureOf` and `structuralProblems(english, target)` (a client mirror of `EMPTY`, `REF_TOKENS`, `TAGS`, `CELLS`); `toEditorDoc` / `fromEditorDoc` for TipTap |
| `segments.ts` | Pure: `groupByScope` in document order; `sectionOrder(template, scopes)` (template sections, then "Template text", then "Cross-references"); `locatorLabel` ("Paragraph", "Table r3 c2", "Table header c1", "Heading or label", "Reference"); `issuesBySegment`; `sameTextCount(segment, all)` (same English text, not human, not itself); `keptInEnglish(renderReport)` (the segment ids named in the render warnings); filters |
| `useTranslationDownloads.ts` | Approved `.docx` (`export/word`, named `{job}_{language}_v{n}.docx`), glossary export, previews |
| `translations.test.ts` | vitest (see Tests) |
| `components/…` | Listed per session below |

Pages: `pages/TranslationsList.tsx`, `pages/LanguageResources.tsx`, `pages/GlossaryEditorPage.tsx`, `pages/LanguageTemplatePage.tsx`, `pages/TranslationWorkspace.tsx`.

Routes (`App.tsx`):

| Route | Page |
|---|---|
| `/translations` | jobs list |
| `/translations/resources` | resources page (`?tab=glossaries\|templates`) |
| `/translations/resources/glossaries/:glossaryId` | glossary editor (`?version=`) |
| `/translations/resources/templates/:templateId` | language template page (`?version=`) |
| `/translations/:jobId` | workspace (`?step=`, `?section=`, `?segment=`) |

React Router ranks the static `resources` segment above `:jobId`. The job id pattern `TRN-…` never clashes with it.

### Status, steps and permissions (`status.ts`)

| Status | Label | Tone | Step |
|---|---|---|---|
| PENDING | Queued | working | none |
| PREPARING | Preparing | working | prepare |
| TRANSLATING | Translating | working | translate |
| CHECKING | Checking | working | translate |
| REPAIRING | Repairing | working | translate |
| RENDERING | Rendering | working | review |
| REVIEW_PENDING | To review | review | review |
| APPROVED | Approved | success | final |
| FAILED_TECHNICAL | Failed | danger | none |
| CANCELLED | Cancelled | neutral | none |

- **Steps:**
  - ① Preparing (reachable once the `segments` artifact exists);
  - ② Translating (once any `translation` artifact exists);
  - ③ Review (once `quality_report[translation]` exists);
  - ④ Final (once `docx[translated]` exists);
  - plus Activity.
  
  The same `done` / `current` / `working` / `locked` / `available` rules apply as for migrations. A re-render shows ③ as working.
- **`isWorking`:** `running` is true, or the status is between PENDING and RENDERING.
- **Permissions** (the server enforces the same rules):

  | Action | Allowed when |
  |---|---|
  | edit, replace, resolve | idle and REVIEW_PENDING |
  | render | idle, REVIEW_PENDING and `!review.render_current` |
  | approve | `review.can_approve` |
  | cancel | not terminal |
  | retry | FAILED_TECHNICAL or CANCELLED, and idle |
  | download | APPROVED |

## T8a: foundation and language resources

1. **Backend additions** 1–3 and 5 above, with tests. Item 4 (the stub) goes in T8b, together with the tab that replaces it.
2. **`types.ts`, `api.ts`, `hooks.ts`, `status.ts`,** and the migrations `types.ts` additions.
3. **Sidebar:** "Translation" → `/translations` and "Glossary" → `/translations/resources`. Both are active on their own prefixes; "Glossary" wins on `/translations/resources…`.
4. **`LanguageResources` page:**
   - **Coverage strip:** the 8 languages, each showing whether it has an approved glossary and a ready language template (✓, or "—"). Clicking a language filters both tabs.
   - **Glossaries tab:** the list grouped by `glossary_id`, newest version first, older versions expandable. Each row shows the name, language, `vN`, a status chip (in review / approved / failed), the term count, and who created it and when. Actions:
     - Open, which goes to the editor.
     - Approve (only while in review).
     - Export CSV or XLSX.
     - Upload a new version (the upload dialog with the `glossary_id` fixed).
     - Delete. A 409 `RECORD_IN_USE` shows as a toast naming the jobs.
   - **`GlossaryUploadDialog`:** language, name, an optional `.csv`/`.xlsx` file ("leave empty to start an empty glossary"), and style notes. A 422 shows every problem the server lists (they carry spreadsheet row numbers). A 409 `GLOSSARY_LANGUAGE_MISMATCH` is shown as is.
   - **Language templates tab:** the list grouped by `template_id`. Each row shows the language, `vN`, status (extracted / ready / failed, with `error`), and its problem and warning counts from the report. Actions: Open, Mark ready, Delete (409 in use).
   - **`LanguageTemplateUploadDialog`:** language, `.docx`, name, and an optional `template_id` for a new version. After the upload, it opens the template page.
5. **`GlossaryEditorPage`:**
   - An editable table with the columns source term, target term, note, case-sensitive and do-not-translate. When do-not-translate is ticked, the target is disabled and shows the source. Rows can be added and deleted. There is a search filter and a count. Above the table: the name and the style notes (a textarea).
   - **Client checks before saving** (mirroring `glossary.py`): a source term is required; the target is required unless do-not-translate; no duplicate source term (case-folded unless case-sensitive). Bad rows are highlighted, and Save stays disabled while any row is bad.
   - **Save** (`PUT …/entries`):
     - While in review, the version is saved in place.
     - On an approved version, it saves as the next version, with the toast "Saved as v3; v2 stays approved", and the URL moves to the new version.
     - A 422 shows the server's problems.
   - A guard for unsaved changes (`beforeunload` and a confirm on in-app navigation). Buttons: Approve, Export, and "Versions" (a dropdown).
6. **`LanguageTemplatePage`:**
   - On the left, `DocxViewer` with the preview (`…/preview`): the first page and two placeholder body pages.
   - On the right, the report:
     - how the first page ends (section break / page break) and its block count;
     - the cover text snippet;
     - sections; `titlePg`, `evenAndOddHeaders`;
     - cover and body header/footer parts (type, text snippet, images);
     - styles and images;
     - **problems** (red; they block ready) and **warnings** (amber; e.g. `DOCVARIABLE`, the English default header).
   - **Mark ready** is disabled while there are problems. A 409 `LANGUAGE_TEMPLATE_NOT_READY` lists the reasons. A note asks the reviewer to "Check the preview pages before marking ready".
7. **Tests:** status and permissions, the glossary editor's row checks, and grouping versions by id.

## T8b: starting translations, job lists, workspace shell, retiring the mocks

1. **`StartTranslationDialog`** (`migrationJobId`, optional SOP for the title):
   - A summary of the migration: the SOP title, `MIG-…`, template `vN`, and its status. It is refused unless the status is COMPLETED or COMPLETED_WITH_WARNINGS; the dialog is never offered otherwise.
   - **Languages:** 8 checkboxes (name, code, script). A language that already has jobs for this migration shows them ("de-DE: To review, TRN-…"). A new job is still allowed.
   - **Per checked language, two selects:**
     - Glossary: the approved versions of that language, newest first, preselected when one exists, else "None (free translation)".
     - Language template: the ready versions, preselected when one exists, else "None (keep English first page, header and footer)".
     
     Each select has a one-line hint saying what "None" means.
   - **Submit** (`POST /translations`):
     - One job: open its workspace.
     - Several: stay on the migration page; the toast lists the jobs.
     - Errors show the server's code and message (e.g. `GLOSSARY_NOT_APPROVED` if it changed meanwhile).
   - Defaults are a pure function (`defaultChoices(languages, glossaries, templates)`), tested.
2. **Migration page:**
   - **`JobHeader`:** a "Translate…" button (with the `Languages` icon) when the job is exportable and idle.
   - **`FinalDocument` aside:** a "Translations" section (`MigrationTranslations`) listing this migration's jobs (language name, status pill, updated time, link), plus "Translate…". It polls while any job works.
3. **SOP review page:**
   - **`SopTranslationJobs`** (the Translation tab): the SOP's migrations (from `useMigrationJobs`), each with its translation jobs (one `GET /translations` call, filtered by migration ids on the client). "Translate…" appears on each completed migration. With no completed migration, the tab says "Complete a migration first" and links to the Migration tab.
   - **`ReviewPage`:** render `SopTranslationJobs` for `mode === 'translation'`. Drop the `onRunQa` / `onAiTranslate` handlers and the mock toasts.
   - **`ActionFooter`:** drop the `RUN_QA` and `AI_TRANSLATE` buttons and props.
   - Backend item 4 (the `review.py` stub). Check `tests/` for a review bootstrap test and update it.
   - **Delete** `components/review/TranslationReviewMode.tsx`, `GlossaryPanel.tsx` and `TranslationQaPanel.tsx`. Keep `SectionNav` and `AISuggestionPanel` if extraction review still uses them (it does today).
4. **`TranslationsList` page (`/translations`):**
   - **Table columns:** language, SOP (joined through the migration rows' `sop_record_id` and `api.getSops`, as `MigrationsList` does), migration id, glossary (or "none"), language template (or "English front matter"), status, updated.
   - **Filters:** language, status, and "needs me" (REVIEW_PENDING).
   - It polls while any job works. Clicking a row opens the workspace. Button: "Language resources".
5. **`TranslationWorkspace` shell:**
   - **`TranslationHeader`:**
     - Back goes to the migration's page (with `?step=final`).
     - The title is "{SOP title} → Deutsch (de-DE)", with a status pill.
     - Below it: the job id; a link to the migration; the glossary `id vN` or "No glossary: free translation"; the language template `id vN` or "English first page, header and footer kept".
     - Buttons: Retry, Cancel (confirm), and "Download translation" (enabled once approved).
   - **Stepper** (the generalized `StageStepper`) and the Activity view (`EventList` over `/audit`, with labels for the translation events `segment_edited`, `segments_replaced`, `issue_resolved`, `render_requested`, `render`, `approved`, `export`, `translator`, …).
   - **`TranslationProgress`** while working: a stage timeline (PREPARING → TRANSLATING → CHECKING → REPAIRING → RENDERING) built from the status events, the `SegmentSet.notes` (no glossary, no language template, English render problems), and the counts once known (segments by kind, distinct texts).
   - **Failed:** the error and Retry, as the migrations `Failed` panel does.
   - **① Preparing and ② Translating, once done:** a read-only summary. Segments by kind, notes, document terms (count, plus a link to the glossary tab), and translator events (calls, tokens, repairs).
   - **④ Final (`TranslationFinal`):**
     - **Document view:** `DocxViewer` on `export/preview`, with `fileKey` carrying `docx_version`. A tab switches to "English" (backend item 3).
     - **Out-of-date banner:** "Edits since this render are not in it yet", with an "Update document" button.
     - **Aside:**
       - approval status (approved by / at, or the blockers);
       - "Download translated document" (approved only; recorded as an export event);
       - render problems (red);
       - render warnings, with "Shown in English" segments linking to the grid;
       - TOC entries;
       - front matter (language template, or English kept);
       - the East Asian font for zh/ja (from the `render` event).
       
       It ends with the existing "in-app view approximates Word" note.
6. **`ReviewBar`**, shown on steps ③ and ④ while REVIEW_PENDING:
   - **Render state:** "Document up to date (render vN)", or "Out of date" with "Update document" (`POST /render`). A RENDERING spinner disables editing.
   - **Blockers:** a count, opening a popover. A blocker with an `issue_id` selects that issue.
   - **"Approve…":** enabled when `can_approve`. It opens a confirm dialog with an optional note and the summary "N open issues (by severity) stay open; they don't block approval". A 409 `APPROVAL_BLOCKED` shows its field errors. On success, go to ④.
7. **Tests:** `defaultChoices`, the job-row join, step states for every status, and the stepper state during a re-render.

## T8c: segment review, then the end-to-end check

1. **Layout** (`ReviewShell`, `storageKey="translation-review-panes"`):
   - **Left pane, "Sections"** (`SectionNav`):
     - Entries in template order: number and heading from the migration's `template_model` (`/api/v1/migrations/{mig}/artifacts/template_model`, the snapshot the job used). Then "Template text" and "Cross-references".
     - Each entry shows its segment count, a dot for the worst open issue's severity, and the count edited by a human.
     - Keyboard: ↑/↓ moves between entries.
   - **Centre: `SegmentGrid`** for the section in `?section=`.
   - **Right pane:** tabs Issues | Glossary | Find & replace.
2. **`SegmentGrid`:**
   - **Toolbar filters:** All | With open issues | Edited | Shown in English | Copied. A search box filters English or target text within the section.
   - **`SegmentRow`:**
     - Header: the segment id, `locatorLabel`, an origin chip (`llm` / `repair` / `human` / `copied`), and chips for its open issues (severity colour; a click selects the issue).
     - Body: two columns, English | target. Both are rendered from `tokenize`. Markers are chips; the words between a ⟦k⟧ pair get a subtle per-k underline in both columns, so the reviewer sees which words carry that formatting. `{{ref:…}}` shows as a "ref" chip, and a lost `⟦1⟧` is obvious.
     - States: hover; selected (`?segment=`, scrolled into view); editing.
   - Rendering is plain React; only the row being edited mounts TipTap. About 370 segments per job, at most about 100 per section, so no virtualization is needed.
3. **`SegmentEditor`** (TipTap):
   - **Nodes:** an inline atom `marker` node (`{type: open|close|object|number|ref|cell, k?, raw}`), `hardBreak` for `\n` (the `LINE_BREAKS` check), and plain text. There are no marks: formatting comes only from the markers.
   - **Locking:** a ProseMirror `filterTransaction` rejects any transaction that changes the multiset of marker nodes, so typing, deleting, cut and drag cannot drop or duplicate one. Paste is plain text with `⟦`, `⟧`, `{{` and `}}` stripped, plus a hint.
   - **Keys:** Ctrl+Enter saves, Esc cancels. Before saving, `structuralProblems` runs as a last client check.
   - **Apply to:** when `sameTextCount > 0`, Save asks "Apply to this segment only / All N segments with this English (edits by people are kept)", defaulting to all, which the API calls `same_text`. With 0 it saves at once.
   - **Result:** `EditResult` gives the segments and issues. A toast reports "Saved to N segments; K issues open on them". The query refetch follows the job's new artifact versions. A 422 `SEGMENT_INVALID` keeps the editor open and lists the server's details.
   - Read-only while not editable (running, re-rendering, or approved), with a banner explaining why.
4. **Issues tab (`TranslationIssuePanel`):**
   - Filters: Blocking (gate or critical) | All open | Resolved, and "This section".
   - Rows use `IssueRow`. "Where" is the section heading and the segment id. A click selects the first segment of `segment_ids`, switching section if needed.
   - Resolve goes through `JustifyDialog` and `POST /issues/{iid}/resolve`. The response's `blockers` refresh the `ReviewBar`.
   - The category labels cover `terminology` and `language`.
5. **Glossary tab (`JobGlossaryPanel`):**
   - **The job's glossary snapshot:** source → target, with do-not-translate and the note. It is searchable, and the terms the selected segment's English uses come first and are marked. Without a glossary: "No glossary: free translation".
   - **Document terms:** each English term with its agreed translation.
   - "Replace everywhere…" on a term pre-fills Find & replace with the agreed translation. That is the T7 way to agree a new term.
6. **Find & replace tab (`FindReplacePanel`):**
   - **Inputs:** find, replace with, case-sensitive, whole words (on by default), scope (whole document / this section).
   - **Preview** (`POST /replace/preview`): totals, then every match as "before **match** after" with the English below it, its segment id, and a checkbox (all ticked). The server's warnings are shown as given: the glossary target, the document term, and longer words with counts, plus a one-click "Search without whole words".
   - **"Replace selected" / "Replace all"** (`POST /replace` with `expected_versions` from the preview):
     - The result shows the count, the skipped segments with their reasons, `term_updated` ("document term X now agreed as Y"), and any longer words left.
     - A 409 `PREVIEW_OUT_OF_DATE` re-runs the preview and says so.
     - Markers in either field are refused on the client, as the server refuses them.
   - Clicking a match selects its segment.
7. **The full review loop through the UI:** edit → issues update → "Out of date" → Update document → render → ④ preview → Approve → Download.
8. **Tests** (vitest): `tokenize` on every marker kind and on mixed text; `structuralProblems` (lost, added or reordered pairs; crossed pairs; changed refs; `|` counts); the `toEditorDoc` / `fromEditorDoc` round trip; marker-multiset preservation (the filter's pure helper); `sameTextCount`; `keptInEnglish`; `issuesBySegment`; section order.
9. **End-to-end on a scratch copy:** see Verification.

## Verification

- **Every session:**
  - `venv/Scripts/python -m pytest` is green, apart from the known unrelated failures (`test_samples_pass_inspection` on `BI-VQD-10643-S (1).docx`, and Word `~$` lock files).
  - `npm run build`, `npm run lint` and `npm test` are clean.
- **Do not touch the real server:** the user's `uvicorn --reload` runs on the real `data/`. The T8a backend changes reload it; they add routes only, with no schema change.
- **End to end (T8c), on scratch data:**
  1. Copy `data/` (plus the template and document folders that the settings resolve) to the scratchpad.
  2. Start `uvicorn app.main:app --port 8001` with `SOP_PROJECT_ROOT` pointing at the copy. Start Vite with `API_TARGET=http://localhost:8001` on port 5174.
  3. Drive the UI in the browser (Claude in Chrome or the built-in browser):
     1. Upload the German and Spanish language templates (`documents/Templates/Template Main GP Docs-de.docx`, `…-es.docx`). Check the previews and mark them ready.
     2. Upload a small French glossary (3–5 terms) and approve it.
     3. On `MIG-20261019-7BF76968`, start **de-DE** (template, no glossary) and **fr-FR** (glossary, no template) from the migration page, and **es-ES** (template) from the SOP's Translation tab. Together these cover three of the plan's four cases; "neither" is ja-JP if the token budget allows.
     4. In de-DE:
        - edit a segment and apply it to all with the same English;
        - edit a template-text segment that has markers, and try to delete a chip (it must refuse);
        - run a find and replace that hits the longer-words warning;
        - resolve a LOW issue.
     5. Update document, check ④, approve and download.
  4. Open the download in Word (as in T3/T7). Check:
     - the German header;
     - the edit is in the document;
     - the TOC is translated;
     - the audit shows each action under the reviewer.
  5. Screenshots of each step go in the PROGRESS entry.
- **Live LLM cost:** about 30k tokens per language. Three languages is about 90k.

## Risks and how the plan handles them

| Risk | Handling |
|---|---|
| The TipTap atom nodes are deleted by Backspace or selection | `filterTransaction` on the marker multiset, with a vitest on the pure multiset helper and a manual check in the end-to-end run |
| The Vite `/translations` proxy swallows page reloads | Delete the entry in T8a (backend item 5) |
| The segments query gets heavy | One `GET /segments` per job version, grouped on the client; only the edited row mounts an editor |
| The issue → segment link is missing on old reports | Issues without `segment_ids` show without a link |
| Stale find-and-replace previews | The server's `expected_versions` → 409, handled by re-previewing |
| `ReviewShell` sizes shared with migrations | The `storageKey` prop |

## At the end of T8

- Update `IMPLEMENTATION_PLAN.md`:
  - the T8 row: split into a/b/c, link to this file;
  - the Frontend section: as built;
  - the "Retire" bullet: done.
- Write a PROGRESS entry per session.
- T9 (evaluation) can then use the UI to review the reports of all 8 languages.
