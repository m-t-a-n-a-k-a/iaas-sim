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

## Phase 2E target: VirtualMachine creation

Phase 2E will expose `POST /v1/virtualMachines` with exactly `name` and an embedded
`instanceType` Resource Reference (`resourceType: "instanceTypes"`, UUIDv7 `id`). The control
plane will resolve that reference, allocate the future VirtualMachine UUIDv7 and an Operation
UUIDv7 before asynchronously submitting the blank VM creation. The accepted Operation has action
`CREATE` and targets `{ "resourceType": "virtualMachines", "id": "<future VM UUIDv7>" }`.

While creation is in progress, `GET /v1/virtualMachines/{future-id}` returns 404. It returns 200
only after the backend task succeeds and its VM identity is finalized. Phase 2E-1 implements only
the backend submission primitive: `POST /v1/virtualMachines` is intentionally **not exposed** until
identity finalization is implemented in Phase 2E-2.
