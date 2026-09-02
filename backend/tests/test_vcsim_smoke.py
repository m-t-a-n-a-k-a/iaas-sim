# ruff: noqa: PLR2004
from __future__ import annotations

import os
import ssl
import time
from tempfile import NamedTemporaryFile
from urllib import error, request
from uuid import uuid4, uuid7

import pytest
from pyVim import connect
from pyVmomi import vim

from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.adapters.sqlite.adapter import SQLiteAdapter
from iaas_sim.adapters.sqlite.migration import migrate_database
from iaas_sim.adapters.vsphere.adapter import VSphereAdapter
from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationRef,
    BackendOperationRunning,
    BackendOperationSucceeded,
)
from iaas_sim.application.snapshot import (
    SnapshotNotFound,
    create_snapshot,
    delete_snapshot,
    get_snapshot,
    list_snapshots,
)
from iaas_sim.application.virtual_machine import (
    get_virtual_machine,
    list_virtual_machines,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.operation import OperationId
from iaas_sim.domain.entity.virtual_machine import PowerCommand, PowerState
from iaas_sim.result import Err, Ok


def wait_for_success(adapter: VSphereAdapter, backend_ref: BackendOperationRef) -> None:
    for _ in range(50):
        polled = adapter.get_operation_status(backend_ref)
        assert isinstance(polled, Ok)
        if isinstance(polled.value, BackendOperationSucceeded):
            return
        assert isinstance(polled.value, BackendOperationRunning), polled.value
        time.sleep(0.1)
    pytest.fail("vcsim task did not complete within five seconds")


@pytest.mark.skipif(
    os.getenv("PYVMOMI_SMOKE") != "1",
    reason=(
        "Run through make smoke-test or set PYVMOMI_SMOKE=1 to execute "
        "the real vcsim connectivity check."
    ),
)
def test_vcsim_retrieve_content_success() -> None:  # noqa: PLR0915
    host = os.getenv("VSPHERE_HOST", "vcsim")
    port = int(os.getenv("VSPHERE_PORT", "8989"))
    scheme = os.getenv("VSPHERE_SCHEME", "https")
    username = os.getenv("VSPHERE_USERNAME", "user")
    password = os.getenv("VSPHERE_PASSWORD", "pass")

    readiness_url = f"{scheme}://{host}:{port}/about"
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    ready = False
    last_error: Exception | None = None
    for _ in range(30):
        try:
            with request.urlopen(
                readiness_url,
                timeout=3,
                context=ssl_context,
            ):
                pass
            ready = True
            break
        except (error.URLError, OSError, ValueError) as exc:
            last_error = exc
            time.sleep(1)
    assert ready, f"vcsim did not become ready at {readiness_url}: {last_error}"

    service_instance = None
    try:
        service_instance = connect.SmartConnect(
            protocol=scheme,
            host=host,
            port=port,
            user=username,
            pwd=password,
            disableSslCertValidation=True,
        )
        content = service_instance.RetrieveContent()
        view_manager = content.viewManager
        assert view_manager is not None
        inventory = view_manager.CreateContainerView(
            content.rootFolder,
            [vim.VirtualMachine],
            True,
        )
        vms = list(inventory.view)
        assert len(vms) >= 1
        assert content.rootFolder is not None

        adapter = VSphereAdapter()
        database = NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        database.close()
        migrate_database(database.name)
        identity = SQLiteAdapter(database.name)
        registry = InMemoryOperationRegistry()
        listed = list_virtual_machines(adapter, identity)
        assert isinstance(listed, Ok)
        assert len(listed.value) >= 1
        public_id = listed.value[0].id
        repeated = list_virtual_machines(adapter, identity)
        assert isinstance(repeated, Ok) and repeated.value[0].id == public_id
        fetched = get_virtual_machine(adapter, identity, public_id)
        assert isinstance(fetched, Ok)
        assert fetched.value.id == public_id and public_id.version == 7
        command = (
            PowerCommand.STOP
            if fetched.value.power_state is PowerState.RUNNING
            else PowerCommand.START
        )
        submitted = (
            stop_virtual_machine if command is PowerCommand.STOP else start_virtual_machine
        )(adapter, identity, registry, OperationId(uuid7()), public_id)
        assert isinstance(submitted, Ok)
        tracked = registry.get(submitted.value.id)
        assert tracked is not None
        polled = adapter.get_operation_status(tracked.backend_ref)
        assert isinstance(polled, Ok)
        assert isinstance(
            polled.value,
            (BackendOperationRunning, BackendOperationSucceeded, BackendOperationFailed),
        )
        wait_for_success(adapter, tracked.backend_ref)

        snapshot_name = f"iaas-sim-{uuid4()}"
        created = create_snapshot(
            adapter, identity, registry, OperationId(uuid7()), public_id, snapshot_name
        )
        assert isinstance(created, Ok)
        created_tracked = registry.get(created.value.id)
        assert created_tracked is not None
        wait_for_success(adapter, created_tracked.backend_ref)
        snapshots = list_snapshots(adapter, identity, identity)
        assert isinstance(snapshots, Ok)
        snapshot = next(item for item in snapshots.value if item.name == snapshot_name)
        assert snapshot.virtual_machine.resource_id == str(public_id)
        repeated_snapshots = list_snapshots(adapter, identity, identity)
        assert isinstance(repeated_snapshots, Ok)
        assert (
            next(item for item in repeated_snapshots.value if item.name == snapshot_name).id
            == snapshot.id
        )
        loaded_snapshot = get_snapshot(adapter, identity, identity, snapshot.id)
        assert isinstance(loaded_snapshot, Ok)
        assert loaded_snapshot.value == snapshot
        deleted = delete_snapshot(adapter, identity, registry, OperationId(uuid7()), snapshot.id)
        assert isinstance(deleted, Ok)
        deleted_tracked = registry.get(deleted.value.id)
        assert deleted_tracked is not None
        wait_for_success(adapter, deleted_tracked.backend_ref)
        assert get_snapshot(adapter, identity, identity, snapshot.id) == Err(
            SnapshotNotFound(snapshot.id)
        )
    finally:
        if service_instance is not None:
            connect.Disconnect(service_instance)
