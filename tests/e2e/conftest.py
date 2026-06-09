import pytest
import httpx
from httpx import ASGITransport
from main import app


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring real Trae API credentials")


@pytest.fixture(scope="session")
async def async_client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
