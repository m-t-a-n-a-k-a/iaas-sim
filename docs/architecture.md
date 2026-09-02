# Architecture

The Phase 2C-2 architecture remains intentionally small. VirtualMachine public identity is a
control-plane UUIDv7 persisted by the SQLite identity adapter; vSphere MORs remain backend-only
references. Application use cases project backend observations into Domain resources.

## Boundary

- Domain: pure logic and immutable state modeling. No I/O and no framework imports.
- Application: orchestration and port-based use cases for VM and Snapshot queries, async command submission, and Operation polling.
- Adapters: concrete HTTP, vSphere, in-memory Operation registry, telemetry, and external integrations.
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

Operations remain process-local and non-durable. Snapshot hierarchy is flattened inside the vSphere adapter; the domain and API expose independent top-level Snapshot resources.
