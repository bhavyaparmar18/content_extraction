"""Live check of the translator (Phase T5) on one sample SOP, for French (with a small glossary) and Japanese (none).

The sample goes through the rule section and slot plans and placement drafts (no LLM), the assembly and the
segments, plus a few template texts with formatting markers. After one translation and one repair round, every
segment must be translated or copied, no critical issue or gate may be open, and Japanese must be in Japanese
(at most 3% of the segments flagged for Latin script: product names and titles the model keeps in English).

    SOP_RUN_LLM_TESTS=1 PYTHONIOENCODING=utf-8 pytest -m llm tests/test_translation_live.py -s
"""

import os

import pytest

from app.config.settings import get_settings
from app.schemas.v2 import Glossary, GlossaryEntry, Segment, SegmentKind, SegmentOrigin, Severity
from app.services.llm.chain_factory import ChainFactory
from app.services.migration_v2.assembly import assemble
from app.services.migration_v2.drafting.drafter import Drafter, draft_all
from app.services.migration_v2.planning.section_planner import SectionPlanner
from app.services.migration_v2.planning.slot_planner import SlotPlanner
from app.services.migration_v2.quality.facts import extract_facts
from app.services.translation.checks import check_segment, check_translations, copy_only, repair_candidates, worst
from app.services.translation.segments import build_segments
from app.services.translation.translator import Translator, group_of, group_segments, repair_all, translate_all
from tests.test_v2_slot_planner import samples  # noqa: F401  (fixture)

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(os.environ.get("SOP_RUN_LLM_TESTS") != "1", reason="set SOP_RUN_LLM_TESTS=1 to call the LLM"),
]

TEMPLATE_TEXTS = [
    "Table of Contents",
    "Purpose",
    "Responsibilities",
    "⟦1⟧Note:⟦/1⟧ keep this record for 10 years.⟦2⟧",
    "Approved by ⟦1⟧Quality Assurance⟦/1⟧ on ⟦2⟧",
]

FRENCH = Glossary(glossary_id="live-fr", version=1, language="fr-FR", name="Live test terms", entries=[
    GlossaryEntry(source_term="deviation", target_term="écart"),
    GlossaryEntry(source_term="batch record", target_term="dossier de lot"),
    GlossaryEntry(source_term="SAP", do_not_translate=True, case_sensitive=True),
])


def _plans(samples):  # noqa: F811
    tpl, docs = samples
    doc, _ = docs[0]
    sections = SectionPlanner(doc, tpl)
    section_plan = sections.build_plan(sections.propose(), "J", 1)
    slots = SlotPlanner(doc, tpl, section_plan, None)
    slot_plan = slots.build_plan(slots.propose(), "J", 1)
    return doc, tpl, section_plan, slot_plan


async def _translate(segments: list[Segment], language: str, glossary, factory) -> tuple[list[Segment], dict]:
    """TRANSLATING, CHECKING, REPAIRING and CHECKING again, as the stages do."""
    groups = group_segments(segments)
    copied = [g for g in groups if copy_only(g.source_text, glossary)]
    todo = [g for g in groups if g not in copied]
    translator = Translator(language, groups, glossary)
    run = await translate_all(translator, todo, factory)
    targets = {sid: (g.source_text, SegmentOrigin.COPIED) for g in copied for sid in g.segment_ids}
    for g in todo:
        text = run.targets.get(g.key)
        targets.update({sid: (text, SegmentOrigin.LLM if text else None) for sid in g.segment_ids})
    current = [s.model_copy(update={"target_text": targets[s.segment_id][0], "origin": targets[s.segment_id][1]})
               for s in segments]
    first = check_translations("TRN-LIVE", 1, current, language, glossary, get_settings())

    wanted = set(repair_candidates(current, first))
    by_id = {s.segment_id: s for s in current}
    owner = group_of(groups)
    repair_groups = [g for g in groups if wanted & set(g.segment_ids)]
    problems: dict[str, list[str]] = {}
    for issue in first.issues:
        for sid in issue.segment_ids:
            if sid in wanted:
                problems.setdefault(owner[sid].key, []).append(issue.message.split(": ", 1)[-1])
    previous = {g.key: by_id[next(s for s in g.segment_ids if s in wanted)].target_text for g in repair_groups}
    repaired = await repair_all(translator, repair_groups, previous, problems, factory)
    for g in repair_groups:
        answer = repaired.targets.get(g.key)
        for sid in (s for s in g.segment_ids if s in wanted):
            old = by_id[sid]
            new = old.model_copy(update={"target_text": answer, "origin": SegmentOrigin.REPAIR}) if answer else old
            if answer and worst(check_segment(new, language, glossary)) > worst(check_segment(old, language, glossary)):
                new = old
            by_id[sid] = new.model_copy(update={"origin": SegmentOrigin.REPAIR})
    final = [by_id[s.segment_id] for s in segments]
    usage = {"translate": run.usage, "repair": repaired.usage, "repair_segments": len(wanted),
             "first_round_issues": len(first.issues)}
    return final, usage


@pytest.mark.parametrize("language, glossary", [("fr-FR", FRENCH), ("ja-JP", None)])
async def test_live_translation_keeps_tokens_markers_and_numbers(samples, language, glossary):  # noqa: F811
    doc, tpl, section_plan, slot_plan = _plans(samples)
    drafter = Drafter(doc, tpl, section_plan, slot_plan, extract_facts(doc, "J"))
    drafts = drafter.build_drafts(await draft_all(drafter), {})
    assembly = assemble(tpl, drafts, doc, section_plan, job_id="J")
    segments = build_segments(tpl, drafts, doc, assembly.document,
                              [(f"body/p[{i}]", text) for i, text in enumerate(TEMPLATE_TEXTS)])
    assert {s.kind for s in segments} >= {SegmentKind.CLAIM, SegmentKind.TEMPLATE_TEXT}

    final, usage = await _translate(segments, language, glossary, ChainFactory(get_settings()))
    report = check_translations("TRN-LIVE", 2, final, language, glossary, get_settings())
    open_issues = [i for i in report.issues if not i.resolved]
    print(f"\n{language}: {len(segments)} segments, {len({s.source_text for s in segments})} distinct; {usage}")
    print(f"  open issues: {sorted({i.issue_id.split('-', 3)[3] for i in open_issues})}")
    for segment in [s for s in final if s.origin != SegmentOrigin.COPIED][:3] + final[-len(TEMPLATE_TEXTS):][3:]:
        print(f"  {segment.source_text[:90]!r}\n   → {segment.target_text[:90]!r}")

    assert all(s.target_text is not None for s in final)
    assert not [i.message for i in open_issues if i.severity == Severity.CRITICAL]
    assert not report.open_gate_issues
    if language == "ja-JP":  # product names and titles kept in English may be flagged; the rest is Japanese
        script = [i.message for i in open_issues if i.issue_id.endswith("-SCRIPT")]
        assert len(script) <= 0.03 * len(segments), script
    note = next(s for s in final if s.source_text == TEMPLATE_TEXTS[3])
    assert note.target_text.count("⟦1⟧") == 1 and "⟦/1⟧" in note.target_text and "⟦2⟧" in note.target_text
    assert "10" in note.target_text
