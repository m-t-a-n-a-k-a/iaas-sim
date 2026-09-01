from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Final, Protocol, runtime_checkable

from pyVim import connect
from pyVmomi import vim

from iaas_sim.application.virtual_machine import (
    PowerCommandSubmissionFailure,
    VirtualMachineAdapterFailure,
    VirtualMachineNotFound,
)
from iaas_sim.domain.entity.operation import VsphereTaskRef
from iaas_sim.domain.entity.virtual_machine import (
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

logger: Final[logging.Logger] = logging.getLogger("iaas_sim.adapters.vsphere")


class _RuntimeInfo(Protocol):
    powerState: object


class _SummaryInfo(Protocol):
    runtime: _RuntimeInfo


@runtime_checkable
class _VirtualMachineObject(Protocol):
    name: str
    summary: _SummaryInfo

    def PowerOnVM_Task(self) -> object: ...

    def PowerOffVM_Task(self) -> object: ...


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
    def _managed_object_id(vm: _VirtualMachineObject) -> str:
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
    ) -> _VirtualMachineObject | None:
        content = service_instance.RetrieveContent()
        view_manager = content.viewManager
        if view_manager is None:
            return None
        inventory = view_manager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
        for vm in inventory.view:
            if isinstance(vm, _VirtualMachineObject) and self._managed_object_id(vm) == str(
                virtual_machine_id
            ):
                return vm
        return None

    def _to_domain(self, vm: _VirtualMachineObject) -> VirtualMachine:
        """
        Project vSphere object → Domain VirtualMachine.

        VirtualMachine.power_state reflects backend-observed state.
        """
        virtual_machine_id = VirtualMachineId(self._managed_object_id(vm))
        power_state_str: str | None = None
        try:
            power_state_str = str(vm.summary.runtime.powerState)
            state = {
                "poweredOn": PowerState.RUNNING,
                "poweredOff": PowerState.STOPPED,
            }.get(power_state_str)
        except AttributeError:
            state = None
        if state is None:
            raise ValueError(f"unsupported power state: {power_state_str}")
        return VirtualMachine(virtual_machine_id, str(vm.name), state)

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[VirtualMachine], VirtualMachineAdapterFailure]:
        service_instance: vim.ServiceInstance | None = None
        try:
            service_instance = self._connect()
            content = service_instance.RetrieveContent()
            view_manager = content.viewManager
            if view_manager is None:
                return Err(VirtualMachineAdapterFailure("list", "view manager unavailable"))
            inventory = view_manager.CreateContainerView(
                content.rootFolder, [vim.VirtualMachine], True
            )
            return Ok(
                tuple(
                    self._to_domain(vm)
                    for vm in inventory.view
                    if isinstance(vm, _VirtualMachineObject)
                )
            )
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
            return Ok(self._to_domain(vm))
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
    ) -> Result[VsphereTaskRef, PowerCommandSubmissionFailure]:
        """
        Submit async power command to vSphere backend.

        Returns:
            Ok(VsphereTaskRef): Task created, tracked for async completion
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
            return Ok(VsphereTaskRef(task_mor))

        except Exception as exc:
            logger.exception("vSphere power command submission failed")
            return Err(PowerCommandSubmissionFailure(virtual_machine_id, str(exc)))
        finally:
            if service_instance is not None:
                try:
                    connect.Disconnect(service_instance)
                except Exception:
                    logger.exception("vSphere disconnect failed")
