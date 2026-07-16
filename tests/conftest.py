import pytest


@pytest.fixture(autouse=True)
def _stub_health_check(monkeypatch):
    """Keep the background token health loop offline during unit tests.

    The lifespan now starts health.health_loop(), which would otherwise fire a
    real model-list request to Trae on startup. Stub the upstream call so the
    unit suite never touches the network.
    """
    try:
        import health
    except Exception:
        return

    async def _fake_list_models():
        return []

    monkeypatch.setattr(health, "list_models", _fake_list_models, raising=False)
