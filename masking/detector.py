import re
from typing import List, Tuple
from enum import Enum


class PIIType(str, Enum):
    EMAIL   = "EMAIL"
    PHONE   = "PHONE"
    SSN     = "SSN"
    IP      = "IP"
    CC      = "CC"
    ACCOUNT = "ACCOUNT"


# Order matters — more specific patterns first
# CC before PHONE to avoid partial matches
_PATTERNS: List[Tuple[PIIType, re.Pattern]] = [
    (PIIType.EMAIL,
     re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')),

    (PIIType.SSN,
     re.compile(r'\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b')),

    (PIIType.CC,
     re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?'        # Visa
                r'|5[1-5][0-9]{14}'                     # MC
                r'|3[47][0-9]{13}'                      # Amex
                r'|6(?:011|5[0-9]{2})[0-9]{12})\b')),  # Discover

    (PIIType.IP,
     re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
                r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b')),

    (PIIType.PHONE,
     re.compile(r'\b(?:\+?1[-.\s]?)?'
                r'(?:\(\d{3}\)|\d{3})'
                r'[-.\s]?\d{3}[-.\s]?\d{4}\b')),

    (PIIType.ACCOUNT,
     re.compile(r'\b(?:acct|account|acc)[\s#:]*\d{6,17}\b',
                re.IGNORECASE)),
]


class PIIMatch:
    __slots__ = ("pii_type", "value", "start", "end")

    def __init__(self, pii_type: PIIType, value: str, start: int, end: int):
        self.pii_type = pii_type
        self.value    = value
        self.start    = start
        self.end      = end


def detect(text: str) -> List[PIIMatch]:
    """
    Detect all PII in text.
    Returns list of PIIMatch sorted by position.
    Overlapping matches: first pattern wins (most specific).
    """
    matches: List[PIIMatch] = []
    covered: set = set()

    for pii_type, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            span = set(range(m.start(), m.end()))
            if span & covered:
                continue  # overlapping — skip
            covered |= span
            matches.append(PIIMatch(
                pii_type=pii_type,
                value=m.group(),
                start=m.start(),
                end=m.end(),
            ))

    return sorted(matches, key=lambda x: x.start)


def has_pii(text: str) -> bool:
    """Fast check — returns True if any PII detected."""
    for _, pattern in _PATTERNS:
        if pattern.search(text):
            return True
    return False
