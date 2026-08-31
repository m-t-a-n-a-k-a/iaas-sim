from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from pyVim import connect
from pyVmomi import vim

from iaas_sim.result import Err, Ok, Result

logger: logging.Logger = logging.getLogger("iaas_sim.adapters.vsphere")


@dataclass(frozen=True, slots=True)
class VcsimConnectionFailure:
    host: str
    port: int
    reason: str


@dataclass(frozen=True, slots=True)
class VcsimInventoryFailure:
    host: str
    port: int
    reason: str


VcsimHealthFailure = VcsimConnectionFailure | VcsimInventoryFailure


def vcsim_health_check() -> Result[dict[str, object], VcsimHealthFailure]:
    """Open a real pyVmomi session to vcsim and fetch minimal inventory."""
    host = os.getenv("VSPHERE_HOST", "vcsim")
    port = int(os.getenv("VSPHERE_PORT", "8989"))
    protocol = os.getenv("VSPHERE_SCHEME", "https")
    username = os.getenv("VSPHERE_USERNAME", "user")
    password = os.getenv("VSPHERE_PASSWORD", "pass")
    service_instance: vim.ServiceInstance | None = None

    try:
        service_instance = connect.SmartConnect(
            protocol=protocol,
            host=host,
            port=port,
            user=username,
            pwd=password,
            disableSslCertValidation=True,
        )
    except Exception as exc:
        logger.exception("pyVmomi connection to %s:%s failed", host, port)
        return Err(VcsimConnectionFailure(host=host, port=port, reason=str(exc)))

    assert service_instance is not None

    try:
        content = service_instance.RetrieveContent()
        view_manager = content.viewManager
        if view_manager is None:
            return Err(
                VcsimInventoryFailure(
                    host=host,
                    port=port,
                    reason="vcsim view manager is unavailable",
                )
            )
        inventory = view_manager.CreateContainerView(
            content.rootFolder,
            [vim.VirtualMachine],
            True,
        )
        vms = list(inventory.view)
        return Ok(
            dict[str, object](
                {
                    "status": "ok",
                    "host": host,
                    "port": port,
                    "virtual_machine_count": len(vms),
                    "service_instance": service_instance.__class__.__name__,
                }
            )
        )
    except Exception as exc:
        logger.exception("vcsim inventory retrieval failed for %s:%s", host, port)
        return Err(VcsimInventoryFailure(host=host, port=port, reason=str(exc)))
    finally:
        try:
            connect.Disconnect(service_instance)
        except Exception:
            logger.exception("pyVmomi disconnect failed for %s:%s", host, port)
