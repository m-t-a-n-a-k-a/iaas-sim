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

from iaas_sim.adapters.sqlite.adapter import SQLiteAdapter
from iaas_sim.adapters.sqlite.instance_type import SQLiteInstanceTypeStore
from iaas_sim.adapters.sqlite.migration import migrate_database
from iaas_sim.adapters.sqlite.operation import SQLiteOperationStore
from iaas_sim.adapters.sqlite.virtual_machine_create import SQLiteVirtualMachineCreateFinalizer
from iaas_sim.adapters.vsphere.adapter import (
    VSphereAdapter,
    VspherePropertyCollector,
    new_vmodl_data_object,
)
from iaas_sim.application.get_operation import get_operation as reconcile_operation
from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationRunning,
    BackendOperationSucceeded,
    BackendVirtualMachineCreated,
)
from iaas_sim.application.snapshot import (
    SnapshotNotFound,
    create_snapshot,
    delete_snapshot,
    get_snapshot,
    list_snapshots,
)
from iaas_sim.application.virtual_machine import (
    create_virtual_machine,
    get_virtual_machine,
    list_virtual_machines,
    start_virtual_machine,
)
from iaas_sim.domain.entity.operation import OperationId, Running, Succeeded
from iaas_sim.domain.entity.virtual_machine import PowerState, VirtualMachineId
from iaas_sim.result import Err, Ok

VM_CREATE_SMOKE_PROPERTIES = (
    "name",
    "summary.runtime.powerState",
    "config.hardware.numCPU",
    "config.hardware.memoryMB",
)


def collect_created_vm_properties(
    property_collector: object, virtual_machine: object
) -> dict[str, object]:
    """Collect only properties needed to verify blank creation against vcsim."""
    assert isinstance(property_collector, VspherePropertyCollector)
    object_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.ObjectSpec")
    object.__setattr__(object_spec, "obj", virtual_machine)
    property_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.PropertySpec")
    object.__setattr__(property_spec, "type", vim.VirtualMachine)
    object.__setattr__(property_spec, "pathSet", list(VM_CREATE_SMOKE_PROPERTIES))
    filter_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.FilterSpec")
    object.__setattr__(filter_spec, "objectSet", [object_spec])
    object.__setattr__(filter_spec, "propSet", [property_spec])

    contents = property_collector.RetrieveContents([filter_spec])
    assert len(contents) == 1
    properties = {item.name: item.val for item in contents[0].propSet}
    assert set(properties) == set(VM_CREATE_SMOKE_PROPERTIES)
    return properties


