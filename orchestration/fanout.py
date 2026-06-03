from typing import Awaitable, Any
import asyncio


async def execute_parallel(
    tasks: list[Awaitable[Any]],
) -> list[Any]:
    return await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )
