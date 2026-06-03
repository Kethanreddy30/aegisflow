from enum import Enum
from dataclasses import dataclass


class IntentType(str, Enum):
    TRIVIAL = "trivial"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass(slots=True)
class RouteDecision:
    intent: IntentType
    target: str
    reason: str = ""
