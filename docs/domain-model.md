# Domain Model

Phase 2B keeps the business domain deliberately narrow rather than modeling a complete cloud.

The implemented domain consists of:

- immutable `VirtualMachine` UUIDv7 public identity, name, and observed backend power state
- pure START/STOP command validation against that observed state
- immutable `Operation` identity, target, action, and `Running | Succeeded | Failed` status
- immutable `Snapshot` UUIDv7 public identity, name, and a `ResourceReference` to its owning VirtualMachine

The application submits power commands asynchronously and polls their opaque backend operation references through ports. The public UUIDv7 `OperationId` remains distinct from backend identity. Operations are not persisted in Phase 2A.

Snapshots are flat top-level resources. Snapshot trees, revert, rename, memory/quiesce options, persistence, and speculative control-plane snapshot identities remain outside the scope.
Snapshot public identity is a persisted UUIDv7 in Phase 2C-3. Its vSphere MOR and owning VM
relationship remain backend/application concerns and never become public resource identity.
