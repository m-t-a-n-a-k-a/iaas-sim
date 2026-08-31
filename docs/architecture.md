# Architecture

This Phase 1 repository is intentionally small.

## Boundary

- Domain: pure logic and state modeling. No I/O and no framework imports.
- Application: orchestration and port-based use cases.
- Adapters: concrete HTTP, vSphere, SQLite, telemetry, and external integrations.
- Bootstrap: composition root and dependency wiring.

## Constraints

- No mutable domain state.
- No business logic in HTTP handlers.
- No direct use of FastAPI or pyVmomi from the domain.
- No health model in the domain; health is operational.
- No fake domain classes for future entities in Phase 1.
- Use a project-local Result primitive instead of external FP libraries.
- Treat expected failures as typed Result values, not as exceptions propagated across the application.
- Prefer railway-oriented composition over nested if/else or try/except chains for expected failure propagation.
- Convert external exceptions only at adapter boundaries into typed Err values; unexpected runtime failures remain handled at the process boundary.
