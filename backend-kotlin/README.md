# Kotlin backend

`backend-kotlin/` is the incremental target backend. Phase K0 delivered its
executable Kotlin/JVM, Ktor, Maven, and JDK 21 skeleton. Phase K1 adds the
immutable VirtualMachine Domain model, pure power-command validation, and the
minimal typed `Outcome<T, E>` expected-failure primitive.

The next phase is K2, the VirtualMachine read vertical slice. This backend still
has no business HTTP API, persistence, Application layer, Ports, Adapters, or
VMware integration.

Use the repository-level commands for normal development:

```bash
make kotlin-run
make kotlin-test
make kotlin-verify
```

The committed Maven Wrapper uses the official `only-script` mode, so it pins and
downloads Maven without a wrapper JAR or a system Maven requirement.
