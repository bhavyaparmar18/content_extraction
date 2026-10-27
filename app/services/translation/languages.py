"""The target languages: identity only (name, Word language code, script).

No writing-style rules live here. The translation follows the preservation rules
and, when the job has one, the language's glossary (with its style notes).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.v2.translation import LanguageCode


@dataclass(frozen=True)
class Language:
    code: LanguageCode
    name: str             # as shown to users and named in the prompt
    script: str           # "latin" | "greek" | "han" | "japanese"
    east_asian: bool      # Word needs w:eastAsia language and font for it

    @property
    def word_lang(self) -> str:
        return self.code.value


LANGUAGES: dict[LanguageCode, Language] = {
    lang.code: lang
    for lang in (
        Language(LanguageCode.ZH_CN, "Chinese (Simplified)", "han", True),
        Language(LanguageCode.FR_FR, "French", "latin", False),
        Language(LanguageCode.DE_DE, "German", "latin", False),
        Language(LanguageCode.IT_IT, "Italian", "latin", False),
        Language(LanguageCode.JA_JP, "Japanese", "japanese", True),
        Language(LanguageCode.PT_BR, "Portuguese (Brazil)", "latin", False),
        Language(LanguageCode.ES_ES, "Spanish", "latin", False),
        Language(LanguageCode.EL_GR, "Greek", "greek", False),
    )
}


def get_language(code: str | LanguageCode) -> Language:
    """The language for a code such as ``"fr-FR"``; ``ValueError`` for anything else."""
    try:
        return LANGUAGES[LanguageCode(code)]
    except ValueError:
        raise ValueError(f"unsupported language {code!r}; expected one of {[c.value for c in LanguageCode]}") from None
