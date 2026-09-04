# iaas-sim

A small IaaS control-plane simulator for learning, design validation, and architecture experiments. It uses a vSphere simulator backend while keeping control-plane identities, persistence, and architectural boundaries explicit.

## Current capabilities

The complete, executable control plane remains the Python 3.14 implementation in `backend/`. It provides FastAPI/Uvicorn HTTP APIs, pyVmomi integration with `vcsim`, SQLite-backed durable state, and control-plane UUIDv7 identities. Its implemented Resources are `VirtualMachine`, `Snapshot`, `InstanceType`, and persistent `Operation`, including asynchronous VM power and Snapshot commands and blank VM creation.

`VirtualMachine.power_state` is observed backend state, not desired state. Command acceptance is not command completion: accepted asynchronous commands return `202 Accepted` and are tracked by durable `Operation` Resources through completion or failure.

The target backend is Kotlin/JVM with Ktor and Maven. Phase K0 established the executable skeleton and liveness endpoint in `backend-kotlin/`; Phase K1 now provides its immutable VirtualMachine Domain model, pure power-command validation, and typed expected-failure foundation. No business HTTP API has been migrated.

## Incremental Kotlin migration

Migration is incremental rather than a big-bang rewrite. The Python backend remains the executable behavior and architecture reference while vertical slices move to Kotlin in later phases:

- **K0 (complete):** executable Kotlin/Ktor/Maven skeleton
- **K1 (complete):** Kotlin-native Domain and expected-failure foundation
- **K2 (next):** VirtualMachine read vertical slice
- **K3:** VirtualMachine command / Operation vertical slice

## Architecture and expected failures

The language-independent architecture combines Functional Core + Imperative Shell with Hexagonal Architecture. Immutable, pure Domain rules are orchestrated by the Application layer through Ports, infrastructure remains in Adapters, and expected failures are typed.

In the current Python reference, the project-local `Result`, `result_workflow`, and `ResultUnwrapper` are focused implementation techniques for expected-failure propagation, not a general FP framework or a Kotlin migration requirement. Kotlin uses its own minimal, project-local `Outcome<T, E>` sealed type to represent success and typed expected failure without exceptions or speculative combinators.

## Stack

- Current control plane: Python 3.14, FastAPI, Uvicorn, pyVmomi, and SQLite
- Target backend foundation: Kotlin 2.4.10/JVM, Ktor 3.5.2, Maven 3.9.16, and JDK 21
- Svelte, TypeScript, and Vite
- Docker Compose with `vcsim`, OpenTelemetry, and Grafana/otel-lgtm

## Running the two backends

Normal Kotlin backend operations use Make:

```bash
make kotlin-run
make kotlin-test
make kotlin-verify
```

`make kotlin-run` starts the executable skeleton from Phase K0 at http://localhost:8080/health. This endpoint only proves that the Kotlin process can serve HTTP; it does not reproduce the Python endpoint's operational probes. Phase K1 adds Domain code but no business endpoint. The lower-level equivalent is `cd backend-kotlin && ./mvnw ...`; a system Maven installation is not required.

`make up` continues to start the current Python application through Docker Compose. Its health endpoint is http://localhost:8000/health, with API documentation at http://localhost:8000/docs and the UI at http://localhost:8000/ui. Stop it with `make down`.

## Local commands

```bash
make kotlin-run
make kotlin-test
make kotlin-verify
make up
make down
make reset
make logs
make verify
```

## Codespaces

The dev container includes Python 3.14, uv, Node.js 24, Docker-in-Docker, and JDK 21. Use the commands above; ports 8000 and 8080 are forwarded for the Python application and Kotlin skeleton respectively.

## Current limitations

The intended Python application path connects to `vcsim` over HTTPS inside the Docker Compose network; host-side `127.0.0.1` access is only an incidental port-publishing path. The Kotlin backend has a K1 Domain foundation but no business HTTP APIs, Application use cases, Ports, Adapters, persistence, authentication, authorization, VMware integration, or observability. IAM, metering, queues, retry policy, and broader cloud-domain behavior are not yet implemented. `make verify` enforces the Python, Kotlin, frontend, architecture, smoke, and Compose checks.
