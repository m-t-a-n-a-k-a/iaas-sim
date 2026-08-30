# API Style

The API follows a small, explicit set of rules.

- Top-level resources only.
- Flat resource names under `/v1`.
- Commands use `POST /v1/{resourceType}/{id}:verb`.
- `PUT` is forbidden.
- Nested resources are forbidden.
- Health is `/health` and is operational, not part of the domain model.
- OpenAPI is treated as the contract source for future client generation.
