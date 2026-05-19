"""Общие фикстуры pytest: изоляция API-тестов от локального PostgreSQL."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: тесты с реальным PostgreSQL (нужен TEST_DATABASE_URL)",
    )


@pytest.fixture(autouse=True)
def _disable_database_url_for_tests(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Без DATABASE_URL lifespan не поднимает engine — pytest не требует Docker."""
    if request.node.get_closest_marker("integration"):
        return
    monkeypatch.delenv("DATABASE_URL", raising=False)
