
import re
from dataclasses import dataclass


@dataclass
class InjectionCheckResult:
    is_suspicious: bool
    matched_patterns: list[str]


# These patterns identify common attempts to override instructions
# or extract hidden system information.
INJECTION_PATTERNS = {
    "ignore_previous_instructions": (
        r"\b(ignore|disregard|forget|override)\b.{0,60}"
        r"\b(previous|prior|above|all)\b.{0,30}"
        r"\b(instructions|prompts|rules|directions)\b"
    ),
    "reveal_system_prompt": (
        r"\b(reveal|show|print|display|repeat|output)\b.{0,60}"
        r"\b(system prompt|hidden prompt|developer message|"
        r"internal instructions)\b"
    ),
    "role_override": (
        r"\b(you are now|act as|pretend to be)\b.{0,60}"
        r"\b(system|developer|administrator|unrestricted|"
        r"jailbroken)\b"
    ),
    "instruction_override": (
        r"\b(new instructions|updated instructions|"
        r"replacement instructions|highest priority instruction)\b"
    ),
    "secret_extraction": (
        r"\b(reveal|expose|print|output|disclose)\b.{0,60}"
        r"\b(secrets|api keys|passwords|credentials|"
        r"access tokens)\b"
    ),
}

COMPILED_PATTERNS = {
    name: re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for name, pattern in INJECTION_PATTERNS.items()
}


def check_prompt_injection(text: str) -> InjectionCheckResult:
    """
    Check text for common prompt-injection patterns.

    This is a heuristic detector, not a guarantee that text is safe.
    """
    if not isinstance(text, str):
        raise TypeError("Input must be a string.")

    matched_patterns = [
        name
        for name, pattern in COMPILED_PATTERNS.items()
        if pattern.search(text)
    ]

    return InjectionCheckResult(
        is_suspicious=bool(matched_patterns),
        matched_patterns=matched_patterns,
    )
