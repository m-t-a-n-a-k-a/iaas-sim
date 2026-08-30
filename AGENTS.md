# AGENTS.md

This repository follows strict Phase 1 constraints.

Architecture:

- Functional Domain-Driven Design
- Functional Core + Imperative Shell
- Hexagonal Architecture
- Domain purity
- strict Python typing
- Adapter-to-adapter direct dependency forbidden
- Operational health is not Domain
- `make verify` is required

API:

- Entity -> top-level Resource
- Value Object -> embedded
- Resource nesting forbidden
- Resource Reference
- PUT forbidden
- POST :verb

Domain filesystem:

- `domain/entity/{entity}/` is the baseline structure for future domain entities
- Domain model is intentionally empty in Phase 1

Rules:

1. Do not implement fake business domain models in Phase 1.
2. Keep the architecture small and explicit.
3. Use immutable data and pure functions where domain logic exists.
4. Keep adapters and infrastructure outside the domain layer.
5. Do not bypass static typing with `Any`, `cast`, or `type: ignore`.
6. Use `make verify` as the required quality gate before completion.
7. Do not add direct adapter-to-adapter imports; compose them in the bootstrap layer or through application ports.

Future design notes:

- IAM: Principal × Scope × Role
- Scope: Provider, Account(accountId)
- Role: cloudAdmin, accountAdmin, viewer
- OIDC identity: issuer + subject
- Unknown OIDC identity: do not create JIT Principal
- Metering: Compute Usage = VM RUNNING time; Volume Usage = provisioned GiB × existence time
- Metering and OpenTelemetry metrics are separate concerns
- Long-running operations are modeled later as asynchronous command + Operation Resource, not implemented in Phase 1
