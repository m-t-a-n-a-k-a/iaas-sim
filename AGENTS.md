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
8. Debugging discipline:
   - Do not treat an observed symptom as the root cause without validating the hypothesis with additional evidence.
   - Before claiming the root cause, verify the expected facts implied by that hypothesis with concrete commands.
   - If any observation remains contradictory, do not declare the issue resolved; continue the investigation.
   - Prefer actual command output and measured behavior over speculation.
   - Debugging and verification must follow the intended execution path.
   - Incidental development-environment paths must not be promoted to product requirements without a real requirement.
   - A failure outside the intended execution path should be classified separately rather than blocking completion automatically.
   - When `make verify` fails, continue root-cause tracing, fix, and re-test within the current change scope until the failure is resolved.
   - Do not complete work with fake success, swallowed exceptions, weakened tests, or ignored failures.
   - Separate the root cause from the workaround; if a workaround is used, explicitly record that the underlying cause remains unresolved.

Future design notes:

- IAM: Principal × Scope × Role
- Scope: Provider, Account(accountId)
- Role: cloudAdmin, accountAdmin, viewer
- OIDC identity: issuer + subject
- Unknown OIDC identity: do not create JIT Principal
- Metering: Compute Usage = VM RUNNING time; Volume Usage = provisioned GiB × existence time
- Metering and OpenTelemetry metrics are separate concerns
- Long-running operations are modeled later as asynchronous command + Operation Resource, not implemented in Phase 1

Result / Railway policy:

- Use a project-local Ok / Err / Result primitive; do not add external FP libraries.
- Expected failures are typed Result values, not exceptions, and are propagated as control flow.
- Prefer railway-style pipelines: input -> Result -> Result -> Result -> output, and stop on the first Err.
- Adapter boundaries may catch external exceptions and convert them to typed Err values; domain and application code should not use try/except for expected failures.
- Use ADT / Enum / Union + match for meaningful states; keep simple booleans and if statements where they are clearer.
- State transitions should prefer table-driven or decision-table logic over nested if/else chains.
- Exceptions are for unexpected programming errors and bootstrap boundary handling, not for expected domain/application failures.
- Keep the Result API minimal; do not build a custom FP framework or broad helper ecosystem before a real need exists.
- Keep Pyright strict and readable; avoid Any, cast, or type: ignore when narrowing Result values.

Testing policy:

- When behavior is determined by combinations of finite states, commands, roles, scopes, or inputs, prefer table-driven tests using pytest.mark.parametrize.
- The table should expose the relevant state space explicitly rather than duplicating one test function per case.
- Use descriptive pytest.param(..., id="...") identifiers.
- Do not force parametrization onto one-off integration/smoke tests where there is no meaningful case matrix.
