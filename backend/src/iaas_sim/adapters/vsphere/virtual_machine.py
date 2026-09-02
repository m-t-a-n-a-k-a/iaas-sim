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
from iaas_sim.application.virtual_machine import (
    PowerCommandSubmissionFailure,
    VirtualMachineBackendFailure,
    VirtualMachineNotFound,
)
from iaas_sim.domain.entity.virtual_machine import (
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

logger: Final[logging.Logger] = logging.getLogger("iaas_sim.adapters.vsphere")


@dataclass(frozen=True, slots=True)
class VsphereTaskRef:
    managed_object_reference: str


@runtime_checkable
class VsphereVirtualMachineObject(Protocol):
    def PowerOnVM_Task(self) -> object: ...

    def PowerOffVM_Task(self) -> object: ...


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


class VSphereVirtualMachineAdapter:
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
