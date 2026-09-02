# Domain Model

Phase 2A keeps the business domain deliberately narrow rather than modeling a complete cloud.

The implemented domain consists of:

- immutable `VirtualMachine` identity, name, and observed backend power state
- pure START/STOP command validation against that observed state
- immutable `Operation` identity, target, action, and `Running | Succeeded | Failed` status

The application submits power commands asynchronously and polls their opaque backend operation references through ports. The public UUIDv7 `OperationId` remains distinct from backend identity. Operations are not persisted in Phase 2A.

IAM, accounts, volumes, networks, metering, reconciliation, queues, retry, cancellation, and progress remain outside the current domain scope.
