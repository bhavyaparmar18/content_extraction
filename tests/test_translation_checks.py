"""Phase T5: the deterministic QA checks of a translation (``translation/checks.py``)."""

from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.schemas.v2 import (
    Gate,
    Glossary,
    GlossaryEntry,
    QualityReport,
    Segment,
    SegmentKind,
    SegmentLocator,
    SegmentOrigin,
    SegmentSet,
    Severity,
    TranslationSet,
)
from app.services.translation.checks import (
    check_segment,
    check_translations,
    neutral_numbers,
    repair_candidates,
    tag_problems,
    worst,
)
from app.services.translation.translator import merged


def _seg(source: str, target, origin=SegmentOrigin.LLM, kind=SegmentKind.CLAIM, n: int = 1) -> Segment:
    locator = (SegmentLocator(section_id="TGT-1", slot_id="TGT-1-S1", claim_id=f"C-{n}") if kind == SegmentKind.CLAIM
               else SegmentLocator(block_path=f"body/p[{n}]"))
    return Segment(segment_id=f"SEG-{n:04d}", kind=kind, source_text=source, target_text=target,
                   origin=origin if target is not None or origin != SegmentOrigin.LLM else None, locator=locator)


def codes(source: str, target, language="de-DE", glossary=None, settings=None, **kw) -> dict[str, Severity]:
    issues = check_segment(_seg(source, target, **kw), language, glossary, settings)
    return {i.issue_id.split("-", 3)[3]: i.severity for i in issues}


def test_a_missing_translation_is_critical_and_nothing_else_is_checked():
    assert codes("Keep the records.", None) == {"EMPTY": Severity.CRITICAL}
    assert codes("Keep the records.", "⟦1⟧ ") == {"EMPTY": Severity.CRITICAL}
    assert codes("1.2", "1.2", origin=SegmentOrigin.COPIED) == {}


def test_reference_tokens_must_all_stay():
    source = "Follow {{ref:SRC-7.1}} and {{ref:SRC-8}}."
    assert codes(source, "Folgen Sie {{ref:SRC-8}} und {{ref:SRC-7.1}}.") == {}
    issue = check_segment(_seg(source, "Folgen Sie {{ref:SRC-7.1}}."), "de-DE")[0]
    assert issue.issue_id == "TQ-SEG-0001-REF_TOKENS" and issue.severity == Severity.CRITICAL
    assert "lost {{ref:SRC-8}}" in issue.message and issue.segment_ids == ["SEG-0001"]
    assert issue.target_section_id == "TGT-1" and issue.claim_ids == ["C-1"]
    assert "REF_TOKENS" in codes(source, "Folgen Sie {{ref:SRC-7.1}} {{ref:SRC-8}} {{ref:SRC-9}}.")


def test_markers_may_move_but_not_change():
    source = "⟦1⟧Note:⟦/1⟧ keep this record.⟦2⟧"
    assert tag_problems(source, "⟦1⟧Hinweis:⟦/1⟧ Diese Aufzeichnung aufbewahren.⟦2⟧") == []
    assert tag_problems(source, "⟦2⟧Diese Aufzeichnung ⟦1⟧aufbewahren⟦/1⟧.") == []  # reordered
    assert tag_problems(source, "⟦1⟧Hinweis: Diese Aufzeichnung aufbewahren.⟦2⟧")  # the close dropped
    assert tag_problems(source, "Hinweis: Diese Aufzeichnung aufbewahren.")
    assert tag_problems(source, "⟦1⟧Hinweis:⟦/1⟧ ⟦3⟧Diese⟦/3⟧ Aufzeichnung.⟦2⟧")
    nested = "⟦1⟧a ⟦2⟧b⟦/2⟧ c⟦/1⟧"
    assert tag_problems(nested, "⟦1⟧c ⟦2⟧b⟦/1⟧ a⟦/2⟧")  # pairs that cross
    assert codes("chapter ⟦1⟧", "Kapitel ⟦1⟧", kind=SegmentKind.TEMPLATE_TEXT) == {}
    assert codes("chapter ⟦1⟧", "Kapitel 1", kind=SegmentKind.TEMPLATE_TEXT)["TAGS"] == Severity.CRITICAL


