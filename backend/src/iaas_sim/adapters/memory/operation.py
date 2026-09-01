from iaas_sim.application.operation import TrackedOperation
from iaas_sim.domain.entity.operation import OperationId


class InMemoryOperationRegistry:
    """Process-local Phase 2A correlation registry; intentionally not durable."""

    def __init__(self) -> None:
        self._operations: dict[OperationId, TrackedOperation] = {}

    def add(self, operation: TrackedOperation) -> None:
        self._operations[operation.id] = operation

    def get(self, operation_id: OperationId) -> TrackedOperation | None:
        return self._operations.get(operation_id)
