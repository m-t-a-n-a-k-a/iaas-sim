# AGENTS.md

This repository implements a small IaaS control plane while keeping its architecture explicit.

Architecture:

- Functional Domain-Driven Design
- Functional Core + Imperative Shell
- Hexagonal Architecture
- Domain purity
- strict static typing
- Adapter-to-adapter direct dependency forbidden
- Operational health is not Domain
- `make verify` is required

Migration status:

- The target backend language is Kotlin/JVM, built with Maven.
- `backend/` is the current Python executable, behavior, and architecture reference implementation.
- `backend-kotlin/` is the incremental target implementation.
- Migration proceeds incrementally through vertical slices, not as a big-bang rewrite.
- Do not port behavior beyond the explicitly requested migration phase.

Kotlin principles:

- Prefer immutable data and `val`; prefer `data class` for immutable data.
- Model meaningful finite states with `sealed interface` or `enum class`, and branch with exhaustive `when` expressions.
- Do not allow unchecked Java nullable or platform types to flow into Domain or Application code.
- Handle VMware Java SDK exceptions at Adapter boundaries.
- As a rule, do not use `!!`, unchecked casts, or `Any` as typing escape hatches.
- Do not add speculative framework abstractions.

Kotlin expected-failure policy:

- Model expected Domain and Application failures with the project-local, typed `Outcome<T, E>`.
- Do not use `kotlin.Result` for expected Domain or Application failures.
- Expected failures are values, not `Exception` or `Throwable` types.
- Keep `Outcome` minimal rather than growing it into an FP helper ecosystem.
- Add helpers or combinators only after concrete repeated use demonstrates a need.

Kotlin build simplicity:

- Use a single-module Maven build and the official Maven Wrapper `only-script` mode.
- Pin a stable Maven 3 release and use JDK 21; do not use Gradle.
- Do not add Maven profiles or split into multiple modules without a concrete requirement.
- Do not add custom Maven extensions or a build-framework ecosystem.
- Prefer top-level Makefile targets for developer-facing commands.

API:

- Entity -> top-level Resource
- Value Object -> embedded
- Resource nesting forbidden
- Resource Reference
- PUT forbidden
- POST :verb

Domain filesystem:

- `domain/entity/{entity}/` is the baseline structure for domain entities
- VirtualMachine, Snapshot, Operation, and InstanceType are the implemented Resources; do not infer unimplemented future domain behavior.

Rules:

1. Do not add speculative business domain models or proceed beyond the requested phase.
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

Documentation:

- `README.md` and `README-ja.md` are English and Japanese peer versions of the same project overview and must remain semantically synchronized; neither document is subordinate to the other.
- Any addition, update, or deletion that materially changes project purpose, architecture, stack, implemented Resources, persistence, asynchronous Operation semantics, Result workflow policy, setup or Codespaces commands, current limitations, or other substantive information in one README must update the corresponding content in the other README in the same change.
- Semantic equivalence is required, not word-for-word translation. Do not leave stale information in either README when removing or revising content in the other.

Future design notes:

- IAM: Principal × Scope × Role
- Scope: Provider, Account(accountId)
- Role: cloudAdmin, accountAdmin, viewer
- OIDC identity: issuer + subject
- Unknown OIDC identity: do not create JIT Principal
- Metering: Compute Usage = VM RUNNING time; Volume Usage = provisioned GiB × existence time
- Metering and OpenTelemetry metrics are separate concerns

Current control-plane invariants:

- VirtualMachine and Snapshot use control-plane UUIDv7 identities mapped to backend identities.
- InstanceType is a control-plane-owned Resource and has no backend identity mapping.
- VirtualMachine.power_state represents **observed backend state**, not desired state
- Power operations (START, STOP) are asynchronous; backend-specific submission details remain in adapters
- Domain validation (validate_power_command) is pure: checks command validity against observed state, no side effects
- Operation is a persistent control-plane Resource. Its state is stored in SQLite.
- OperationId (UUIDv7) is distinct from the opaque backend operation reference, which remains internal.
- Command acceptance (HTTP 202 Accepted) ≠ command completion
  - Synchronous failure: validation error or submission failure → HTTP 4xx/5xx
  - Asynchronous failure: backend operation failure → Operation.state = FAILED
