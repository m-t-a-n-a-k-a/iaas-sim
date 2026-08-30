from fastapi.testclient import TestClient

from iaas_sim.bootstrap.main import app


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
