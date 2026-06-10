import pytest
import httpx
from httpx import ASGITransport
from config import API_KEY
from main import app


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring real Trae API credentials")


@pytest.fixture(scope="session")
async def async_client():
    transport = ASGITransport(app=app)
    # The proxy requires a Bearer token on /v1/chat/completions when API_KEY is set
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        yield client
