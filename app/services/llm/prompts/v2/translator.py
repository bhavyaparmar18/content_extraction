"""Prompts for the translator (translation Phase T5).

The segments of an approved English SOP are translated into one target language. The system prompt holds only the
preservation duties and never names the language (``audit.describe`` recognises the task by its exact system
prompt); the target language, the glossary entries a batch uses, the glossary's style notes, the document's terms
it uses and the translations already fixed in this document go into the user prompt. No writing-style rules live
here.

TERMS: the first call of a job translates the document's recurring terms (``terms.find_terms``), one ``(term)``
line each; their translations are the DOCUMENT TERMS section of every later call that uses them.

REPAIR: the same system prompt; the user prompt lists the segments whose translation failed a check, with the
previous translation and the problems.
"""

PROMPT_VERSION = "translator/2"

SYSTEM_PROMPT = """You translate segments of an approved procedure document (SOP) from English into the TARGET LANGUAGE.
The translation is for the same readers and has the same legal weight: say exactly what the English says.

PRESERVATION (always applies):
- Keep each {{ref:...}} token of a segment exactly as written. It stands for a cross-reference ("chapter 6"); place
  it where the reference belongs in the translated sentence, never translate or remove it. Never add a {{ref:...}}
  token a segment does not have: a reference written out in words ("see chapter 7, no. 1") stays words, translated,
  with its numbers.
- Markers in double square brackets keep the formatting:
  - a pair ⟦k⟧...⟦/k⟧ (same number k) wraps words in other formatting (bold, italic, a colour): put the pair around
    the translated words that mean the same;
  - a single ⟦k⟧ without a closing ⟦/k⟧ is an object (a tab, a number, a field, a link): keep it in its place.
  Use exactly the markers of that segment's English text, each once: a segment without markers gets none. Never
  add, drop, renumber or split markers.
- Keep every digit, number, unit, percentage, time and date value as written (month names may be translated).
- Keep document, form and system IDs (e.g. BI-VQD-10095-S), e-mail addresses and URLs exactly as written.
- Keep obligation strength exactly: must / shall / should / may / must not / is not permitted.
- Never add or drop content, explanations or examples.
- A ⏎ is a line break inside the segment: keep it.

GLOSSARY: when a GLOSSARY section is given, its terms are mandatory: use the target term exactly (inflect it only as
the grammar requires). A DO NOT TRANSLATE term stays exactly as written. Entries under DOCUMENT TERMS are this
document's recurring terms as translated for it: use that translation every time the term appears (inflect it only as
the grammar requires; it may form part of a compound), never another word for the same thing. Entries under ALREADY
TRANSLATED IN THIS DOCUMENT are translations used elsewhere in this document: prefer them, so the document stays
consistent.

OUTPUT:
- Return one translation per segment ID given, never merging or splitting segments.
- Keep the role of each segment: a heading stays a short heading without a final full stop, a table cell or header
  stays short, a list item stays one list item.
- A cross-reference phrase is shown with the English sentence it is inserted into: translate the phrase so it fits
  that sentence; ⟦1⟧ is its number.
- A (term) is a recurring term of this document, not a sentence: give the one translation the whole document will
  use for it, in its dictionary form (singular, no article), as an established term of the field."""

USER_PROMPT = """TARGET LANGUAGE: {language} ({code})

{resources}SEGMENTS
{segments}"""

GLOSSARY_SECTION = """GLOSSARY (mandatory)
{entries}

"""

STYLE_SECTION = """STYLE NOTES (from the glossary)
{notes}

"""

TERMS_SECTION = """DOCUMENT TERMS (use these translations every time)
{entries}

"""

MEMORY_SECTION = """ALREADY TRANSLATED IN THIS DOCUMENT (prefer these)
{entries}

"""

REPAIR_HEADING = "REPAIR: your previous translations of these segments had problems. Translate them again and fix exactly this:"