def test_numbers_are_compared_language_neutrally():
    assert neutral_numbers("1.5 mg") == neutral_numbers("1,5 mg")
    assert neutral_numbers("1,000 units") == neutral_numbers("1 000 unités") == neutral_numbers("1.000 Einheiten")
    assert neutral_numbers("within 10 days") == neutral_numbers("１０日以内")  # full-width digits
    assert neutral_numbers("on 12/03/2025") == neutral_numbers("am 12.3.2025")
    assert neutral_numbers("see {{ref:SRC-7.1}} ⟦1⟧") == neutral_numbers("")
    # The digits of an ID count on both sides, recognised as an ID or not (the English lacks a space here).
    assert neutral_numbers("per 028-BIS-00535Computerized") == neutral_numbers("gemäß 028-BIS-00535 Computerized")
    assert neutral_numbers("an E2E scenario in S4HANA") == neutral_numbers("")  # digits inside names
    assert neutral_numbers("最低1つ") == neutral_numbers("at least 1")

    found = check_segment(_seg("Store at 2-8 °C for 30 days.", "Bei 2–8 °C für 3 Tage lagern."), "de-DE")
    number = next(i for i in found if i.issue_id.endswith("-NUMBERS"))
    assert number.gate == Gate.NUMERICAL_CHANGE and "30" in number.message
    assert codes("Store for two days.", "2 Tage lagern.") == {"NUMBERS_ADDED": Severity.LOW}

    ids = check_segment(_seg("Use form BI-VQD-10095-S or mail qa@example.com.", "Formular BI-VQD-10095 verwenden."),
                        "de-DE")
    reference = next(i for i in ids if i.issue_id.endswith("-REFERENCES"))
    assert reference.gate == Gate.NUMERICAL_CHANGE and "QA@EXAMPLE.COM".lower() in reference.message.lower()
    # An ID right next to Chinese or Japanese text is still found.
    assert codes("The roles defined in 028-BIP-00516-RD01 apply.", "028-BIP-00516-RD01で定義された役割が適用される。",
                 "ja-JP") == {}


def _glossary(language: str, *entries: GlossaryEntry) -> Glossary:
    return Glossary(glossary_id="g", version=1, language=language, name="Terms", entries=list(entries))


@pytest.mark.parametrize("language, entry, good, bad", [
    ("de-DE", GlossaryEntry(source_term="deviation", target_term="Abweichung"),
     "Alle Abweichungen erfassen.", "Alle Fehler erfassen."),
    ("ja-JP", GlossaryEntry(source_term="deviation", target_term="逸脱"), "すべての逸脱を記録する。", "すべての誤りを記録する。"),
    ("el-GR", GlossaryEntry(source_term="deviation", target_term="απόκλιση"),
     "Καταγράψτε όλες τις αποκλίσεις.", "Καταγράψτε όλα τα σφάλματα."),
])
def test_glossary_terms_are_required(language, entry, good, bad):
    glossary = _glossary(language, GlossaryEntry(source_term="SAP", do_not_translate=True, case_sensitive=True), entry)
    assert "GLOSSARY-2" not in codes("Record all deviations.", good, language, glossary)
    assert codes("Record all deviations.", bad, language, glossary)["GLOSSARY-2"] == Severity.HIGH
    assert codes("Record all deviations.", bad, language)  .get("GLOSSARY-2") is None  # no glossary: not checked
    assert codes("Enter it in SAP now.", "In S.A.P. eingeben.", language, glossary)["DNT-1"] == Severity.HIGH


def test_text_left_in_english_and_the_wrong_script():
    assert codes("Keep the records.", "Keep the records.")["UNTRANSLATED"] == Severity.MEDIUM
    assert codes("Scope", "Scope", kind=SegmentKind.TEMPLATE_TEXT)["UNTRANSLATED"] == Severity.LOW
    assert "UNTRANSLATED" not in codes("QA SOP", "QA SOP")  # abbreviations
    assert codes("Carsten Schacht, HPSC", "Carsten Schacht, HPSC")["UNTRANSLATED"] == Severity.LOW  # a name
    sap = _glossary("de-DE", GlossaryEntry(source_term="SAP", do_not_translate=True))
    assert codes("SAP", "SAP", glossary=sap) == {}

    assert codes("Record every deviation in the batch record.", "Record every deviation in 記録.", "ja-JP")[
        "SCRIPT"] == Severity.MEDIUM
    assert "SCRIPT" not in codes("Record every deviation in SAP.", "すべての逸脱をSAPに記録する。", "ja-JP")
    assert "SCRIPT" not in codes("GBS unITed Program", "GBS unITedプログラム", "ja-JP")  # names stay as written
    assert "SCRIPT" not in codes("Enter it in SAP Quality Management now.", "SAP Quality Managementに入力する。", "ja-JP",
                                 _glossary("ja-JP", GlossaryEntry(source_term="SAP Quality Management",
                                                                  do_not_translate=True)))
    assert codes("Record every deviation now.", "Record every deviation now please.", "el-GR")["SCRIPT"] == Severity.MEDIUM
    assert "SCRIPT" not in codes("Record every deviation now.", "Record every deviation now.", "de-DE")


