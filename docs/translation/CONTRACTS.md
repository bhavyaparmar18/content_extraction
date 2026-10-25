# Translation contracts

The models are in `app/schemas/v2/translation.py` and are exported from `app.schemas.v2`. Example documents are in `examples/` and are kept valid by `tests/test_translation_contracts.py`.

| Model | What it is | Example |
|---|---|---|
| `LanguageCode` | The 8 target languages; each value is the Word `w:lang` code (`zh-CN`, `fr-FR`, `de-DE`, `it-IT`, `ja-JP`, `pt-BR`, `es-ES`, `el-GR`). Names and scripts are in `app/services/translation/languages.py`. | — |
| `GlossaryEntry`, `Glossary` | One glossary version of one language; the source of truth after review. | `glossary.json` |
| `Segment`, `SegmentLocator`, `SegmentKind`, `SegmentOrigin` | One piece of English text to translate, and where its translation goes back. | in `translation_set.json` |
| `TranslationSet` | The segments of one scope in one language: a target section id, `template` or `xrefs`. | `translation_set.json` |
| `SegmentSet` | Every segment of a job's English final document, untranslated: the `segments` artifact PREPARING writes, with the accepted gaps, the draft versions, the English `docx`'s hash and notes for the reviewer. | `segment_set.json` |
| `TranslationJob`, `TranslationStatus` | One language of one completed migration. | `translation_job.json` |
| `FrontMatterReport`, `FrontMatterPart`, `CoverEnd` | What was taken from a language template: how its first page ends, the headers and footers of the first page's section and of the first body section, styles, images, and the problems that block marking it ready. | `front_matter_report.json` |
| `FrontMatterSwap` | What `apply_front_matter` changed in a document (blocks, sections, parts, styles, warnings). | — |
| `QualityReport`, `ValidationIssue` (from `app/schemas/v2/quality.py`) | The QA checks of a translation: the `quality_report[translation]` artifact. Issues name their segments in `segment_ids`; categories `terminology` and `language` are for translations. | `translation_quality_report.json` |

## Rules enforced by the models

| Rule | Where |
|---|---|
| A glossary entry has a target term, unless it is `do_not_translate`; then the target is the source term itself. | `GlossaryEntry._has_target` |
| A source term appears once per glossary. Without `case_sensitive`, the comparison ignores case. | `Glossary._unique_terms` |
| A segment's locator has the fields its kind needs (e.g. a claim names its section, slot and claim). | `Segment._locator_fits_kind` |
| A translated segment records its origin (`llm`, `repair`, `human` or `copied`). | `Segment._locator_fits_kind` |
| Segment ids are unique within a set. | `TranslationSet._unique_ids`, `SegmentSet._unique_ids` |
| A segment's scope is its target section (claims, table cells and headers), `xrefs` or `template`. | `Segment.scope` |
| The glossary and the language template are **optional** on a job, but each id needs its version. | `TranslationJob._versions_with_ids` |
| A language template with report problems cannot be marked ready. | `language_template_service.mark_ready` |

## Conventions

- **Job ids** look like `TRN-YYYYMMDD-XXXXXXXX`. Segment ids look like `SEG-0001` and are unique within a job.
- **Artifacts** are written by the migration `ArtifactWriter` under `data/translations/{job_id}/`. The kinds come from `ArtifactKind`:
  - `segments`: the English document's segments, untranslated;
  - `translation[<scope>]`: one `TranslationSet` per scope;
  - `glossary`: the job's snapshot of its glossary;
  - `front_matter`: the job's snapshot of its language template's first page, headers and footers;
  - `docx`, `render_report` and `quality_report`, as in a migration job: scope `english` for the English final that
    PREPARING rendered, scope `translated` for the translated document RENDERING renders (T6), and
    `quality_report[translation]` for the QA checks.
- **Placeholders** that the translation must keep unchanged:
  - `{{ref:<id>}}` reference tokens;
  - `⟦n⟧` number placeholders in cross-reference phrases;
  - `⟦k⟧…⟦/k⟧` tags around the formatted runs of template text.
- **Database tables** (`app/db/migrations/0002_translation.sql`):
  - `glossaries` and `language_templates`, versioned like `gwp_guides`;
  - `translation_jobs`, `translation_artifacts` and `translation_events`.
  
  A migration, glossary version or language-template version that a translation job uses cannot be deleted: there is a foreign key `ON DELETE RESTRICT`, plus `RecordInUseError` in the stores.

## Segments (Phase T4)

Built in `app/services/translation/segments.py` and `template_text.py` from the migration's final render (`export.render_final`, accepted gaps left out).

- **What is a segment:**
  - `claim`: every claim of the final document except gap markers, table rows (their cells are segments) and figures. `{{ref:…}}` tokens stay in the text.
  - `table_cell`: each non-empty cell of a source table row that a rendered claim cites (`row` is the row index, `col` the column); a cell with several paragraphs gives one segment per paragraph (`paragraph`). A row a reviewer **edited** in the migration (the claim's text is not the unit's, with as many `|`-separated parts as the row has cells) is shown by the renderer from the claim, so it is one `claim` segment with its `|` separators instead (T6).
  - `table_header`: the header cells of each source table **once**, located on the first cited row unit of that table; the translation applies to every row unit of the table.
  - `xref`: each resolved reference phrase (`AssembledDocument.refs[ref_index]`); the new number shown in it is `⟦1⟧`.
  - `template_text`: each body paragraph that the renderer did **not** build from the drafts or the source rows: section headings, retained instruction labels, callout labels, template table headers, conditional text that stays, the table of contents' title. Left out: the cover page, the table of contents' entries (rebuilt from the translated headings) and paragraphs without a letter.
- **Ids** (`SEG-0001`, …) follow the document: each template section in display order, each claim followed by its table's header (the first time), its cells and its references; then the template text in body order.
- **Block paths** locate a template-text paragraph from the body: each step is a tag and its index among the siblings with the same tag, the WordprocessingML prefix left out (`body/sdt[3]/sdtContent[0]/tbl[0]/tr[1]/tc[0]/p[0]`, `body/p[2]/r[0]/pict[0]/v:shape[0]/v:textbox[0]/txbxContent[0]/p[0]`). They are taken by the renderer's `body_hook` once the slots are filled and the instructions removed, before the slot controls are unwrapped; T6 applies the translations at the same point of the same render.
- **Formatting tags** in template text: runs are grouped by formatting (`w:lang`, `w:noProof` and revision ids ignored). The formatting with the most characters is plain; each other one is `⟦k⟧…⟦/k⟧` (the same `k` each time it recurs); spaces never open a tag. A tab, break, field, drawing, hyperlink or inline control is a standalone `⟦k⟧`. A paragraph in one formatting has no tags.
- **Untranslated:** PREPARING leaves every `target_text` empty, even for text without letters; TRANSLATING copies those (`origin: copied`) and translates each distinct string once.

### What PREPARING snapshots into the job

| Artifact | Scope | What |
|---|---|---|
| `source_model`, `template_model`, `slot_plan`, `section_draft[<section>]`, `assembled_draft`, `number_map` | — | the migration's final-render inputs |
| `docx`, `render_report` | `english` | the English final document and its render report |
| `glossary` | — | the job's glossary version (only when it names one) |
| `front_matter` | — | the language template's front-matter package `.docx` (only when it names one) |
| `segments` | — | the `SegmentSet` |

## Translation, checks and repair (Phase T5)

Built in `app/services/translation/translator.py`, `checks.py` and the TRANSLATING, CHECKING and REPAIRING stages; prompt `translator/1` (`app/services/llm/prompts/v2/translator.py`).

