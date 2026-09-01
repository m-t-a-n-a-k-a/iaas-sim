from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from pyVim import connect
from pyVmomi import vim

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
    VirtualMachineAdapterFailure,
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


class VsphereRuntimeInfo(Protocol):
    @property
    def powerState(self) -> object: ...


class VsphereSummaryInfo(Protocol):
    @property
    def runtime(self) -> VsphereRuntimeInfo: ...


@runtime_checkable
class VsphereVirtualMachineObject(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def summary(self) -> VsphereSummaryInfo: ...

    def PowerOnVM_Task(self) -> object: ...

    def PowerOffVM_Task(self) -> object: ...


def project_virtual_machine(vm: VsphereVirtualMachineObject) -> VirtualMachine:
    """Project a vSphere VM's observed summary into the Domain entity."""
    virtual_machine_id = VirtualMachineId(str(object.__getattribute__(vm, "_moId")))
    power_state = str(vm.summary.runtime.powerState)
    state = {
        "poweredOn": PowerState.RUNNING,
        "poweredOff": PowerState.STOPPED,
    }.get(power_state)
    if state is None:
        raise ValueError(f"unsupported power state: {power_state}")
    return VirtualMachine(virtual_machine_id, str(vm.name), state)


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
    ) -> Result[Sequence[VirtualMachine], VirtualMachineAdapterFailure]:
        service_instance: vim.ServiceInstance | None = None
        try:
            connected = self._connect()
            service_instance = connected
            content = connected.RetrieveContent()
            view_manager = content.viewManager
            if view_manager is None:
                return Err(VirtualMachineAdapterFailure("list", "view manager unavailable"))
            inventory = view_manager.CreateContainerView(
                content.rootFolder, [vim.VirtualMachine], True
            )
            vms: list[VirtualMachine] = []
            for vm in inventory.view:
                if not isinstance(vm, VsphereVirtualMachineObject):
                    continue
                try:
                    vms.append(project_virtual_machine(vm))
                except ValueError as exc:
                    logger.warning(
                        "Skipping VM %s: %s",
                        self._managed_object_id(vm),
                        exc,
                    )
            return Ok(tuple(vms))
        except Exception as exc:
            logger.exception("vSphere VM listing failed")
            return Err(VirtualMachineAdapterFailure("list", str(exc)))
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
        VirtualMachineNotFound | VirtualMachineAdapterFailure,
    ]:
        service_instance: vim.ServiceInstance | None = None
        try:
            service_instance = self._connect()
            vm = self._find(service_instance, virtual_machine_id)
            if vm is None:
                return Err(VirtualMachineNotFound(virtual_machine_id))
            return Ok(project_virtual_machine(vm))
        except Exception as exc:
            logger.exception("vSphere VM retrieval failed")
            return Err(VirtualMachineAdapterFailure("get", str(exc)))
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
