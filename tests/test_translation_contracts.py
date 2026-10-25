"""Tests for the translation contracts (app/schemas/v2/translation.py) and the language list.

The example documents in docs/translation/examples/ are the reference shapes;
these tests keep them valid.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.v2 import (
    ArtifactKind,
    FrontMatterReport,
    Glossary,
    GlossaryEntry,
    LanguageCode,
    Segment,
    SegmentKind,
    SegmentSet,
    TranslationJob,
    TranslationSet,
    TranslationStatus,
)
from app.services.translation.languages import LANGUAGES, get_language

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "translation" / "examples"

EXAMPLE_MODELS = {
    "glossary.json": Glossary,
    "translation_set.json": TranslationSet,
    "segment_set.json": SegmentSet,
    "translation_job.json": TranslationJob,
    "front_matter_report.json": FrontMatterReport,
}


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("filename, model", EXAMPLE_MODELS.items())
def test_example_validates_and_round_trips(filename, model):
    obj = model.model_validate(_load(filename))
    assert model.model_validate_json(obj.model_dump_json()) == obj


# ── Languages ─────────────────────────────────────────────────────────


def test_the_eight_languages_are_known_with_their_word_codes():
    assert {lang.word_lang for lang in LANGUAGES.values()} == {
        "zh-CN", "fr-FR", "de-DE", "it-IT", "ja-JP", "pt-BR", "es-ES", "el-GR"}
    assert get_language("pt-BR").name == "Portuguese (Brazil)"
    assert get_language(LanguageCode.ZH_CN).east_asian and get_language("ja-JP").east_asian
    assert not get_language("el-GR").east_asian and get_language("el-GR").script == "greek"


def test_an_unknown_language_is_refused():
    with pytest.raises(ValueError, match="unsupported language"):
        get_language("pt-PT")


# ── Glossary ──────────────────────────────────────────────────────────


def test_do_not_translate_keeps_the_source_term():
    entry = GlossaryEntry(source_term="Veeva  Vault", do_not_translate=True)
    assert entry.target_term == "Veeva Vault"
    with pytest.raises(ValidationError, match="do-not-translate"):
        GlossaryEntry(source_term="Veeva", target_term="Wiwa", do_not_translate=True)


def test_an_entry_needs_a_target_term():
    with pytest.raises(ValidationError, match="no target term"):
        GlossaryEntry(source_term="deviation")


def test_a_term_may_appear_only_once_per_glossary():
    entries = [GlossaryEntry(source_term="Deviation", target_term="Abweichung"),
               GlossaryEntry(source_term="deviation", target_term="Abweichung")]
    with pytest.raises(ValidationError, match="more than once"):
        Glossary(glossary_id="G", version=1, language="de-DE", name="g", entries=entries)
    # case-sensitive terms are distinct from their other spellings
    entries[0] = GlossaryEntry(source_term="Deviation", target_term="Abweichung", case_sensitive=True)
    assert len(Glossary(glossary_id="G", version=1, language="de-DE", name="g", entries=entries).entries) == 2


# ── Segments ──────────────────────────────────────────────────────────


def test_a_segment_locator_must_fit_its_kind():
    with pytest.raises(ValidationError, match="no locator"):
        Segment(segment_id="SEG-1", kind=SegmentKind.CLAIM, source_text="x", locator={"section_id": "TGT-1"})
    Segment(segment_id="SEG-1", kind=SegmentKind.TABLE_HEADER, source_text="Role", locator={"unit_id": "U", "col": 0})


def test_a_translated_segment_records_its_origin():
    with pytest.raises(ValidationError, match="no origin"):
        Segment(segment_id="SEG-1", kind=SegmentKind.TEMPLATE_TEXT, source_text="Purpose", target_text="Zweck",
                locator={"block_path": "body/p[3]"})


def test_segment_ids_are_unique_within_a_set():
    seg = {"segment_id": "SEG-1", "kind": "template_text", "source_text": "a", "locator": {"block_path": "p"}}
    with pytest.raises(ValidationError, match="repeat"):
        TranslationSet(job_id="T", language="fr-FR", scope="template", version=1, segments=[seg, seg])
    assert len(TranslationSet(job_id="T", language="fr-FR", scope="template", version=1,
                              segments=[seg]).untranslated) == 1


def test_a_segment_belongs_to_its_section_or_to_xrefs_or_template():
    segments = SegmentSet.model_validate(_load("segment_set.json"))
    assert [s.scope for s in segments.segments] == ["TGT-3", "xrefs", "TGT-4", "TGT-4", "template", "template"]
    assert segments.scopes == ["TGT-3", "xrefs", "TGT-4", "template"]
    assert [s.segment_id for s in segments.scope("TGT-4")] == ["SEG-0003", "SEG-0004"]
    assert segments.counts == {"claim": 1, "xref": 1, "table_header": 1, "table_cell": 1, "template_text": 2}
    seg = segments.segments[0].model_dump()
    with pytest.raises(ValidationError, match="repeat"):
        SegmentSet(job_id="T", migration_job_id="M", language="de-DE", version=1, segments=[seg, seg])


# ── Jobs ──────────────────────────────────────────────────────────────


def test_glossary_and_language_template_are_optional_but_need_their_versions():
    job = TranslationJob(job_id="TRN-1", migration_job_id="MIG-1", language="ja-JP")
    assert job.glossary_id is None and job.language_template_id is None and not job.is_terminal
    with pytest.raises(ValidationError, match="go together"):
        TranslationJob(job_id="TRN-1", migration_job_id="MIG-1", language="ja-JP", glossary_id="G")
    with pytest.raises(ValidationError, match="go together"):
        TranslationJob(job_id="TRN-1", migration_job_id="MIG-1", language="ja-JP", language_template_version=1)


def test_latest_artifact_per_scope():
    job = TranslationJob.model_validate(_load("translation_job.json"))
    assert job.status == TranslationStatus.REVIEW_PENDING
    assert job.latest_artifact(ArtifactKind.TRANSLATION, "TGT-3").version == 1
    assert job.latest_artifact(ArtifactKind.TRANSLATION) is None
