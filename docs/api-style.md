# API Style

The API follows a small, explicit set of rules.

- Top-level resources only.
- Flat resource names under `/v1`.
- Commands use `POST /v1/{resourceType}/{id}:verb`.
- `PUT` is forbidden.
- Nested resources are forbidden.
- Snapshot resources use flat `/v1/snapshots` collection/item routes and embed a Resource Reference to their VirtualMachine.
- VirtualMachine item and power-command paths accept UUIDv7 identifiers only; backend MORs are never resource IDs.
- Health is `/health` and is operational, not part of the domain model.
- OpenAPI is treated as the contract source for future client generation.
