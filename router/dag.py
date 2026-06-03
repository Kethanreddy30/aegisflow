from dataclasses import dataclass
from typing import List


@dataclass(slots=True)
class DAGNode:
    name: str


@dataclass(slots=True)
class ExecutionDAG:
    nodes: List[DAGNode]