- No concurrent power operations policy yet (collect requirements first)
- Backend operation identity is adapter-internal; public API uses Operation.id only
- No transitional power states (POWERING_ON/OFF); Operation.state tracks execution
- `POST /v1/virtualMachines` accepts a name and InstanceType reference and returns a RUNNING CREATE Operation targeting the preallocated future VirtualMachine UUIDv7.
- A newly created VM remains unavailable and STOPPED until its backend MOR identity binding and Operation SUCCEEDED transition are committed atomically.
- Backend VMs carrying the internal creation marker are never automatically adopted while their future public identity is pending finalization.
- A RUNNING Operation's backend state is polled on GET /operations/{id}, and terminal state is persisted.
- A SUCCEEDED VirtualMachine CREATE Operation requires an exact persisted future-ID to backend-ref mapping.

Result policy (current Python reference implementation only):

This policy describes the Python implementation technique. It is not a mandatory
Kotlin design; the Kotlin policy is defined separately above.

- Use a project-local Ok / Err / Result primitive; do not add external FP libraries.
- Expected failures are typed Result values, not exceptions, and are propagated as control flow.
- Expected failures remain Result values at Domain and Application boundaries. The only permitted exception-based control flow for expected Result propagation is the private `_ResultShortCircuit` implementation detail inside `iaas_sim.result`; it may only be raised by `ResultUnwrapper` and caught by `result_workflow`.
- `_ResultShortCircuit` carries no Domain or Application error semantics and must never cross the decorated workflow boundary. `result_workflow` must not convert unexpected exceptions into `Result` values.
- Application use cases are imperative orchestration over pure Domain functions and Ports. Keep the happy path visible from top to bottom.
- Result combinators are a local implementation technique, not an architectural requirement. Use `map`, `map_error`, and `and_then` only when they improve local clarity; combinator-heavy Railway syntax is not a goal.
- Explicit `Err` early returns are acceptable and preferred when they make sequential orchestration easier to read.
- For short or simple Result handling, use an explicit `Err` return or an ordinary Result combinator when locally clearer. For a sequential, multi-step fallible workflow with heterogeneous intermediate values, use `result_workflow` and `ResultUnwrapper` when they improve readability; do not require them for every Application function.
- Within a `result_workflow`, prefer `ResultUnwrapper.map_error` over nested `unwrap(map_error(...))` when semantic error translation before unwrapping is more readable.
- Do not introduce nested local stages, tuple plumbing, closure-heavy composition, or nested lambdas merely to eliminate explicit `Err` propagation.
- Once a value has been validated or transformed, downstream effects must consume that value rather than bypass it with an earlier input.
- Semantic branching is distinct from Result propagation. Meaningful domain-state branches, ADT matches, pure validation, explicit collection traversal, and boundary unwrapping remain appropriate. Do not optimize for zero if-statements.
- Adapter boundaries may catch external exceptions and convert them to typed Err values; domain and application code should not use try/except for expected failures.
- Use ADT / Enum / Union + match for meaningful states; keep simple booleans and if statements where they are clearer.
- State transitions should prefer table-driven or decision-table logic over nested if/else chains.
- Exceptions are for unexpected programming errors and bootstrap boundary handling, not for expected domain/application failures.
- The intended Result API is `Ok`, `Err`, `Result`, `map`, `map_error`, `and_then`, `ResultUnwrapper`, and `result_workflow`. Add another helper only after a repeated concrete need; do not build a speculative FP helper ecosystem.
- Keep Pyright strict and readable; avoid Any, cast, or type: ignore when narrowing Result values.

Testing policy:

- When behavior is determined by combinations of finite states, commands, roles, scopes, or inputs, prefer table-driven tests that expose the relevant state space explicitly.
- In Python, use `pytest.mark.parametrize` for such tables.
- The table should expose the relevant state space explicitly rather than duplicating one test function per case.
- Use descriptive pytest.param(..., id="...") identifiers.
- Do not force parametrization onto one-off integration/smoke tests where there is no meaningful case matrix.
