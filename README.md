# iaas-sim

A small IaaS control-plane simulator for learning, design validation, and architecture experiments. It uses a vSphere simulator backend while keeping control-plane identities, persistence, and architectural boundaries explicit.

## Current capabilities

The complete, executable control plane remains the Python 3.14 implementation in `backend/`. It provides FastAPI/Uvicorn HTTP APIs, pyVmomi integration with `vcsim`, SQLite-backed durable state, and control-plane UUIDv7 identities. Its implemented Resources are `VirtualMachine`, `Snapshot`, `InstanceType`, and persistent `Operation`, including asynchronous VM power and Snapshot commands and blank VM creation.

`VirtualMachine.power_state` is observed backend state, not desired state. Command acceptance is not command completion: accepted asynchronous commands return `202 Accepted` and are tracked by durable `Operation` Resources through completion or failure.

The target backend is Kotlin/JVM with Ktor and Maven. Phases K0 and K1 established the executable skeleton, immutable VirtualMachine Domain model, pure power-command validation, and typed expected-failure foundation. Phase K2 added VirtualMachine reads. Phase K3 adds asynchronous START/STOP commands, persistent SQLite Operations, GET polling with terminal-state persistence, and live `vcsim` Task integration. VirtualMachine identity mapping remains temporary process-local memory.

## Incremental Kotlin migration

Migration is incremental rather than a big-bang rewrite. The Python backend remains the executable behavior and architecture reference while vertical slices move to Kotlin in later phases:

- **K0 (complete):** executable Kotlin/Ktor/Maven skeleton
- **K1 (complete):** Kotlin-native Domain and expected-failure foundation
- **K2 (complete):** VirtualMachine read vertical slice
- **K3 (complete):** VirtualMachine command / Operation vertical slice
- **K4 (next):** next incremental vertical slice

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

`make kotlin-run` starts `vcsim` and the Kotlin server. Check http://localhost:8080/health and http://localhost:8080/v1/virtualMachines. The health endpoint remains liveness-only; list/get responses read observed live simulator state, command endpoints return 202 Accepted with a persistent Operation, and GET Operation polls a running backend Task once per request. The lower-level equivalent is `cd backend-kotlin && ./mvnw ...`; a system Maven installation is not required.

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

The Python application connects to `vcsim` inside Docker Compose, while K2 publishes `vcsim` only on host loopback for the host-run Kotlin backend. Kotlin implements health, VirtualMachine list/get reads, asynchronous START/STOP submission, and persistent SQLite Operation lookup with live VMware Task polling. Terminal Operation states are persisted; VirtualMachine public identity mapping remains temporary process-local memory and is lost on restart. Authentication, authorization, and observability have not been migrated. IAM, metering, queues, retry policy, and broader cloud-domain behavior are not yet implemented. `make verify` enforces the Python, Kotlin, frontend, architecture, smoke, and Compose checks.