def reconcile_until_success(
    database_path: str, adapter: VSphereAdapter, operation_id: OperationId
) -> None:
    """Recreate the store while polling to exercise durable read-through behavior."""
    for _ in range(50):
        result = reconcile_operation(SQLiteOperationStore(database_path), adapter, operation_id)
        assert isinstance(result, Ok)
        if isinstance(result.value.status, Succeeded):
            return
        time.sleep(0.1)
    pytest.fail("vcsim Operation did not reconcile within five seconds")


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

        database = NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        database.close()
        migrate_database(database.name)
        adapter = VSphereAdapter()
        identity = SQLiteAdapter(database.name)
        store = SQLiteOperationStore(database.name)
        instance_types = SQLiteInstanceTypeStore(database.name).list_instance_types()
        assert isinstance(instance_types, Ok)
        small = next(item for item in instance_types.value if item.name == "small")
        create_name = f"blank-{uuid4()}"
        future_id = VirtualMachineId(uuid7())
        create_operation_id = OperationId(uuid7())
        accepted = create_virtual_machine(
            adapter,
            SQLiteInstanceTypeStore(database.name),
            store,
            create_operation_id,
            future_id,
            small.id,
            create_name,
        )
        assert isinstance(accepted, Ok)
        tracked_create = store.get(create_operation_id)
        assert isinstance(tracked_create, Ok)
        assert isinstance(tracked_create.value.operation.status, Running)

        for _ in range(50):
            create_status = adapter.get_operation_status(tracked_create.value.backend_ref)
            assert isinstance(create_status, Ok)
            if isinstance(create_status.value, BackendOperationSucceeded):
                break
            assert isinstance(create_status.value, BackendOperationRunning)
            time.sleep(0.1)
        else:
            pytest.fail("vcsim blank VM creation did not complete within five seconds")
        assert isinstance(create_status.value.result, BackendVirtualMachineCreated)
        created_backend_ref = create_status.value.result.backend_ref

        # The completed, marked VM must remain invisible until reconciliation; in
        # particular list must not adopt it under a fresh public UUID.
        pending_list = list_virtual_machines(adapter, identity)
        assert isinstance(pending_list, Ok)
        assert all(item.id != future_id for item in pending_list.value)
        assert identity.find_by_backend_ref(created_backend_ref) == Ok(None)

        reconciled = reconcile_operation(
            store,
            adapter,
            create_operation_id,
            SQLiteVirtualMachineCreateFinalizer(database.name),
        )
        assert isinstance(reconciled, Ok)
        assert isinstance(reconciled.value.status, Succeeded)
        assert identity.get_backend_ref(future_id) == Ok(created_backend_ref)

        fetched = get_virtual_machine(adapter, identity, future_id)
        assert isinstance(fetched, Ok)
        finalized_list = list_virtual_machines(adapter, identity)
        assert isinstance(finalized_list, Ok)
        assert sum(item.id == future_id for item in finalized_list.value) == 1

        created_vm = vim.VirtualMachine(str(created_backend_ref), service_instance._stub)
        created_properties = collect_created_vm_properties(content.propertyCollector, created_vm)
        assert created_properties["name"] == create_name
        assert str(created_properties["summary.runtime.powerState"]) == "poweredOff"
        assert created_properties["config.hardware.numCPU"] == 1
        assert created_properties["config.hardware.memoryMB"] == 1024

        assert fetched.value.id == future_id and fetched.value.power_state is PowerState.STOPPED
        submitted = start_virtual_machine(adapter, identity, store, OperationId(uuid7()), future_id)
        assert isinstance(submitted, Ok)
        tracked = store.get(submitted.value.id)
        assert isinstance(tracked, Ok)
        polled = adapter.get_operation_status(tracked.value.backend_ref)
        assert isinstance(polled, Ok)
        assert isinstance(
            polled.value,
            (BackendOperationRunning, BackendOperationSucceeded, BackendOperationFailed),
        )
        reconcile_until_success(database.name, adapter, submitted.value.id)

        snapshot_name = f"iaas-sim-{uuid4()}"
        created = create_snapshot(
            adapter, identity, store, OperationId(uuid7()), future_id, snapshot_name
        )
        assert isinstance(created, Ok)
        created_tracked = store.get(created.value.id)
        assert isinstance(created_tracked, Ok)
        reconcile_until_success(database.name, adapter, created.value.id)
        snapshots = list_snapshots(adapter, identity, identity)
        assert isinstance(snapshots, Ok)
        snapshot = next(item for item in snapshots.value if item.name == snapshot_name)
        assert snapshot.virtual_machine.resource_id == str(future_id)
        repeated_snapshots = list_snapshots(adapter, identity, identity)
        assert isinstance(repeated_snapshots, Ok)
        assert (
            next(item for item in repeated_snapshots.value if item.name == snapshot_name).id
            == snapshot.id
        )
        loaded_snapshot = get_snapshot(adapter, identity, identity, snapshot.id)
        assert isinstance(loaded_snapshot, Ok)
        assert loaded_snapshot.value == snapshot
        deleted = delete_snapshot(adapter, identity, store, OperationId(uuid7()), snapshot.id)
        assert isinstance(deleted, Ok)
        deleted_tracked = store.get(deleted.value.id)
        assert isinstance(deleted_tracked, Ok)
        reconcile_until_success(database.name, adapter, deleted.value.id)
        assert get_snapshot(adapter, identity, identity, snapshot.id) == Err(
            SnapshotNotFound(snapshot.id)
        )
    finally:
        if service_instance is not None:
            connect.Disconnect(service_instance)
