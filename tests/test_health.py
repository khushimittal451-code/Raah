import asyncio

import httpx

from app.main import app

def request(method, path, **kwargs):
    async def perform():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(perform())


def test_health_states_liveness_without_claiming_model_readiness():
    response = request("GET", "/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "raah-ml-service",
        "seed": 57,
        "data_mode": "synthetic-only",
        "controller": "virtual-demo",
        "syllabus": "UNVERIFIED",
    }


def test_health_is_read_only():
    assert request("POST", "/health").status_code == 405


def test_cors_allows_local_client():
    response = request("GET", "/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_does_not_allow_arbitrary_origin():
    response = request("GET", "/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in response.headers
