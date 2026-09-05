# Kotlin backend

`backend-kotlin/` is the incremental target backend. K0 delivered the executable
Ktor/Maven/JDK 21 skeleton, K1 the Domain and minimal `Outcome<T, E>`, and K2 the
VirtualMachine read vertical slice. K2 provides health, VirtualMachine list and
get, official VMware SDK integration with live `vcsim`, and process-local UUIDv7
public identity mapping.

Run from the repository root:

```bash
make kotlin-run
```

Then check:

- `GET http://localhost:8080/health`
- `GET http://localhost:8080/v1/virtualMachines`

Use `make kotlin-test` and `make kotlin-verify` for checks. The Maven Wrapper uses
official `only-script` mode. K3 is complete and K4 is next. VirtualMachine identity
mappings remain temporary in-memory state and are lost when the Kotlin process
restarts; only Operations are persisted in SQLite.
