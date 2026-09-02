from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from pyVim import connect
from pyVmomi import VmomiSupport, vim

from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationRef,
    BackendOperationRunning,
    BackendOperationStatus,
    BackendOperationSucceeded,
    OperationPollingFailure,
)
from iaas_sim.application.snapshot import (
    SnapshotBackendFailure,
    SnapshotCommandSubmissionFailure,
    SnapshotNotFound,
)
from iaas_sim.application.virtual_machine import (
    PowerCommandSubmissionFailure,
    VirtualMachineBackendFailure,
    VirtualMachineNotFound,
)
from iaas_sim.domain.entity.snapshot import Snapshot, SnapshotId
from iaas_sim.domain.entity.virtual_machine import (
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result

logger: Final[logging.Logger] = logging.getLogger("iaas_sim.adapters.vsphere")


@dataclass(frozen=True, slots=True)
class VsphereTaskRef:
    managed_object_reference: str


@runtime_checkable
class VsphereVirtualMachineObject(Protocol):
    def PowerOnVM_Task(self) -> object: ...

    def PowerOffVM_Task(self) -> object: ...


@runtime_checkable
class VsphereSnapshotVirtualMachine(VsphereVirtualMachineObject, Protocol):
    def CreateSnapshot_Task(
        self, name: str, description: str, memory: bool, quiesce: bool
    ) -> object: ...


@runtime_checkable
class VsphereSnapshotObject(Protocol):
    def RemoveSnapshot_Task(self, removeChildren: bool, consolidate: bool) -> object: ...


class VsphereDynamicProperty(Protocol):
    name: str
    val: object


class VsphereObjectContent(Protocol):
    propSet: Sequence[VsphereDynamicProperty]


@runtime_checkable
class VspherePropertyCollector(Protocol):
    def RetrieveContents(self, specSet: list[object]) -> Sequence[VsphereObjectContent]: ...


@runtime_checkable
class VmodlDataObjectFactory(Protocol):
    def __call__(self) -> object: ...


def new_vmodl_data_object(type_name: str) -> object:
    data_object_type = VmomiSupport.GetVmodlType(type_name)
    if not isinstance(data_object_type, VmodlDataObjectFactory):
        raise TypeError(f"VMODL type is not a data object: {type_name}")
    return data_object_type()


def project_virtual_machine(
    virtual_machine_id: VirtualMachineId, name: str, observed_power_state: object
) -> VirtualMachine:
    """Project explicitly collected vSphere properties into the Domain entity."""
    power_state = str(observed_power_state)
    state = {
        "poweredOn": PowerState.RUNNING,
        "poweredOff": PowerState.STOPPED,
    }.get(power_state)
    if state is None:
        raise ValueError(f"unsupported power state: {power_state}")
    return VirtualMachine(virtual_machine_id, name, state)


def virtual_machine_property_filter(
    vm: VsphereVirtualMachineObject,
) -> object:
    """Request only the VM properties needed by the control-plane projection."""
    object_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.ObjectSpec")
    object.__setattr__(object_spec, "obj", vm)
    property_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.PropertySpec")
    object.__setattr__(property_spec, "type", vim.VirtualMachine)
    object.__setattr__(property_spec, "pathSet", ["name", "summary.runtime.powerState"])
    filter_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.FilterSpec")
    object.__setattr__(filter_spec, "objectSet", [object_spec])
    object.__setattr__(filter_spec, "propSet", [property_spec])
    return filter_spec


def snapshot_property_filter(vm: VsphereVirtualMachineObject) -> object:
    """Request only the snapshot tree roots needed by the flat projection."""
    object_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.ObjectSpec")
    object.__setattr__(object_spec, "obj", vm)
    property_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.PropertySpec")
    object.__setattr__(property_spec, "type", vim.VirtualMachine)
    object.__setattr__(property_spec, "pathSet", ["snapshot.rootSnapshotList"])
    filter_spec = new_vmodl_data_object("vmodl.query.PropertyCollector.FilterSpec")
    object.__setattr__(filter_spec, "objectSet", [object_spec])
    object.__setattr__(filter_spec, "propSet", [property_spec])
    return filter_spec


def snapshot_roots(
    property_collector: object, vm: VsphereVirtualMachineObject
) -> tuple[object, ...]:
    """Load snapshot roots explicitly; an absent property means no snapshots."""
    if not isinstance(property_collector, VspherePropertyCollector):
        raise TypeError("vSphere property collector unavailable")
    contents = property_collector.RetrieveContents([snapshot_property_filter(vm)])
    if len(contents) != 1:
        raise ValueError("snapshot properties unavailable")
    properties = contents[0].propSet
    if len(properties) == 0:
        return ()
    if len(properties) != 1 or properties[0].name != "snapshot.rootSnapshotList":
        raise ValueError("malformed snapshot properties")
    roots = properties[0].val
    if not isinstance(roots, Sequence):
        raise ValueError("malformed snapshot roots")
    return tuple(roots)


def project_snapshots(
    virtual_machine_id: VirtualMachineId, roots: Sequence[object]
) -> tuple[Snapshot, ...]:
    """Flatten the backend tree without exposing its hierarchy to the domain."""
    owner = ResourceReference("virtualMachines", str(virtual_machine_id))
    projected: list[Snapshot] = []

    def visit(node: object) -> None:
        name = object.__getattribute__(node, "name")
        snapshot_object = object.__getattribute__(node, "snapshot")
        children = object.__getattribute__(node, "childSnapshotList")
        snapshot_id = object.__getattribute__(snapshot_object, "_moId")
        if (
            not isinstance(name, str)
            or not isinstance(snapshot_id, str)
            or not isinstance(children, Sequence)
        ):
            raise ValueError("malformed snapshot tree")
        projected.append(Snapshot(SnapshotId(snapshot_id), name, owner))
        for child in children:
            visit(child)

    for root in roots:
        visit(root)
    return tuple(projected)


class VSphereAdapter:
    """
    vSphere Adapter: control-plane ↔ backend translation.

    Invariants:
    - Does NOT maintain shadow state of VM power_state
    - Does NOT mutate domain VirtualMachine
    - submit_power_command() returns Task reference for Adapter-internal tracking
    - Backend Task identity (MOR) is NOT exposed as public Operation ID
    """

    @staticmethod
    def _managed_object_id(vm: VsphereVirtualMachineObject) -> str:
        return str(object.__getattribute__(vm, "_moId"))

    def _connect(self) -> vim.ServiceInstance:
        return connect.SmartConnect(
            protocol=os.getenv("VSPHERE_SCHEME", "https"),
            host=os.getenv("VSPHERE_HOST", "vcsim"),
            port=int(os.getenv("VSPHERE_PORT", "8989")),
            user=os.getenv("VSPHERE_USERNAME", "user"),
            pwd=os.getenv("VSPHERE_PASSWORD", "pass"),
            disableSslCertValidation=True,
        )

    def _project(
        self,
        property_collector: object,
        vm: VsphereVirtualMachineObject,
    ) -> VirtualMachine:
        if not isinstance(property_collector, VspherePropertyCollector):
            raise TypeError("vSphere property collector unavailable")
        filter_spec = virtual_machine_property_filter(vm)
        contents = property_collector.RetrieveContents([filter_spec])
        if len(contents) != 1:
            raise ValueError("VM properties unavailable")
        properties: dict[str, object] = {
            dynamic_property.name: dynamic_property.val for dynamic_property in contents[0].propSet
        }
        name = properties.get("name")
        power_state = properties.get("summary.runtime.powerState")
        if not isinstance(name, str):
            raise ValueError("VM name unavailable")
        if power_state is None:
            raise ValueError("VM power state unavailable")
        return project_virtual_machine(
            VirtualMachineId(self._managed_object_id(vm)), name, power_state
        )

    def _find(
        self, service_instance: vim.ServiceInstance, virtual_machine_id: VirtualMachineId
    ) -> VsphereVirtualMachineObject | None:
        content = service_instance.RetrieveContent()
        view_manager = content.viewManager
        if view_manager is None:
            return None
        inventory = view_manager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
        for vm in inventory.view:
            if isinstance(vm, VsphereVirtualMachineObject) and self._managed_object_id(vm) == str(
                virtual_machine_id
            ):
                return vm
        return None

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[VirtualMachine], VirtualMachineBackendFailure]:
        service_instance: vim.ServiceInstance | None = None
        try:
            connected = self._connect()
            service_instance = connected
            content = connected.RetrieveContent()
            view_manager = content.viewManager
            if view_manager is None:
                return Err(VirtualMachineBackendFailure("list", "view manager unavailable"))
            inventory = view_manager.CreateContainerView(
                content.rootFolder, [vim.VirtualMachine], True
            )
            vms: list[VirtualMachine] = []
            for vm in inventory.view:
                if not isinstance(vm, VsphereVirtualMachineObject):
                    continue
                try:
                    vms.append(self._project(content.propertyCollector, vm))
                except ValueError as exc:
                    logger.warning(
                        "Skipping VM %s: %s",
                        self._managed_object_id(vm),
                        exc,
                    )
            return Ok(tuple(vms))
        except Exception as exc:
            logger.exception("vSphere VM listing failed")
            return Err(VirtualMachineBackendFailure("list", str(exc)))
        finally:
            if service_instance is not None:
                try:
                    connect.Disconnect(service_instance)
                except Exception:
                    logger.exception("vSphere disconnect failed")

    def get_virtual_machine(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[
        VirtualMachine,
        VirtualMachineNotFound | VirtualMachineBackendFailure,
    ]:
        service_instance: vim.ServiceInstance | None = None
        try:
            service_instance = self._connect()
            vm = self._find(service_instance, virtual_machine_id)
            if vm is None:
                return Err(VirtualMachineNotFound(virtual_machine_id))
            content = service_instance.RetrieveContent()
            return Ok(self._project(content.propertyCollector, vm))
        except Exception as exc:
            logger.exception("vSphere VM retrieval failed")
            return Err(VirtualMachineBackendFailure("get", str(exc)))
        finally:
            if service_instance is not None:
                try:
                    connect.Disconnect(service_instance)
                except Exception:
                    logger.exception("vSphere disconnect failed")

    def submit_power_command(
        self, virtual_machine_id: VirtualMachineId, command: PowerCommand
    ) -> Result[BackendOperationRef, PowerCommandSubmissionFailure]:
        """
        Submit async power command to vSphere backend.

        Returns:
            Ok(BackendOperationRef): opaque backend operation reference
            Err(PowerCommandSubmissionFailure): submission failed

        Does not block on Task completion.
        Backend Task MOR is not exposed as public Operation ID.
        """
        service_instance: vim.ServiceInstance | None = None
        try:
            service_instance = self._connect()
            vm = self._find(service_instance, virtual_machine_id)
            if vm is None:
                return Err(PowerCommandSubmissionFailure(virtual_machine_id, "not found"))

            # Submit async task
            task = vm.PowerOnVM_Task() if command is PowerCommand.START else vm.PowerOffVM_Task()

            # Extract Task MOR for internal tracking
            task_mor = str(object.__getattribute__(task, "_moId"))
            task_ref = VsphereTaskRef(task_mor)
            return Ok(BackendOperationRef(task_ref.managed_object_reference))

        except Exception as exc:
            logger.exception("vSphere power command submission failed")
            return Err(PowerCommandSubmissionFailure(virtual_machine_id, str(exc)))
        finally:
            if service_instance is not None:
                try:
                    connect.Disconnect(service_instance)
                except Exception:
                    logger.exception("vSphere disconnect failed")

    @staticmethod
    def _snapshot_id(snapshot_object: object) -> SnapshotId:
        return SnapshotId(str(object.__getattribute__(snapshot_object, "_moId")))

    def list_snapshots(self) -> Result[Sequence[Snapshot], SnapshotBackendFailure]:
        service_instance: vim.ServiceInstance | None = None
        try:
            service_instance = self._connect()
            content = service_instance.RetrieveContent()
            view_manager = content.viewManager
            if view_manager is None:
                return Err(SnapshotBackendFailure("list", "view manager unavailable"))
            inventory = view_manager.CreateContainerView(
                content.rootFolder, [vim.VirtualMachine], True
            )
            snapshots: list[Snapshot] = []
            for vm in inventory.view:
                if isinstance(vm, VsphereVirtualMachineObject):
                    roots = snapshot_roots(content.propertyCollector, vm)
                    snapshots.extend(
                        project_snapshots(VirtualMachineId(self._managed_object_id(vm)), roots)
                    )
            return Ok(tuple(snapshots))
        except Exception as exc:
            logger.exception("vSphere snapshot listing failed")
            return Err(SnapshotBackendFailure("list", str(exc)))
        finally:
            if service_instance is not None:
                connect.Disconnect(service_instance)

    def get_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[Snapshot, SnapshotNotFound | SnapshotBackendFailure]:
        listed = self.list_snapshots()
        if isinstance(listed, Err):
            return Err(listed.error)
        for snapshot in listed.value:
            if snapshot.id == snapshot_id:
                return Ok(snapshot)
        return Err(SnapshotNotFound(snapshot_id))

    def submit_create_snapshot(
        self, virtual_machine_id: VirtualMachineId, name: str
    ) -> Result[BackendOperationRef, SnapshotCommandSubmissionFailure]:
        service_instance: vim.ServiceInstance | None = None
        try:
            service_instance = self._connect()
            vm = self._find(service_instance, virtual_machine_id)
            if not isinstance(vm, VsphereSnapshotVirtualMachine):
                return Err(
                    SnapshotCommandSubmissionFailure(
                        "create", str(virtual_machine_id), "virtual machine not found"
                    )
                )
            task = vm.CreateSnapshot_Task(name, "", False, False)
            return Ok(BackendOperationRef(str(object.__getattribute__(task, "_moId"))))
        except Exception as exc:
            logger.exception("vSphere snapshot creation submission failed")
            return Err(
                SnapshotCommandSubmissionFailure("create", str(virtual_machine_id), str(exc))
            )
        finally:
            if service_instance is not None:
                connect.Disconnect(service_instance)

    def _find_snapshot_object(
        self, service_instance: vim.ServiceInstance, snapshot_id: SnapshotId
    ) -> VsphereSnapshotObject | None:
        vm_content = service_instance.RetrieveContent()
        view_manager = vm_content.viewManager
        if view_manager is None:
            return None
        inventory = view_manager.CreateContainerView(
            vm_content.rootFolder, [vim.VirtualMachine], True
        )
        for vm in inventory.view:
            if not isinstance(vm, VsphereVirtualMachineObject):
                continue
            pending = list(snapshot_roots(vm_content.propertyCollector, vm))
            while pending:
                node = pending.pop()
                snapshot_object = object.__getattribute__(node, "snapshot")
                if self._snapshot_id(snapshot_object) == snapshot_id:
                    if isinstance(snapshot_object, VsphereSnapshotObject):
                        return snapshot_object
                    raise ValueError("snapshot removal API unavailable")
                pending.extend(object.__getattribute__(node, "childSnapshotList"))
        return None

    def submit_delete_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[BackendOperationRef, SnapshotCommandSubmissionFailure]:
        service_instance: vim.ServiceInstance | None = None
        try:
            service_instance = self._connect()
            snapshot = self._find_snapshot_object(service_instance, snapshot_id)
            if snapshot is None:
                return Err(
                    SnapshotCommandSubmissionFailure(
                        "delete", str(snapshot_id), "snapshot not found"
                    )
                )
            # Delete only this snapshot; do not implicitly delete descendants. Consolidation is
            # requested because removal otherwise leaves snapshot delta files behind.
            task = snapshot.RemoveSnapshot_Task(removeChildren=False, consolidate=True)
            return Ok(BackendOperationRef(str(object.__getattribute__(task, "_moId"))))
        except Exception as exc:
            logger.exception("vSphere snapshot deletion submission failed")
            return Err(SnapshotCommandSubmissionFailure("delete", str(snapshot_id), str(exc)))
        finally:
            if service_instance is not None:
                connect.Disconnect(service_instance)

    def get_operation_status(
        self, backend_ref: BackendOperationRef
    ) -> Result[BackendOperationStatus, OperationPollingFailure]:
        service_instance: vim.ServiceInstance | None = None
        try:
            connected = self._connect()
            service_instance = connected
            task_ref = VsphereTaskRef(str(backend_ref))
            task = vim.Task(task_ref.managed_object_reference, connected._stub)
            state = str(task.info.state)
            if state in ("queued", "running"):
                return Ok(BackendOperationRunning())
            if state == "success":
                return Ok(BackendOperationSucceeded())
            if state == "error":
                error = task.info.error
                reason = str(error) if error is not None else "backend task failed"
                return Ok(BackendOperationFailed(reason))
            return Err(OperationPollingFailure(f"unsupported backend task state: {state}"))
        except Exception as exc:
            logger.exception("vSphere task polling failed")
            return Err(OperationPollingFailure(str(exc)))
        finally:
            if service_instance is not None:
                try:
                    connect.Disconnect(service_instance)
                except Exception:
                    logger.exception("vSphere disconnect failed")
