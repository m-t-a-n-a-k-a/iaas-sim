# iaas-sim

A minimal IaaS cloud simulator for learning, design validation, and architecture experiments. This repository intentionally keeps the Phase 1 model small and static-focused rather than building production-grade cloud features.

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
- **Separation of concerns**:
  - Domain validation is pure: command validation against observed state, no side effects
  - Application layer composes domain validation + backend submission
  - Backend Task MOR (vSphere) is internal to Adapter; not exposed as public Operation ID
- **Failure semantics**:
  - Synchronous failure (validation/submission): HTTP 4xx/5xx response
  - Asynchronous failure (task execution): `Operation.state = FAILED`

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

- Phase 1 validates the intended execution path inside the Docker Compose network: the application connects to the vSphere simulator using the service hostname `vcsim` over HTTPS.
- Host-side `127.0.0.1` access is not treated as the completion criterion because it is an incidental local port-publishing path rather than the real application path.
- This repository intentionally does not implement IAM, VM lifecycle, metering, or full cloud domain logic in Phase 1.
- Phase 1 emphasizes architecture skeleton, infrastructure start-up, and static verification.
- The project uses a strict Python typing setup and architecture import rules that are enforced in CI.
