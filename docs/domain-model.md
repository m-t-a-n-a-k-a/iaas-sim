# Domain Model

Phase 1 deliberately avoids a large business domain model.

The current repository focuses on a minimal operational shell:

- health endpoint
- OpenAPI generation
- placeholder console UI
- real pyVmomi connection verification to vcsim
- OTLP telemetry export

This is intentionally not a fake VM or account domain. The purpose is to verify the architecture skeleton and startup flow before adding business logic in later phases.
