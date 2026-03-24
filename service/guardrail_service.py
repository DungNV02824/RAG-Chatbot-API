import re
from typing import Dict, List, Tuple


INJECTION_PATTERNS: List[str] = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior)\s+instructions?",
    r"forget\s+(all\s+)?(previous|prior)\s+instructions?",
    r"act\s+as\s+(a\s+)?(system|developer|admin|root)",
    r"you\s+are\s+now\s+",
    r"reveal\s+(the\s+)?(system|developer)\s+prompt",
    r"show\s+(the\s+)?(hidden|internal)\s+instructions?",
    r"bypass\s+(safety|policy|guardrail|restrictions?)",
    r"jailbreak",
    r"prompt\s+injection",
    r"```(?:system|developer|assistant)",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def scan_prompt_injection(text: str) -> Dict[str, object]:
    """
    Lightweight detector for prompt-injection indicators.
    Returns risk score and matched patterns for policy decisions.
    """
    if not text:
        return {"is_suspicious": False, "risk_score": 0, "matches": []}

    matches: List[str] = []
    risk_score = 0

    for pattern in COMPILED_PATTERNS:
        found = pattern.search(text)
        if found:
            matches.append(pattern.pattern)
            risk_score += 1

    # Extra weight if many role-like tokens are stacked
    lowered = text.lower()
    stacked_roles = sum(token in lowered for token in ["system:", "developer:", "assistant:"])
    if stacked_roles >= 2:
        risk_score += 1
        matches.append("stacked_role_tokens")

    return {
        "is_suspicious": risk_score > 0,
        "risk_score": risk_score,
        "matches": matches,
    }


def sanitize_untrusted_history(chat_history: str) -> Tuple[str, Dict[str, object]]:
    """
    Remove suspicious lines from chat history before forwarding to LLM.
    """
    if not chat_history:
        return chat_history, {"removed_lines": 0, "is_suspicious": False, "risk_score": 0, "matches": []}

    kept_lines: List[str] = []
    removed_lines = 0
    aggregate_matches: List[str] = []
    highest_risk = 0

    for line in chat_history.splitlines():
        result = scan_prompt_injection(line)
        if result["is_suspicious"]:
            removed_lines += 1
            aggregate_matches.extend(result["matches"])
            highest_risk = max(highest_risk, int(result["risk_score"]))
            continue
        kept_lines.append(line)

    sanitized = "\n".join(kept_lines)
    report = {
        "removed_lines": removed_lines,
        "is_suspicious": removed_lines > 0,
        "risk_score": highest_risk,
        "matches": sorted(set(aggregate_matches)),
    }
    return sanitized, report

