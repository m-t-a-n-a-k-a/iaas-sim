# Domain Model

Phase 2B keeps the business domain deliberately narrow rather than modeling a complete cloud.

The implemented domain consists of:

- immutable `VirtualMachine` UUIDv7 public identity, name, and observed backend power state
- pure START/STOP command validation against that observed state
- immutable `Operation` identity, target, action, and `Running | Succeeded | Failed` status
- immutable `Snapshot` UUIDv7 public identity, name, and a `ResourceReference` to its owning VirtualMachine

The application submits commands asynchronously and persists the resulting RUNNING Operation.
The public UUIDv7 `OperationId` remains distinct from the internal backend correlation identity.
SQLite is the source of truth for public Operation state; backend polling is only an observation
used to persist the one-way `RUNNING -> SUCCEEDED | FAILED` transition.

Snapshots are flat top-level resources. Snapshot trees, revert, rename, memory/quiesce options, persistence, and speculative control-plane snapshot identities remain outside the scope.
Snapshot public identity is a persisted UUIDv7 in Phase 2C-3. Its vSphere MOR and owning VM
relationship remain backend/application concerns and never become public resource identity.
