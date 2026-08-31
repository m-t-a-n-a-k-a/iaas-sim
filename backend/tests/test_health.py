from fastapi.testclient import TestClient

from iaas_sim.adapters.vsphere.health import vcsim_health_check
from iaas_sim.bootstrap.main import app
from iaas_sim.result import Err, Ok


def test_result_primitives_are_immutable_and_typed() -> None:
    ok_value = Ok(value={"status": "ok"})
    err_value = Err(error={"status": "error"})

    assert ok_value.value == {"status": "ok"}
    assert err_value.error == {"status": "error"}
    assert isinstance(ok_value, Ok)
    assert isinstance(err_value, Err)


def test_vsphere_health_check_returns_result_on_failure() -> None:
    result = vcsim_health_check()

    assert isinstance(result, (Ok, Err))
    assert result is not None


def test_health_endpoint() -> None:
    expected_status_code = 200
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == expected_status_code
    body = response.json()
    assert "status" in body
    assert "checks" in body
    assert "vcsim" in body["checks"]
    assert "dex" in body["checks"]
    assert "otel_lgtm" in body["checks"]
