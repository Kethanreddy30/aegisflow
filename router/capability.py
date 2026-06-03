from enum import Enum


class Capability(str, Enum):
    CHAT = "chat"
    CODE = "code"
    REASONING = "reasoning"
    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
