# Kotlin backend

`backend-kotlin/` is the incremental target backend. K0 delivered the executable
Ktor/Maven/JDK 21 skeleton, K1 the Domain and minimal `Outcome<T, E>`, and K2 the
VirtualMachine read vertical slice. It provides health, VirtualMachine list and
get, and official VMware SDK integration with live `vcsim`.

Run from the repository root:

```bash
make kotlin-run
```

Then check:

- `GET http://localhost:8080/health`
- `GET http://localhost:8080/v1/virtualMachines`

Use `make kotlin-test` and `make kotlin-verify` for checks. The Maven Wrapper uses
official `only-script` mode. K4 is complete and K5 is next. VirtualMachine identity
mappings and InstanceType Resources are durable SQLite state. Blank VM CREATE uses a
preallocated UUIDv7 creation marker and atomically finalizes identity plus Operation success.
