# API Style

The API follows a small, explicit set of rules.

- Top-level resources only.
- Flat resource names under `/v1`.
- Commands use `POST /v1/{resourceType}/{id}:verb`.
- `PUT` is forbidden.
- Nested resources are forbidden.
- Snapshot resources use flat `/v1/snapshots` collection/item routes and embed a Resource Reference to their VirtualMachine.
- VirtualMachine and Snapshot item paths accept UUIDv7 identifiers only; backend MORs are never resource IDs.
- InstanceTypes use flat, read-only `/v1/instanceTypes` collection/item routes and UUIDv7 resource IDs; their names are not IDs.
- Health is `/health` and is operational, not part of the domain model.
- OpenAPI is treated as the contract source for future client generation.
