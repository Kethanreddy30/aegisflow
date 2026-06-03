from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ── Request Models ────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    presence_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0)
    stop: Optional[Union[str, List[str]]] = None
    user: Optional[str] = None


# ── Response Models ───────────────────────────────────────────────────────────

class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatMessageResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessageResponse
    finish_reason: Optional[str] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: UsageInfo


# ── Streaming Models ──────────────────────────────────────────────────────────

class DeltaMessage(BaseModel):
    role: Optional[Literal["assistant"]] = None
    content: Optional[str] = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[StreamChoice]


# ── Gateway Internal Models ───────────────────────────────────────────────────

class ModelRoutingResult(BaseModel):
    """Result of 3-tier model routing decision."""
    resolved_model: str
    requested_model: str
    was_remapped: bool = False
    remap_reason: Optional[str] = None


class GatewayError(BaseModel):
    error: Dict[str, Any]

    @classmethod
    def make(cls, message: str, code: str = "gateway_error") -> "GatewayError":
        return cls(error={"message": message, "type": code})
