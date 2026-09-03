# ruff: noqa: PLR2004
from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4, uuid7

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iaas_sim.adapters.http.instance_type import create_instance_type_router
from iaas_sim.adapters.sqlite.connection import connect_database
from iaas_sim.adapters.sqlite.instance_type import SQLiteInstanceTypeStore, decode_instance_type_row
from iaas_sim.adapters.sqlite.migration import migrate_database
from iaas_sim.application.instance_type import (
    InstanceTypePersistenceFailure,
    InstanceTypeStoreError,
    InstanceTypeStorePort,
)
from iaas_sim.domain.entity.instance_type import InstanceType, InstanceTypeId
from iaas_sim.result import Err, Ok, Result

EXPECTED = {"small": (1, 1024), "medium": (2, 2048), "large": (4, 4096)}


def _path(tmp_path: Path) -> Path:
    return tmp_path / "instance-types.db"


def test_v3_migration_seeds_uuid7_resources_once_and_enforces_constraints(
    tmp_path: Path,
) -> None:
    path = _path(tmp_path)
    migrate_database(path)
    with connect_database(path) as connection:
        first = connection.execute(
            "SELECT id, name, vcpus, memory_mib FROM instance_type"
        ).fetchall()
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert {row[1]: (row[2], row[3]) for row in first} == EXPECTED
        assert all(UUID(row[0]).version == 7 for row in first)

        for values in ((str(uuid7()), "bad-cpu", 0, 1), (str(uuid7()), "bad-memory", 1, 0)):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO instance_type VALUES (?, ?, ?, ?)", values)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO instance_type VALUES (?, 'small', 8, 8192)", (str(uuid7()),)
            )

    migrate_database(path)
    with connect_database(path) as connection:
        second = connection.execute("SELECT id, name FROM instance_type").fetchall()
    assert {(row[0], row[1]) for row in second} == {(row[0], row[1]) for row in first}


def test_v2_upgrade_preserves_existing_resource_data(tmp_path: Path) -> None:
    path = _path(tmp_path)
    with connect_database(path) as connection:
        connection.executescript(
            """CREATE TABLE virtual_machine
            (id TEXT PRIMARY KEY, backend_ref TEXT NOT NULL UNIQUE) STRICT;
            CREATE TABLE snapshot
            (id TEXT PRIMARY KEY, backend_ref TEXT NOT NULL UNIQUE,
             virtual_machine_id TEXT NOT NULL REFERENCES virtual_machine(id)) STRICT;
            CREATE INDEX snapshot_virtual_machine_id_idx ON snapshot (virtual_machine_id);
            CREATE TABLE operation
            (id TEXT PRIMARY KEY, target_resource_type TEXT NOT NULL,
             target_resource_id TEXT NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL,
             failure_reason TEXT, backend_ref TEXT NOT NULL,
             CHECK (state IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
             CHECK ((state = 'FAILED' AND failure_reason IS NOT NULL)
                 OR (state <> 'FAILED' AND failure_reason IS NULL))) STRICT;
            INSERT INTO virtual_machine VALUES ('vm-id', 'vm-ref');
            INSERT INTO snapshot VALUES ('snapshot-id', 'snapshot-ref', 'vm-id');
            INSERT INTO operation VALUES
              ('operation-id', 'virtualMachines', 'vm-id', 'START', 'RUNNING', NULL, 'task-ref');
            PRAGMA user_version = 2;"""
        )
    migrate_database(path)
    with connect_database(path) as connection:
        assert (
            connection.execute("SELECT backend_ref FROM virtual_machine").fetchone()[0] == "vm-ref"
        )
        assert (
            connection.execute("SELECT backend_ref FROM snapshot").fetchone()[0] == "snapshot-ref"
        )
        assert connection.execute("SELECT backend_ref FROM operation").fetchone()[0] == "task-ref"
        assert connection.execute("SELECT COUNT(*) FROM instance_type").fetchone()[0] == 3


