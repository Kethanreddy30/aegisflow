import json
import time
import uuid
import structlog
from typing import AsyncIterator
from fastapi.responses import StreamingResponse
from gateway.schemas import ChatCompletionChunk, DeltaMessage, StreamChoice

logger = structlog.get_logger()


def _make_chunk(chunk_id: str, model: str, content: str, finish_reason=None) -> str:
    """Serialize one SSE chunk to wire format."""
    chunk = ChatCompletionChunk(
        id=chunk_id,
        created=int(time.time()),
        model=model,
        choices=[StreamChoice(
            delta=DeltaMessage(content=content),
            finish_reason=finish_reason,
        )],
    )
    return f"data: {chunk.model_dump_json()}\n\n"


def _make_done() -> str:
    return "data: [DONE]\n\n"


async def stream_ollama_response(
    ollama_stream: AsyncIterator,
    model: str,
) -> AsyncIterator[str]:
    """
    Consume Ollama async stream, yield SSE chunks.
    Ollama yields dicts with 'message.content' and 'done' fields.
    """
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    try:
        async for part in ollama_stream:
            content = part.get("message", {}).get("content", "")
            done = part.get("done", False)

            if content:
                yield _make_chunk(chunk_id, model, content)

            if done:
                # Final chunk with finish_reason
                yield _make_chunk(chunk_id, model, "", finish_reason="stop")
                yield _make_done()
                return

    except Exception as e:
        logger.error("stream_error", error=str(e))
        # Send error as final chunk so client knows stream died
        error_payload = json.dumps({"error": str(e)})
        yield f"data: {error_payload}\n\n"
        yield _make_done()


def make_streaming_response(generator: AsyncIterator[str]) -> StreamingResponse:
    """Wrap async generator in FastAPI StreamingResponse with correct SSE headers."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )
