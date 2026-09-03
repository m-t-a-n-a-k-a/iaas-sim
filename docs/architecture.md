# Architecture

The Phase 2D architecture remains intentionally small. VirtualMachine and Snapshot public
identities are control-plane UUIDv7 values persisted by the SQLite identity adapter; vSphere MORs
remain backend-only references. Application use cases project backend observations into Domain
resources.
Control-plane-owned InstanceTypes are persisted directly in SQLite with UUIDv7 public identities;
they have no vSphere identity or mapping.

## Boundary

- Domain: pure logic and immutable state modeling. No I/O and no framework imports.
- Application: orchestration and port-based use cases for VM, Snapshot, and InstanceType queries, async command submission, and Operation polling.
- Adapters: concrete HTTP, vSphere, SQLite identity and Operation stores, telemetry, and external integrations.
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
- Prefer railway-oriented composition over nested if/else or try/except chains for expected failure propagation.
- Convert external exceptions only at adapter boundaries into typed Err values; unexpected runtime failures remain handled at the process boundary.

Operations are durable control-plane Resources. Their public state and safe failure reason are
stored in SQLite, while the opaque backend reference remains internal correlation data. GET polls
the backend only for persisted RUNNING Operations and compare-and-set persists terminal state
before exposing it. There is intentionally no worker or retry: a submitted backend task can be
orphaned if the following database insert fails, and an unqueried completed task remains RUNNING
until the next read-through reconciliation.
