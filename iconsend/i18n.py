"""Small bilingual catalogue; follows the desktop language without extra tools."""

import os


def tr(english: str, chinese: str) -> str:
    language = os.environ.get("LANGUAGE") or os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "")
    return chinese if language.split(":")[0].lower().startswith("zh") else english
