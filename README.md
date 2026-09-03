# iaas-sim

A small IaaS control-plane simulator for learning, design validation, and architecture experiments. It uses a vSphere simulator backend while keeping control-plane identities, persistence, and architectural boundaries explicit.

## Current capabilities

- Python 3.14 control plane served by FastAPI and Uvicorn
- pyVmomi integration with a `vcsim` backend
- SQLite-backed durable control-plane state and control-plane UUIDv7 identities
- `VirtualMachine`, `Snapshot`, `InstanceType`, and persistent `Operation` Resources
- Asynchronous VirtualMachine START / STOP and Snapshot create / delete operations
- Blank VM creation through `POST /v1/virtualMachines`; its CREATE Operation targets a preallocated future VirtualMachine UUIDv7, and the VM becomes publicly available only after its backend identity mapping is finalized
- Docker Compose development environment with OpenTelemetry and Grafana/otel-lgtm

`VirtualMachine.power_state` is observed backend state, not desired state. Command acceptance is not command completion: accepted asynchronous commands return `202 Accepted` and are tracked by durable `Operation` Resources through completion or failure.

## Architecture and Result workflows

The project combines Functional Core + Imperative Shell with Hexagonal Architecture. Immutable, pure Domain rules are orchestrated by the Application layer through Ports, while infrastructure remains in Adapters; expected failures use typed `Result` values under strict Python typing.

Multi-step fallible Application orchestration can use the small project-local Result workflow helper. `result_workflow` keeps the public boundary typed as `Result`, while `ResultUnwrapper` consumes heterogeneous intermediate values in a direct, top-to-bottom style. This is a focused control-flow utility, not a general FP framework.

## Stack

- Python 3.14, FastAPI, Uvicorn, pyVmomi, and SQLite
- Svelte, TypeScript, and Vite
- Docker Compose with `vcsim`
- OpenTelemetry and Grafana/otel-lgtm

## Codespaces

1. Open the repository in GitHub Codespaces.
2. Run:
   ```bash
   make up
   ```
3. Open:
   - http://localhost:8000/health
   - http://localhost:8000/docs
   - http://localhost:8000/ui
   - http://localhost:3000 (Grafana/otel-lgtm)
4. Stop the environment with:
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

## Current limitations

The intended application path connects to `vcsim` over HTTPS inside the Docker Compose network; host-side `127.0.0.1` access is only an incidental port-publishing path. IAM, metering, queues, retry policy, and broader cloud-domain behavior are not yet implemented. Strict typing, tests, linting, and architecture import rules are enforced by `make verify`.
