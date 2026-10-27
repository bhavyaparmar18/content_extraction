"""Document terms: found in the English, translated first, given to every later call, held by the ``TERM`` check
and repaired (the TRANSLATING, CHECKING and REPAIRING stages on the fixture migration, with a fake LLM)."""

from __future__ import annotations

import pytest

from app.schemas.v2 import (
    ArtifactKind,
    Glossary,
    GlossaryEntry,
    QualityReport,
    SegmentKind,
    SegmentOrigin,
    Severity,
    TranslationStatus,
)
from app.services.translation import stages
from app.services.translation.checks import check_segment, needs_repair
from app.services.translation.glossary import term_present
from app.services.translation.terms import find_terms
from app.services.translation.translator import TERMS, Translator, group_segments, translate_all
from tests.test_translation_jobs import _env, asked, translating
from tests.test_translation_translator import _current, _events, _seg
from tests.test_v2_drafter import FakeChain, FakeFactory
from tests.test_v2_renderer import tpl  # noqa: F401  (fixture)

# ── Finding the terms ─────────────────────────────────────────────────


def _body(*texts: str, kind=SegmentKind.CLAIM):
    return [_seg(n, kind, t) for n, t in enumerate(texts, start=1)]


def test_a_phrase_used_in_three_texts_is_a_term_and_function_words_are_not():
    segments = _body("The owning system keeps the record.", "Owning systems are listed in the CMDB.",
                     "Ask the owning system owner.", "The record must be kept.", "It must be kept for ten years.",
                     "Copies must be kept as well.")
    terms = find_terms(segments)
    assert "owning system" in terms  # plural and case found, written as most often
    assert not [t for t in terms if "must" in t.split() or "kept" == t.split()[-1] and "be" in t.split()]
    assert find_terms(segments, min_texts=4) == []
    assert len(find_terms(segments, max_terms=1)) == 1


def test_a_phrase_gives_way_to_the_longer_term_that_covers_it():
    segments = _body("A Business Subject Matter Expert writes it.", "The Business Subject Matter Expert signs.",
                     "A Business Subject Matter Expert of QA reviews.", "A Subject Matter Expert helps.",
                     "Ask a Subject Matter Expert.")
    terms = find_terms(segments)
    assert "Business Subject Matter Expert" in terms
    assert "Subject Matter" not in terms and "Matter Expert" not in terms
    assert "Subject Matter Expert" in terms  # it is used on its own as well


def test_a_short_label_used_elsewhere_is_a_term_names_and_glossary_terms_are_not():
    segments = [_seg(1, SegmentKind.TABLE_CELL, "Change Requester"), _seg(2, SegmentKind.CLAIM,
                "The Change Requester closes the change."), _seg(3, SegmentKind.TABLE_CELL, "Asset Manager"),
                _seg(4, SegmentKind.TABLE_CELL, "BI-AS-UIPATH AAP"), _seg(5, SegmentKind.CLAIM,
                "Follow the BI-AS-UIPATH AAP."), _seg(6, SegmentKind.CLAIM, "See the BI-AS-UIPATH AAP.")]
    assert find_terms(segments) == ["Change Requester"]  # Asset Manager is used once, the AAP is a name
    glossary = Glossary(glossary_id="g", version=1, language="de-DE", name="G",
                        entries=[GlossaryEntry(source_term="change requester", target_term="Antragsteller")])
    assert find_terms(segments, glossary) == []  # the glossary governs it


# ── Matching a term's translation ─────────────────────────────────────


def test_a_term_translation_is_found_inflected_hyphenated_and_in_compounds():
    assert term_present("Das besitzende System führt es aus.", "besitzendes System", "de-DE")
    assert term_present("im SAP des besitzenden Systems", "besitzendes System", "de-DE")
    assert term_present("das Risikoanalysedokument", "Risikoanalyse", "de-DE")
    assert term_present("SCHRITT 4: RPAS-Risikoanalyse", "Risikoanalyse", "de-DE")
    assert term_present("der RPAS-Eigentümers", "RPAS-Eigentümer", "de-DE")
    assert not term_present("des Eigentümersystems", "besitzendes System", "de-DE")
    assert not term_present("die Risikobewertung", "Risikoanalyse", "de-DE")
    assert term_present("所有システムの記録", "所有システム", "ja-JP")


