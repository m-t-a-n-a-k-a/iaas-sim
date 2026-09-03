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

## Blank VirtualMachine creation

The public request contains a name and InstanceType Resource Reference. Application orchestration
resolves and validates the name, vCPU count, and memory MiB before backend submission. The vSphere
adapter adds an internal `extraConfig` marker containing the future public UUID and submits one
`CreateVM_Task` without powering on the VM. Marked VMs without a finalized identity mapping are not
auto-adopted. The Task result VM MOR stays internal and is bound to the future UUID in the same
SQLite transaction that changes the CREATE Operation to `SUCCEEDED`. The schema remains version 3.
