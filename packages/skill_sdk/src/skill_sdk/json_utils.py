from __future__ import annotations

import json


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return cleaned


def _escape_string_newlines(text: str) -> str:
    """Escape literal newline/carriage-return characters inside JSON string values.

    Haiku sometimes writes multi-paragraph text directly into JSON string values
    without escaping the newlines, producing malformed JSON.  This walks the text
    character-by-character and replaces bare newlines/CRs that appear inside a
    JSON string with their escaped equivalents.
    """
    result: list[str] = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and in_string and i + 1 < len(text):
            # Pass through escape sequences unchanged
            result.append(c)
            result.append(text[i + 1])
            i += 2
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
        elif c == "\n" and in_string:
            result.append("\\n")
        elif c == "\r" and in_string:
            result.append("\\r")
        else:
            result.append(c)
        i += 1
    return "".join(result)


def parse_llm_json(raw_text: str) -> object:
    """Parse JSON from LLM output, handling common Haiku failure modes:

    1. Markdown code fences (```json ... ```)
    2. Literal unescaped newlines inside string values
    """
    cleaned = _strip_fences(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    sanitized = _escape_string_newlines(cleaned)
    return json.loads(sanitized)