def test_the_term_check_wants_the_agreed_translation_or_the_english_kept():
    terms = [GlossaryEntry(source_term="owning system", target_term="besitzendes System")]
    segment = _seg(1, SegmentKind.CLAIM, "The owning system keeps the record.")

    def issues(target):
        return check_segment(segment.model_copy(update={"target_text": target, "origin": SegmentOrigin.LLM}),
                             "de-DE", terms=terms)

    [issue] = [i for i in issues("Das Eigentümersystem führt den Datensatz.") if "TERM" in i.issue_id]
    assert issue.issue_id == "TQ-SEG-0001-TERM-1" and issue.severity == Severity.MEDIUM and needs_repair(issue)
    assert '"owning system" is translated as "besitzendes System"' in issue.message
    assert not [i for i in issues("Das besitzende System führt den Datensatz.") if "TERM" in i.issue_id]
    assert not [i for i in issues("Das owning system führt den Datensatz.") if "TERM" in i.issue_id]
    assert not [i for i in check_segment(segment.model_copy(update={"target_text": "x y z"}), "de-DE")
                if "TERM" in i.issue_id]  # no terms, no check


# ── The term wave ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_terms_are_translated_first_and_given_to_the_calls_that_use_them():
    segments = [_seg(1, SegmentKind.TEMPLATE_TEXT, "Owning system"),
                _seg(2, SegmentKind.CLAIM, "The owning system keeps the record."),
                _seg(3, SegmentKind.CLAIM, "Sign the form.", "TGT-2")]
    groups = group_segments(segments)
    answers = {"TERM-001": "besitzendes System", "TERM-002": "  der   Datensatz "}
    chain = FakeChain(translating(lambda key, text, repair: answers.get(key, f"DE {text}")))
    translator = Translator("de-DE", groups)
    run = await translate_all(translator, groups, FakeFactory(TranslatorOutput=chain), block_tokens=10,
                              terms=["owning system", "the record"])
    first = asked(chain.calls[0][-1].content)
    assert first == [("TERM-001", "owning system")] and "(term) owning system" in chain.calls[0][-1].content
    assert run.terms == {"owning system": "besitzendes System", "the record": "der Datensatz"}
    assert "TERM-001" not in run.targets and set(run.targets) == {"SEG-0001", "SEG-0002", "SEG-0003"}
    prompts = {asked(c[-1].content)[0][0]: c[-1].content for c in chain.calls}
    assert '"owning system" → "besitzendes System"' in prompts["SEG-0002"] and "DOCUMENT TERMS" in prompts["SEG-0002"]
    assert "DOCUMENT TERMS" not in prompts["SEG-0003"]
    # The template label is memory too, but the term is given once, as a term.
    assert prompts["SEG-0002"].count("owning system\" →") + prompts["SEG-0002"].count("Owning system\" →") == 1


# ── The stages ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_job_agrees_its_terms_and_repairs_a_segment_that_strays(tpl, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(stages, "find_terms", lambda *a, **k: ["Head of Quality"])

    def transform(key, text, repair):
        if key.startswith("TERM-"):
            return "Leitung Qualität"
        if text == "Deputy Head of Quality":
            return "Stellvertretende Leitung Qualität" if repair else "Stellvertretender Qualitätsleiter"
        return f"DE {text}"

    chain = FakeChain(translating(transform))
    env = _env(tmp_path, tpl, FakeFactory(TranslatorOutput=chain))
    job = await env.orch.wait(env.orch.create(env.migration.job_id, "de-DE").job_id)
    assert job.status == TranslationStatus.REVIEW_PENDING, job.error

    terms = env.orch.artifacts.latest(job, ArtifactKind.GLOSSARY, Glossary, TERMS)
    assert [(e.source_term, e.target_term) for e in terms.entries] == [("Head of Quality", "Leitung Qualität")]
    assert asked(chain.calls[0][-1].content) == [("TERM-001", "Head of Quality")]

    first = env.orch.artifacts.read_model(next(a for a in job.artifacts if a.kind == ArtifactKind.QUALITY_REPORT
                                               and a.version == 1), QualityReport)
    [stray] = [i for i in first.issues if "TERM" in i.issue_id]
    assert stray.issue_id.endswith("-TERM-1") and stray.severity == Severity.MEDIUM
    repair = [c[-1].content for c in chain.calls if "REPAIR:" in c[-1].content]
    assert repair and '"Head of Quality" → "Leitung Qualität"' in repair[0]

    final = env.orch.artifacts.latest(job, ArtifactKind.QUALITY_REPORT, QualityReport, "translation")
    assert final.version == 2 and not [i for i in final.issues if "TERM" in i.issue_id]
    deputy = next(s for s in _current(env, job).segments if s.source_text == "Deputy Head of Quality")
    assert deputy.target_text == "Stellvertretende Leitung Qualität" and deputy.origin == SegmentOrigin.REPAIR
    translator = next(e["detail"] for e in _events(env, job.job_id) if e["event"] == "translator")
    assert (translator["terms"], translator["terms_translated"]) == (1, 1)
