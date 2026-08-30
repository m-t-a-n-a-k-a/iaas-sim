from __future__ import annotations

import os

from pyVim import connect
from pyVmomi import vim


def vcsim_health_check() -> dict[str, object]:
    """Open a real pyVmomi session to vcsim and fetch minimal inventory."""
    host = os.getenv("VSPHERE_HOST", "vcsim")
    port = int(os.getenv("VSPHERE_PORT", "8989"))
    username = os.getenv("VSPHERE_USERNAME", "user")
    password = os.getenv("VSPHERE_PASSWORD", "pass")

    service_instance = connect.SmartConnect(
        host=host,
        port=port,
        user=username,
        pwd=password,
        disableSslCertValidation=True,
    )
    try:
        content = service_instance.RetrieveContent()
        view_manager = content.viewManager
        assert view_manager is not None
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
    finally:
        connect.Disconnect(service_instance)
