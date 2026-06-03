from dataclasses import dataclass


@dataclass(slots=True)
class RoutingPolicy:
    max_tokens: int = 8192
    allow_external: bool = True
    allow_reasoning: bool = True
