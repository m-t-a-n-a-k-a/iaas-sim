# Kotlin backend

`backend-kotlin/` is the Phase K0 executable skeleton for the incremental target
backend. It uses Kotlin/JVM, Ktor, Maven, and JDK 21. No business functionality
has been migrated yet.

Use the repository-level commands for normal development:

```bash
make kotlin-run
make kotlin-test
make kotlin-verify
```

The committed Maven Wrapper uses the official `only-script` mode, so it pins and
downloads Maven without a wrapper JAR or a system Maven requirement.
