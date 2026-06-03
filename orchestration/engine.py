from abc import ABC, abstractmethod
from typing import Any


class Orchestrator(ABC):

    @abstractmethod
    async def execute(
        self,
        tenant_id: str,
        request: Any,
    ) -> Any:
        ...