- **TRANSLATING** writes `translation[<scope>]` for every scope. Each distinct English text (markers included) is translated once and the answer goes to every segment that shows it. A text with nothing to translate (no letters once markers, `{{ref:}}` tokens, document IDs, e-mails, URLs and do-not-translate terms are removed) is copied (`origin: copied`).
- **Two waves:** the template text, table headers and cross-reference phrases first; their short translations (six words or fewer, no markers) are then the "already translated in this document" entries of the section texts, sent only to the calls whose texts use them (capped at `translator_memory_tokens`), so headings, labels and the body agree.
- **Calls:** groups are packed per scope (`planning/budget.pack`, `translator_block_tokens`) and run concurrently (`llm_max_concurrent`). The segments an answer leaves out are asked again once; a failed call is tried once more as two halves. Markers an answer adds that its English does not have are dropped. Without an LLM, or when every call fails, the job fails technically.
- **CHECKING** writes `quality_report[translation]` (a `QualityReport`; issue id `TQ-<segment>-<code>`, stable, so a reviewer's resolution carries over to the next round):

  | Code | Severity / gate | Category | Rule |
  |---|---|---|---|
  | `EMPTY` | critical | structure | no translation |
  | `REF_TOKENS` | critical | cross_reference | the `{{ref:}}` tokens differ from the English (lost, added or changed) |
  | `TAGS` | critical | formatting | the `⟦k⟧` markers differ, or pairs are unbalanced or cross (their order may change) |
  | `CELLS` | critical | structure | an English text with `\|` cell separators (an edited table row) has a different number of them (T6) |
  | `NUMBERS` | critical, gate `numerical_change` | preservation | a number of the English is missing |
  | `REFERENCES` | critical, gate `numerical_change` | preservation | a document ID, e-mail or URL of the English is missing |
  | `GLOSSARY-<n>` | high | terminology | a glossary term the English uses is not translated with its target term (`n`: the entry's place) |
  | `DNT-<n>` | high | terminology | a do-not-translate term was altered |
  | `UNTRANSLATED` | medium (low for one word or only capitalized words, e.g. a name) | language | identical to the English |
  | `SCRIPT` | medium | language | Chinese, Japanese, Greek: mostly Latin letters, the English's own names and acronyms left out |
  | `LINE_BREAKS` | medium | formatting | a different number of line breaks |
  | `LENGTH` | low | language | character ratio outside `translation_length_bounds` (English of `translation_length_min_chars` or more) |
  | `NUMBERS_ADDED` | low | preservation | a number the English does not show (e.g. "two" written "2") |

  Numbers are compared language-neutrally: digit runs, a separator before exactly three digits is a thousands separator (`1,000` = `1.000` = `1 000`), any other separator splits (`1.5` and `1,5` both give 1 and 5); digits inside a name (`E2E`) are not numbers; full-width digits count. `COPIED` segments are not checked.
- **Repair:** a segment with an open issue of medium or worse, translated by the LLM or not translated at all, goes to REPAIRING **once**: one retranslation with its previous translation and the problems. It becomes `origin: repair` (so it is never repaired again), keeping the new text unless that checks worse than the previous one. A segment that still fails stays open for the reviewer. Human edits (`origin: human`, T7) are checked but never repaired.
- **Integrity:** every segment of the `SegmentSet` is in exactly one `TranslationSet`, with its English text and locator (`translator.merged`); anything else fails the stage.

## Translated render (Phase T6)

Built in `app/services/translation/render.py`, the RENDERING stage and `template_text.apply_hook` / `decode_into`.

- **One render, the English one's:** the same `render_document` call as PREPARING's (final mode, the job's snapshot of template, slot plan, accepted gaps and number map), on translated inputs:

  | Segments | Translated input |
  |---|---|
  | `claim` | a copy of the drafts with each claim's translation (`{{ref:}}` tokens kept) |
  | `table_cell`, `table_header` | a copy of the source model: cells (a paragraph of a multi-paragraph cell, then `text` re-joined) and headers (applied to every row unit of the table); `unit.text` stays English, so an unedited row is still taken from its cells. A header that was only its rows' text joined is joined again from the translated cells (the renderer drops such a header row). |
  | `xref` | a copy of the assembled document: the phrase translated, the new number in place of `⟦1⟧` (`number_at` moved), still a REF field |
  | `template_text` | `apply_hook` at the harvest point (before the TOC is rebuilt, so it lists the translated headings) |

- **Template text:** every paragraph is first found by its block path and checked against its English (`encode_paragraph(p).tagged == source_text`), then rebuilt (`decode_into`): `pPr` and bookmarks kept, text under `⟦k⟧…⟦/k⟧` in that group's formatting, other text plain, each standalone `⟦k⟧` put back as the object it was. A marker that is unknown, or an object lost or doubled, leaves the paragraph in English.
- **Fallback:** a segment with no translation (or only markers), a cross-reference whose `⟦1⟧` is lost or doubled, or a template paragraph that is not where its segment says, is shown in **English**, with a render warning naming the segment; its QA issue stays open for the reviewer.
- **Before the document is saved** (`render_document(..., finish=)`):
  - with a language template: `apply_front_matter` with the job's `front_matter` snapshot; the post-render check then compares the first page, headers and footers with it (`front_matter_problems`, passed as `header_check`) instead of the English template's headers and footers;
  - without one: the English first page, headers and footers stay, compared byte for byte with the English template as in a migration;
  - `set_language`: every `w:lang` of the body (the first page left out), the styles and `themeFontLang` gets the language's Word code, and the document defaults get one; Chinese and Japanese also get `w:eastAsia`. Header and footer parts are never touched;
  - Chinese and Japanese: the East Asian font is the language template's (its defaults or Normal style), else `translation_east_asia_fonts` (`zh-CN`: Microsoft YaHei, `ja-JP`: Yu Gothic). It is set in the defaults and wherever a style or a body run names an East Asian font (`eastAsiaTheme` removed).
- **Artifacts:** `docx[translated]` (saved even when the post-render check has problems, so the reviewer sees them) and `render_report[translated]`. The render warnings leave out the "source column … is under template column …" ones (translated source headers against the English template's). Events: `render` (segments written per kind, those kept in English, TOC, front matter, East Asian font, problems) and `render_problems`.
- **Status:** the job goes to REVIEW_PENDING; approval waits for a render without problems (T7).

## Changing a contract

Change the model, update the example, run `tests/test_translation_contracts.py`, and note the change in `PROGRESS.md`.

## Language template front matter

Built in `app/services/translation/front_matter.py`.

- **First page:** the body blocks through the first section break that starts a new page, or through the first page break when it comes earlier. A paragraph with "page break before" ends the first page before it. A continuous section break inside the first page is an error.
- **Headers and footers** follow Word's inheritance: a section that does not name a type uses the previous section's. The first page's section supplies the first page's; the section after it (the same one when the first page ends at a page break) supplies every body section's.
- **Package:** a `.docx` holding only the first page and an empty body page whose section names its headers and footers explicitly, with the template's styles and numbering. Files: `data/language_templates/{template_id}_v{n}_front_matter.docx`, `…_preview.docx` (two placeholder body pages added) and `…_report.json`. A translation job snapshots the package as its `front_matter` artifact.
- **Swap** (`apply_front_matter(doc, package, language)`):
  - the document's first page is replaced by the package's, with its images and links re-created;
  - header and footer parts are copied with their own relationship ids, so their XML stays byte-identical to the package's;
  - body sections keep their own page size, margins and page numbering, and take the package body section's headers, footers and different-first-page setting;
  - styles: a style the document lacks is copied (a copy whose name clashes is renamed `"<name> (<language>)"`). A style the document defines differently takes the language template's definition when the rest of the document does not use it (e.g. `Header`, `Footer`); a style the body uses (e.g. `Normal`) keeps the document's definition, with a warning;
  - lists on the first page get numbering definitions of their own;
  - document variables (`w:docVars`) are not copied: `DOCVARIABLE` fields on the first page are Vault's to fill;
  - the document's own header and footer parts are dropped.
- **Check:** `front_matter_problems(doc, package)` compares the first page (relationships compared by their targets' content) and, by section role, each header and footer part byte for byte, then `titlePg`, `evenAndOddHeaders`, and that every relationship reference resolves. T6 uses it in place of `verify.py`'s comparison with the English template.
