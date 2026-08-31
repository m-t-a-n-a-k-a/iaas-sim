from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Final, Protocol, runtime_checkable

from pyVim import connect
from pyVmomi import vim

from iaas_sim.application.virtual_machine import (
    VirtualMachineAdapterFailure,
    VirtualMachineNotFound,
    VirtualMachineOperationFailure,
)
from iaas_sim.domain.entity.virtual_machine import PowerState, VirtualMachine, VirtualMachineId
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
    def __init__(self) -> None:
        self._power_states: dict[VirtualMachineId, PowerState] = {}

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
        virtual_machine_id = VirtualMachineId(self._managed_object_id(vm))
        try:
            state = {
                "poweredOn": PowerState.RUNNING,
                "poweredOff": PowerState.STOPPED,
            }.get(str(vm.summary.runtime.powerState))
        except AttributeError:
            state = self._power_states.get(virtual_machine_id, PowerState.STOPPED)
        if state is None:
            raise ValueError(f"unsupported power state: {vm.summary.runtime.powerState}")
        self._power_states[virtual_machine_id] = state
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

    def _power(
        self, virtual_machine_id: VirtualMachineId, operation: str
    ) -> Result[None, VirtualMachineOperationFailure]:
        service_instance: vim.ServiceInstance | None = None
        try:
            service_instance = self._connect()
            vm = self._find(service_instance, virtual_machine_id)
            if vm is None:
                return Err(
                    VirtualMachineOperationFailure(virtual_machine_id, operation, "not found")
                )
            if operation == "start":
                vm.PowerOnVM_Task()
                self._power_states[virtual_machine_id] = PowerState.RUNNING
            else:
                vm.PowerOffVM_Task()
                self._power_states[virtual_machine_id] = PowerState.STOPPED
            return Ok(None)
        except Exception as exc:
            logger.exception("vSphere VM power operation failed")
            return Err(VirtualMachineOperationFailure(virtual_machine_id, operation, str(exc)))
        finally:
            if service_instance is not None:
                try:
                    connect.Disconnect(service_instance)
                except Exception:
                    logger.exception("vSphere disconnect failed")

    def power_on(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[None, VirtualMachineOperationFailure]:
        return self._power(virtual_machine_id, "start")

    def power_off(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[None, VirtualMachineOperationFailure]:
        return self._power(virtual_machine_id, "stop")
