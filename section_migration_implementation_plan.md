# Section-Wise Document Migration Output (`v3.1`) & Inline Icon Attachment

We are refining the Clean `.docx`-Ready Document Migration JSON export to organize elements hierarchically by **Section** (`sections: list[MigrationSection]`) and to attach icons directly inside their corresponding paragraph/chunk elements (`icons: [MigrationIconRef]`) instead of emitting standalone `"icon"` elements that disrupt document text flow.

## User Review Required

> [!IMPORTANT]
> **Schema Evolution (`v3.0` -> `v3.1`)**:
> - Top-level `elements: list[MigrationElement]` is replaced by **`sections: list[MigrationSection]`**.
> - Every section represents a chapter or section in the SOP (e.g. `"0 PREAMBLE"`, `"1 PURPOSE"`, `"2 APPLICABILITY"`, `"3 DEFINITIONS & ABBREVIATIONS"`), containing its own `section_number`, `title`, `page_start`, `page_end`, and `elements: list[MigrationElement]`.
> - Standalone `"element_type": "icon"` items are **removed**. Any extracted icon is attached to the `.icons` array of the adjacent paragraph, list, or table cell where it belongs.
> - Serialized JSON will exclude null and empty default fields (`exclude_none=True`, empty arrays omitted) for maximum cleanliness.

## Proposed Changes

### 1. Schema Definitions

#### [MODIFY] [migration.py](file:///c:/Users/Bhavya/Desktop/Content%20Extraction/app/schemas/migration.py)
- Add `MigrationSection`:
  ```python
  class MigrationSection(BaseModel):
      section_number: Optional[str] = None
      title: str
      page_start: int = 1
      page_end: int = 1
      elements: list[MigrationElement] = Field(default_factory=list)
  ```
- Update `DocxMigrationOutput`:
  - Replace `elements: list[MigrationElement]` with `sections: list[MigrationSection]`.
  - Set `version: str = "3.1"`.
  - Add a helper `.to_clean_dict()` or customize `.model_dump(exclude_none=True)` to strip empty default arrays/nulls when serializing.

---

### 2. Migration Exporter

#### [MODIFY] [migration_exporter.py](file:///c:/Users/Bhavya/Desktop/Content%20Extraction/app/services/export/migration_exporter.py)
- Refactor `MigrationExporter.export(document_id, ast, assets_manifest)`:
  - Traverse `ASTNode` hierarchy section-by-section.
  - Automatically create an initial `"0 PREAMBLE"` section for any content appearing before the first numbered section heading.
  - When encountering an `IconNode` in `_traverse_ast`:
    - Do **not** create a `MigrationElement(element_type="icon")`.
    - Instead, convert to `MigrationIconRef` and attach it to the most recent `MigrationElement` in the current section (or buffer it for the next element if no element has been emitted in the section yet).
  - Ensure table cells also correctly preserve icon references.

---

### 3. Pipeline & Tests

#### [MODIFY] [job_manager.py](file:///c:/Users/Bhavya/Desktop/Content%20Extraction/app/services/job_manager.py)
- Ensure `JobManager._process_document` saves the updated `v3.1` clean JSON to `data/output/<doc_id>_v2.json` using the clean dict serialization.

#### [MODIFY] [test_migration_exporter.py](file:///c:/Users/Bhavya/Desktop/Content%20Extraction/tests/test_migration_exporter.py)
- Update tests for:
  - Section-wise grouping (`output.sections`).
  - Verification that icons appear inside paragraph `icons: []` lists rather than as standalone elements.
  - Verification that preamble and numbered sections have accurate `page_start` / `page_end`.

---

## Verification Plan

### Automated Tests
- Run exporter unit tests:
  ```powershell
  & ".\venv\Scripts\python.exe" -m pytest tests/test_migration_exporter.py -v
  ```
- Run full non-integration regression test suite:
  ```powershell
  & ".\venv\Scripts\python.exe" -m pytest tests/ -v -k "not test_job_manager and not test_api"
  ```

### Manual Verification
- Re-process `o_BI-VQD-24416_Good_Writing_Practice_for_Governance_and_Procedure_Documents_vC_3.0.pdf`.
- Inspect `data/output/o_BI-VQD-24416_Good_Writing_Practice_for_Governance_and_Procedure_Documents_vC_3.0_v2.json` to confirm:
  1. Top-level `sections` array with `"0 PREAMBLE"`, `"1 PURPOSE"`, `"2 APPLICABILITY"`, etc.
  2. Exactly 0 standalone `"element_type": "icon"` items.
  3. Icons cleanly nested inside their respective paragraph/chunk elements.
