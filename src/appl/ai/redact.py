import os
import re

_PATTERNS = [
    (re.compile(r"(?i)\b(key|api_key|apikey|access_token|token)=[^&\s'\"]+"), r"\1=***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer ***"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"), "sk-***"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{10,}"), "AIza***"),
]
_SECRET_ENV = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD)$", re.IGNORECASE)


def scrub_secrets(text: str) -> str:
    """Remove API keys / tokens from text that may be shown, logged or sent to a client."""
    for name, value in os.environ.items():
        if value and len(value) >= 8 and _SECRET_ENV.search(name):
            text = text.replace(value, "***")
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