def test_length_and_line_breaks():
    settings = Settings()
    long = "Record every deviation in the batch record within two working days."
    assert codes(long, "Kurz.", settings=settings)["LENGTH"] == Severity.LOW
    assert "LENGTH" not in codes(long, "Jede Abweichung innerhalb von zwei Arbeitstagen im Chargenprotokoll erfassen.",
                                 settings=settings)
    assert "LENGTH" not in codes("Short text", "Kurz", settings=settings)  # too short to judge
    assert codes("Line one\nLine two", "Zeile eins Zeile zwei")["LINE_BREAKS"] == Severity.MEDIUM


def test_the_report_carries_resolutions_and_picks_what_to_repair():
    segments = [_seg("Keep {{ref:SRC-1}}.", "Behalten.", n=1),
                _seg("Keep {{ref:SRC-2}}.", "Behalten.", origin=SegmentOrigin.REPAIR, n=2),
                _seg("Keep {{ref:SRC-3}}.", "Behalten.", origin=SegmentOrigin.HUMAN, n=3),
                _seg("Keep {{ref:SRC-4}}.", None, n=4),
                _seg("Two", "Zwei", n=5, kind=SegmentKind.TEMPLATE_TEXT),
                _seg("1.2", "1.2", origin=SegmentOrigin.COPIED, n=6)]
    report = check_translations("TRN-1", 1, segments, "de-DE")
    assert report.unit_coverage == round(5 / 6, 4) and report.soft_scores["copied"] == round(1 / 6, 4)
    assert repair_candidates(segments, report) == ["SEG-0001", "SEG-0004"]  # not repaired yet, not a human's edit
    assert report.gate_counts[Gate.NUMERICAL_CHANGE] == 0

    resolved = report.model_copy(deep=True)
    resolved.issues[0].resolved, resolved.issues[0].resolution_note = True, "the reference is not needed"
    again = check_translations("TRN-1", 2, segments, "de-DE", previous=resolved)
    assert again.issues[0].resolved and again.issues[0].resolution_note == "the reference is not needed"
    assert repair_candidates(segments, again) == ["SEG-0004"]
    assert worst(again.issues[:1]) == -1 and worst(again.issues) == 4


def test_every_segment_is_in_exactly_one_translation_set():
    segment_set = SegmentSet(job_id="TRN-1", migration_job_id="MIG-1", language="de-DE", version=1,
                             segments=[_seg("Keep the records.", None, n=1), _seg("Sign.", None, n=2)])
    translated = [s.model_copy(update={"target_text": "x", "origin": SegmentOrigin.LLM}) for s in segment_set.segments]

    def one(segments) -> TranslationSet:
        return TranslationSet(job_id="TRN-1", language="de-DE", scope="TGT-1", version=1, segments=segments)

    assert merged(segment_set, []) is segment_set
    assert [s.target_text for s in merged(segment_set, [one(translated)]).segments] == ["x", "x"]
    with pytest.raises(RuntimeError, match="in no translation set"):
        merged(segment_set, [one(translated[:1])])
    with pytest.raises(RuntimeError, match="two translation sets"):
        merged(segment_set, [one(translated), one(translated[1:])])
    with pytest.raises(RuntimeError, match="does not match"):
        merged(segment_set, [one([translated[0], translated[1].model_copy(update={"source_text": "Sign!"})])])
    with pytest.raises(RuntimeError, match="unknown segments"):
        extra = translated[1].model_copy(update={"segment_id": "SEG-0009"})
        merged(segment_set, [one([*translated, extra])])


def test_the_report_round_trips():
    report = check_translations("TRN-1", 1, [_seg("Keep {{ref:SRC-1}}.", "Behalten.")], "de-DE")
    assert QualityReport.model_validate_json(report.model_dump_json()).issues[0].segment_ids == ["SEG-0001"]
