from __future__ import annotations

import logging
import os

from pyVim import connect
from pyVmomi import vim

logger: logging.Logger = logging.getLogger("iaas_sim.adapters.vsphere")


def vcsim_health_check() -> dict[str, object]:
    """Open a real pyVmomi session to vcsim and fetch minimal inventory."""
    host = os.getenv("VSPHERE_HOST", "vcsim")
    port = int(os.getenv("VSPHERE_PORT", "8989"))
    username = os.getenv("VSPHERE_USERNAME", "user")
    password = os.getenv("VSPHERE_PASSWORD", "pass")

    try:
        service_instance = connect.SmartConnect(
            host=host,
            port=port,
            user=username,
            pwd=password,
            disableSslCertValidation=True,
        )
    except Exception as exc:
        logger.exception("pyVmomi connection to %s:%s failed", host, port)
        raise RuntimeError(f"pyVmomi connection to {host}:{port} failed") from exc

    try:
        content = service_instance.RetrieveContent()
        view_manager = content.viewManager
        if view_manager is None:
            raise RuntimeError("vcsim view manager is unavailable")
        inventory = view_manager.CreateContainerView(
            content.rootFolder,
            [vim.VirtualMachine],
            True,
        )
        vms = list(inventory.view)
        return {
            "status": "ok",
            "host": host,
            "port": port,
            "virtual_machine_count": len(vms),
            "service_instance": service_instance.__class__.__name__,
        }
    except Exception as exc:
        logger.exception("vcsim inventory retrieval failed for %s:%s", host, port)
        raise RuntimeError(f"vcsim inventory retrieval failed for {host}:{port}") from exc
    finally:
        try:
            connect.Disconnect(service_instance)
        except Exception:
            logger.exception("pyVmomi disconnect failed for %s:%s", host, port)
