from fastapi.testclient import TestClient

import backend.app as app_module


def test_mock_endpoint() -> None:
    """Проверяет, что mock endpoint возвращает ожидаемую заглушку."""
    client = TestClient(app_module.app)
    response = client.get("/api/mock")
    assert response.status_code == 200
    assert "скоро появится прогноз" in response.json()["message"]


def test_health_endpoint() -> None:
    """Проверяет healthcheck endpoint для smoke-тестов деплоя."""
    client = TestClient(app_module.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
