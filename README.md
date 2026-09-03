# iaas-sim

A minimal IaaS cloud simulator for learning, design validation, and architecture experiments. The current Phase 2A scope adds asynchronous VirtualMachine power operations to a deliberately small control-plane architecture.

## Goals

- Validate a small cloud control plane skeleton built around a vSphere-like backend
- Keep the design static, explicit, and deterministic
- Run a local Docker Compose environment that shows the intended architecture
- Provide Operational Health, Swagger UI, OpenAPI, and a placeholder console

## Stack

- Python 3.14
- FastAPI
- Uvicorn
- pyVmomi
- SQLite (selected for future persistence but not yet used for business logic)
- Svelte + TypeScript + Vite
- Dex for future OIDC integration
- OpenTelemetry + Grafana/otel-lgtm
- Docker Compose

## Phase 2A: Asynchronous Power Operations

VirtualMachine power commands (start, stop) are modeled as asynchronous operations:

- **Observed state**: `VirtualMachine.power_state` reflects the last-known backend state, not desired state
- **Async execution**: `POST /v1/virtualMachines/{id}:start` returns `202 Accepted` with `Location` header
- **Operation tracking**: Each power command is tracked via an `Operation` resource with UUIDv7 identifier
  - A process-local registry correlates the public ID with an opaque backend reference; GET polls
    the backend and projects its current state. The registry is intentionally non-durable in Phase 2A.
- **Separation of concerns**:
  - Domain validation is pure: command validation against observed state, no side effects
  - Application layer composes domain validation + backend submission
  - The opaque backend operation reference is adapter-internal and is not exposed as the public Operation ID
  - Operation status is an immutable `Running | Succeeded | Failed(failure)` ADT, and targets use
    a backend-independent resource reference
- **Failure semantics**:
  - Synchronous failure (validation/submission): HTTP 4xx/5xx response
  - Asynchronous failure (backend operation execution): `Operation.state = FAILED`

## Codespaces

1. Open the repository in GitHub Codespaces.
2. Run:
   ```bash
   make up
   ```
3. Open the following:
   - http://localhost:8000/health
   - http://localhost:8000/docs
   - http://localhost:8000/ui
   - http://localhost:3000 (Grafana/otel-lgtm)
4. To stop the environment:
   ```bash
   make down
   ```

## Local commands

```bash
make up
make down
make reset
make logs
make verify
```

## Notes

- The intended execution path is inside the Docker Compose network: the application connects to the vSphere simulator using the service hostname `vcsim` over HTTPS.
- Host-side `127.0.0.1` access is not treated as the completion criterion because it is an incidental local port-publishing path rather than the real application path.
- Phase 2A implements only asynchronous VM start/stop and non-durable Operation polling; IAM, metering, persistence, queues, retry, and broader cloud domain behavior remain out of scope.
- The project uses a strict Python typing setup and architecture import rules that are enforced in CI.
- The project uses a small project-local Result workflow helper to keep multi-step fallible Application orchestration linear while preserving typed Result boundaries.
