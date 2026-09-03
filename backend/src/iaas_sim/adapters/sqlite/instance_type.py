from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from os import PathLike
from uuid import UUID

from iaas_sim.adapters.sqlite.connection import connect_database
from iaas_sim.application.instance_type import (
    InstanceTypeNotFound,
    InstanceTypePersistenceFailure,
    InstanceTypeStoreError,
)
from iaas_sim.domain.entity.instance_type import InstanceType, InstanceTypeId
from iaas_sim.result import Err, Ok, Result

UUID_VERSION_7 = 7
INSTANCE_TYPE_COLUMN_COUNT = 4


def decode_instance_type_row(
    row: tuple[object, ...],
) -> Result[InstanceType, InstanceTypePersistenceFailure]:
    if len(row) != INSTANCE_TYPE_COLUMN_COUNT:
        return Err(InstanceTypePersistenceFailure("decode", "invalid stored instance type"))
    raw_id, name, vcpus, memory_mib = row
    if not (
        isinstance(raw_id, str)
        and isinstance(name, str)
        and bool(name)
        and isinstance(vcpus, int)
        and not isinstance(vcpus, bool)
        and vcpus > 0
        and isinstance(memory_mib, int)
        and not isinstance(memory_mib, bool)
        and memory_mib > 0
    ):
        return Err(InstanceTypePersistenceFailure("decode", "invalid stored instance type"))
    try:
        parsed = UUID(raw_id)
    except ValueError:
        return Err(InstanceTypePersistenceFailure("decode", "invalid stored instance type ID"))
    if parsed.version != UUID_VERSION_7:
        return Err(InstanceTypePersistenceFailure("decode", "stored ID is not UUIDv7"))
    return Ok(InstanceType(InstanceTypeId(parsed), name, vcpus, memory_mib))


class SQLiteInstanceTypeStore:
    def __init__(self, database_path: str | PathLike[str]) -> None:
        self._database_path = database_path

    def list_instance_types(
        self,
    ) -> Result[Sequence[InstanceType], InstanceTypePersistenceFailure]:
        try:
            with connect_database(self._database_path) as connection:
                rows = connection.execute(
                    """SELECT id, name, vcpus, memory_mib FROM instance_type
                    ORDER BY vcpus, memory_mib, name, id"""
                ).fetchall()
            resources: list[InstanceType] = []
            for row in rows:
                decoded = decode_instance_type_row(row)
                if isinstance(decoded, Err):
                    return decoded
                resources.append(decoded.value)
            return Ok(resources)
        except sqlite3.Error as exc:
            return Err(InstanceTypePersistenceFailure("list", str(exc)))

    def get_instance_type(
        self, instance_type_id: InstanceTypeId
    ) -> Result[InstanceType, InstanceTypeStoreError]:
        try:
            with connect_database(self._database_path) as connection:
                row = connection.execute(
                    "SELECT id, name, vcpus, memory_mib FROM instance_type WHERE id = ?",
                    (str(instance_type_id),),
                ).fetchone()
            if row is None:
                return Err(InstanceTypeNotFound(instance_type_id))
            decoded = decode_instance_type_row(row)
            match decoded:
                case Err(error):
                    return Err(error)
                case Ok(instance_type):
                    return Ok(instance_type)
        except sqlite3.Error as exc:
            return Err(InstanceTypePersistenceFailure("get", str(exc)))
