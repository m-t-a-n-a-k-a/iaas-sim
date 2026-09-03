# Architecture

The project uses **Functional Core + Imperative Shell with typed Results** while keeping the
architecture intentionally small. VirtualMachine and Snapshot public
identities are control-plane UUIDv7 values persisted by the SQLite identity adapter; vSphere MORs
remain backend-only references. Application use cases project backend observations into Domain
resources.
Control-plane-owned InstanceTypes are persisted directly in SQLite with UUIDv7 public identities;
they have no vSphere identity or mapping.

## Boundary

- Domain: pure logic and immutable state modeling. No I/O and no framework imports.
- Application: imperative, top-to-bottom orchestration of pure Domain functions and Ports for VM, Snapshot, and InstanceType queries, async command submission, and Operation polling.
- Adapters: the imperative shell for concrete HTTP, vSphere, SQLite identity and Operation stores, telemetry, and external integrations.
- Bootstrap: composition root and dependency wiring.

## Constraints

- No mutable domain state.
- No business logic in HTTP handlers.
- No direct use of FastAPI or pyVmomi from the domain.
- No health model in the domain; health is operational.
- No speculative domain classes for future entities.
- No direct adapter-to-adapter dependencies.
- Use a project-local Result primitive instead of external FP libraries.
- Treat expected failures as typed Result values, not as exceptions propagated across the application.
- Keep Application happy paths visible from top to bottom. Explicit `Err` early returns are appropriate for sequential effects.
- Use `map`, `map_error`, and `and_then` only when they improve local clarity. Result combinators are an implementation technique, not an architectural requirement; nested Railway composition is not a goal.
- Ensure downstream effects consume validated or transformed values rather than bypassing them with earlier inputs.
- Convert external exceptions only at adapter boundaries into typed Err values; unexpected runtime failures remain handled at the process boundary.

Operations are durable control-plane Resources. Their public state and safe failure reason are
stored in SQLite, while the opaque backend reference remains internal correlation data. GET polls
the backend only for persisted RUNNING Operations and compare-and-set persists terminal state
before exposing it. There is intentionally no worker or retry: a submitted backend task can be
orphaned if the following database insert fails, and an unqueried completed task remains RUNNING
until the next read-through reconciliation.

## Phase 2E-1 blank VM backend primitive

The Application boundary defines a resolved create specification containing only a primitive name,
vCPU count, and memory MiB. InstanceType resolution remains outside the vSphere adapter. The
adapter deterministically sorts inventory candidates by name and MOR, then chooses the first
datacenter VM folder, resource pool, and datastore. It submits one `CreateVM_Task` with a generic
guest, no disks or NICs, and no power-on task, returning only the opaque Task MOR. The future public
VM UUID and Task-result-to-VM identity binding remain deferred to Phase 2E-2; no schema or public
HTTP route is added in Phase 2E-1.
