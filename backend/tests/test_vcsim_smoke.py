from __future__ import annotations

import os
import time

import pytest
from pyVim import connect
from pyVmomi import vim


@pytest.mark.skipif(
    os.getenv("PYVMOMI_SMOKE") != "1",
    reason=(
        "Run through make smoke-test or set PYVMOMI_SMOKE=1 to execute "
        "the real vcsim connectivity check."
    ),
)
def test_vcsim_retrieve_content_success() -> None:
    host = os.getenv("VSPHERE_HOST", "127.0.0.1")
    port = int(os.getenv("VSPHERE_PORT", "8989"))
    username = os.getenv("VSPHERE_USERNAME", "user")
    password = os.getenv("VSPHERE_PASSWORD", "pass")

    service_instance = None
    last_error: Exception | None = None
    for _ in range(30):
        try:
            service_instance = connect.SmartConnect(
                protocol="https",
                host=host,
                port=port,
                user=username,
                pwd=password,
                disableSslCertValidation=True,
            )
            break
        except Exception as exc:  # pragma: no cover
            # Startup race is expected while the compose vcsim service is booting.
            last_error = exc
            time.sleep(1)

    assert service_instance is not None, f"vcsim did not become ready: {last_error}"

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
        assert len(vms) >= 1
        assert content.rootFolder is not None
    finally:
        connect.Disconnect(service_instance)
