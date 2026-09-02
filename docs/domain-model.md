# Domain Model

Phase 2B keeps the business domain deliberately narrow rather than modeling a complete cloud.

The implemented domain consists of:

- immutable `VirtualMachine` identity, name, and observed backend power state
- pure START/STOP command validation against that observed state
- immutable `Operation` identity, target, action, and `Running | Succeeded | Failed` status
- immutable, backend-observed `Snapshot` identity, name, and a `ResourceReference` to its owning VirtualMachine

The application submits power commands asynchronously and polls their opaque backend operation references through ports. The public UUIDv7 `OperationId` remains distinct from backend identity. Operations are not persisted in Phase 2A.

Snapshots are flat top-level resources. Snapshot trees, revert, rename, memory/quiesce options, persistence, and speculative control-plane snapshot identities remain outside the scope.