def test_store_lists_gets_and_keeps_control_plane_ids(tmp_path: Path) -> None:
    path = _path(tmp_path)
    migrate_database(path)
    result = SQLiteInstanceTypeStore(path).list_instance_types()
    assert isinstance(result, Ok)
    assert {item.name: (item.vcpus, item.memory_mib) for item in result.value} == EXPECTED
    assert all(item.id.version == 7 for item in result.value)
    assert all(str(item.id) != item.name for item in result.value)
    selected = result.value[1]
    assert SQLiteInstanceTypeStore(path).get_instance_type(selected.id) == Ok(selected)
    assert isinstance(SQLiteInstanceTypeStore(path).get_instance_type(InstanceTypeId(uuid7())), Err)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        pytest.param("id", "broken", id="malformed-id"),
        pytest.param("id", str(uuid4()), id="uuid4-id"),
        pytest.param("name", "", id="empty-name"),
    ],
)
def test_store_reports_corrupt_rows(column: str, value: str, tmp_path: Path) -> None:
    path = _path(tmp_path)
    migrate_database(path)
    with connect_database(path) as connection:
        connection.execute(f"UPDATE instance_type SET {column} = ? WHERE name = 'small'", (value,))
        connection.commit()
    assert isinstance(SQLiteInstanceTypeStore(path).list_instance_types(), Err)


@pytest.mark.parametrize(
    "row",
    [
        pytest.param((str(uuid7()), "small", 0, 1024), id="non-positive-vcpus"),
        pytest.param((str(uuid7()), "small", 1, 0), id="non-positive-memory"),
        pytest.param((str(uuid7()), "small", "bad", 1024), id="non-integer-vcpus"),
        pytest.param((str(uuid7()), "small", 1, "bad"), id="non-integer-memory"),
    ],
)
def test_store_decoder_reports_invalid_stored_values(row: tuple[object, ...]) -> None:
    assert isinstance(decode_instance_type_row(row), Err)


def test_store_reports_database_failure(tmp_path: Path) -> None:
    result = SQLiteInstanceTypeStore(_path(tmp_path)).list_instance_types()
    assert isinstance(result, Err)
    assert isinstance(result.error, InstanceTypePersistenceFailure)


class FailingStore:
    def list_instance_types(
        self,
    ) -> Result[Sequence[InstanceType], InstanceTypePersistenceFailure]:
        return Err(InstanceTypePersistenceFailure("list", "raw sqlite secret"))

    def get_instance_type(
        self, instance_type_id: InstanceTypeId
    ) -> Result[InstanceType, InstanceTypeStoreError]:
        return Err(InstanceTypePersistenceFailure("get", "raw sqlite secret"))


def _client(store: InstanceTypeStorePort) -> TestClient:
    app = FastAPI()
    app.include_router(create_instance_type_router(store))
    return TestClient(app)


def test_http_lists_and_gets_instance_types(tmp_path: Path) -> None:
    path = _path(tmp_path)
    migrate_database(path)
    client = _client(SQLiteInstanceTypeStore(path))
    response = client.get("/v1/instanceTypes")
    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["name"]: (item["vcpus"], item["memoryMiB"]) for item in items} == EXPECTED
    assert all(UUID(item["id"]).version == 7 for item in items)
    assert all(set(item) == {"id", "name", "vcpus", "memoryMiB"} for item in items)
    selected = items[0]
    assert client.get(f"/v1/instanceTypes/{selected['id']}").json() == selected
    assert client.get(f"/v1/instanceTypes/{uuid7()}").status_code == 404


@pytest.mark.parametrize("value", ["small", "malformed UUID", str(uuid4())])
def test_http_rejects_non_uuid7_ids(value: str, tmp_path: Path) -> None:
    path = _path(tmp_path)
    migrate_database(path)
    response = _client(SQLiteInstanceTypeStore(path)).get(f"/v1/instanceTypes/{value}")
    assert response.status_code == 422
    assert response.json() == {"detail": "InstanceType ID must be a UUIDv7"}


def test_http_sanitizes_persistence_failures() -> None:
    client = _client(FailingStore())
    for path in ("/v1/instanceTypes", f"/v1/instanceTypes/{uuid7()}"):
        response = client.get(path)
        assert response.status_code == 500
        assert response.json() == {"detail": "InstanceType persistence failed"}
        assert "raw sqlite secret" not in response.text
