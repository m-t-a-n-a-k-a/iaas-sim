# iaas-sim

A small IaaS control-plane simulator for learning, design validation, and architecture experiments. It exposes VirtualMachine, Snapshot, InstanceType, and persistent Operation resources over a deliberately small vSphere-backed architecture.

## Goals

- Validate a small cloud control plane skeleton built around a vSphere-like backend
- Keep the design explicit, deterministic, and low in cognitive overhead
- Run a local Docker Compose environment that shows the intended architecture
- Provide Operational Health, Swagger UI, OpenAPI, and a placeholder console

## Stack

- Python 3.14
- FastAPI and Uvicorn
- pyVmomi with a vcsim backend
- SQLite-backed durable control-plane state
- Svelte + TypeScript + Vite
- Dex for future OIDC integration
- OpenTelemetry + Grafana/otel-lgtm
- Docker Compose

## Current capabilities

- Control-plane UUIDv7 identities for VirtualMachine and Snapshot resources, mapped to opaque backend identities
- Control-plane-owned InstanceType resources
- Durable SQLite state for resource identity mappings and persistent Operation resources
- Asynchronous VirtualMachine `START`/`STOP` and Snapshot create/delete, tracked through Operations
- Blank VM creation with `POST /v1/virtualMachines`; the VM becomes available after its asynchronous CREATE Operation succeeds

`VirtualMachine.power_state` is observed backend state, not desired state. Command acceptance is distinct from completion: synchronous validation or submission failures produce HTTP errors, while accepted commands return `202 Accepted` and a persistent Operation records eventual success or asynchronous failure.

## Architecture and Result workflows

The primary design is Functional Core + Imperative Shell within a Hexagonal Architecture, with strict Python typing. Domain rules and data remain pure and immutable, while Application code orchestrates Ports and keeps infrastructure in Adapters. Expected failures are represented by typed Results.

The project has selected Expression as a practical typed functional-programming library, not as a way to make the entire codebase purely functional. Result handling will migrate to Expression in a follow-up change; its effect builders are intended to keep multi-step fallible workflows direct, linear, and readable while retaining Result short-circuit semantics and avoiding repetitive manual unwrapping.

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

## Current limitations

- The intended execution path is inside the Docker Compose network: the application connects to vcsim using the service hostname `vcsim` over HTTPS.
- Host-side `127.0.0.1` access is incidental local port publishing and is not the completion criterion for the application path.
- IAM, metering, queues, retry policy, and broader cloud domain behavior remain out of scope.
- Strict Python typing and architecture import rules are enforced in CI.
