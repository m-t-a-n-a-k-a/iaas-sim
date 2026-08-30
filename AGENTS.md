# AGENTS.md

This repository follows strict Phase 1 constraints.

- Functional Domain-Driven Design
- Functional Core + Imperative Shell
- Hexagonal Architecture
- Pyright strict
- no Any
- immutable Domain
- pure Domain
- architecture import rules
- Entity -> top-level Resource
- Value Object -> embedded
- Resource nesting forbidden
- PUT forbidden
- Command -> POST :verb
- operational health is not Domain
- `make verify` is required

Rules:

1. Do not implement fake business domain models in Phase 1.
2. Keep the architecture small and explicit.
3. Use immutable data and pure functions where domain logic exists.
4. Keep adapters and infrastructure outside the domain layer.
5. Do not bypass static typing with `Any`, `cast`, or `type: ignore`.
6. Use `make verify` as the required quality gate before completion.
