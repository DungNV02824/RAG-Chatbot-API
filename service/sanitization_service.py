import re
from typing import Dict, List, Optional, Tuple


PII_PATTERNS: List[Tuple[str, str, str]] = [
    ("email", r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", "[REDACTED_EMAIL]"),
    (
        "phone_vi",
        r"(?<!\d)(?:\+?84|0)(?:\d[\s.\-]?){8,10}\d(?!\d)",
        "[REDACTED_PHONE]",
    ),
    ("national_id", r"\b\d{9}\b|\b\d{12}\b", "[REDACTED_NATIONAL_ID]"),
    ("credit_card", r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED_CARD]"),
    ("ipv4", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[REDACTED_IP]"),
]

COMPILED_PII = [(name, re.compile(pattern), replacement) for name, pattern, replacement in PII_PATTERNS]


def sanitize_text_for_llm(text: str) -> Tuple[str, Dict[str, object]]:
    """
    Mask common PII patterns before sending text to LLM.
    Returns sanitized text and a report for observability.
    """
    if not text:
        return text, {"is_sanitized": False, "total_replacements": 0, "items": {}}

    sanitized = text
    total_replacements = 0
    items: Dict[str, int] = {}

    for pii_name, compiled_pattern, replacement in COMPILED_PII:
        sanitized, count = compiled_pattern.subn(replacement, sanitized)
        if count > 0:
            items[pii_name] = count
            total_replacements += count

    report = {
        "is_sanitized": total_replacements > 0,
        "total_replacements": total_replacements,
        "items": items,
    }
    return sanitized, report


def sanitize_text_for_llm_with_mapping(
    text: str,
    mapping: Optional[Dict[str, str]] = None,
    next_index: int = 1,
) -> Tuple[str, Dict[str, object], Dict[str, str], int]:
    """
    Sanitize text using reversible placeholders so we can restore response
    content for end users after LLM generation.
    """
    if mapping is None:
        mapping = {}
    reverse_mapping = {value: key for key, value in mapping.items()}

    sanitized = text or ""
    total_replacements = 0
    items: Dict[str, int] = {}

    for pii_name, compiled_pattern, _ in COMPILED_PII:
        def _replace(match: re.Match) -> str:
            nonlocal next_index, total_replacements
            original = match.group(0)
            placeholder = reverse_mapping.get(original)
            if not placeholder:
                placeholder = f"[PII_{next_index}]"
                next_index += 1
                mapping[placeholder] = original
                reverse_mapping[original] = placeholder
            total_replacements += 1
            return placeholder

        sanitized, count = compiled_pattern.subn(_replace, sanitized)
        if count > 0:
            items[pii_name] = count

    report = {
        "is_sanitized": total_replacements > 0,
        "total_replacements": total_replacements,
        "items": items,
    }
    return sanitized, report, mapping, next_index


def restore_text_from_mapping(text: str, mapping: Optional[Dict[str, str]]) -> str:
    """Restore reversible placeholders back to original text."""
    if not text or not mapping:
        return text

    restored = text
    for placeholder in sorted(mapping.keys(), key=len, reverse=True):
        restored = restored.replace(placeholder, mapping[placeholder])
    return restored

