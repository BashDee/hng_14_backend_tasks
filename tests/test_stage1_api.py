from __future__ import annotations

import asyncio
import os
import re

import pytest
from fastapi.testclient import TestClient
from supabase import create_client

from main import app


UUID_V7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
UTC_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.fixture()
def isolated_client(tmp_path, monkeypatch):
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        pytest.skip("Set SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) to run integration tests")

    monkeypatch.setenv("SUPABASE_URL", supabase_url)
    monkeypatch.setenv("SUPABASE_KEY", supabase_key)

    with TestClient(app) as client:
        supabase_client = create_client(supabase_url, supabase_key)
        supabase_client.table("profiles").delete().neq("id", "").execute()
        yield client


def install_upstream_successes(client: TestClient, *, gender: str = "female", age: int = 46, country_id: str = "DRC"):
    async def fake_get(url: str, **kwargs):
        await asyncio.sleep(0)
        name = kwargs.get("params", {}).get("name", "unknown")
        if "genderize" in url:
            return FakeResponse({"name": name, "gender": gender, "probability": 0.99, "count": 1234})
        if "agify" in url:
            return FakeResponse({"name": name, "age": age, "count": 999})
        if "nationalize" in url:
            return FakeResponse(
                {
                    "name": name,
                    "country": [
                        {"country_id": country_id, "probability": 0.85},
                        {"country_id": "NG", "probability": 0.2},
                    ],
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    client.app.state.http_client.get = fake_get


def install_upstream_custom(client: TestClient, responses_by_service: dict[str, dict]):
    async def fake_get(url: str, **kwargs):
        await asyncio.sleep(0)
        name = kwargs.get("params", {}).get("name", "unknown")
        if "genderize" in url:
            payload = responses_by_service["genderize"]
            return FakeResponse({"name": name, **payload})
        if "agify" in url:
            payload = responses_by_service["agify"]
            return FakeResponse({"name": name, **payload})
        if "nationalize" in url:
            payload = responses_by_service["nationalize"]
            return FakeResponse({"name": name, **payload})
        raise AssertionError(f"Unexpected URL: {url}")

    client.app.state.http_client.get = fake_get


def create_profile(client: TestClient, name: str):
    return client.post("/api/profiles", json={"name": name})


def test_stage0_classify_success(isolated_client):
    async def fake_get(url: str, **kwargs):
        await asyncio.sleep(0)
        return FakeResponse({"gender": "male", "probability": 0.99, "count": 1234})

    isolated_client.app.state.http_client.get = fake_get

    response = isolated_client.get("/api/classify?name=bashir")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["data"]["name"] == "bashir"
    assert response.json()["data"]["is_confident"] is True


@pytest.mark.parametrize(
    "query, expected_status, expected_message",
    [
        ("/api/classify", 400, "Missing or empty name"),
        ("/api/classify?name=", 400, "Missing or empty name"),
        ("/api/classify?name=a&name=b", 422, "name must be a single string"),
    ],
)
def test_stage0_classify_validation_status_mappings(isolated_client, query, expected_status, expected_message):
    response = isolated_client.get(query)

    assert response.status_code == expected_status
    assert response.json() == {"status": "error", "message": expected_message}


def test_stage0_classify_no_prediction_returns_200_error(isolated_client):
    async def fake_get(url: str, **kwargs):
        await asyncio.sleep(0)
        return FakeResponse({"gender": None, "probability": 0.0, "count": 0})

    isolated_client.app.state.http_client.get = fake_get

    response = isolated_client.get("/api/classify?name=unknown")

    assert response.status_code == 200
    assert response.json() == {
        "status": "error",
        "message": "No prediction available for the provided name",
    }


@pytest.mark.parametrize(
    "body, expected_status, expected_message",
    [
        ({}, 400, "Missing or empty name"),
        ({"name": ""}, 400, "Missing or empty name"),
        ({"name": 123}, 422, "Invalid type"),
        ({"name": ["ella"]}, 422, "Invalid type"),
    ],
)
def test_create_profile_validation_status_mappings(isolated_client, body, expected_status, expected_message):
    response = isolated_client.post("/api/profiles", json=body)

    assert response.status_code == expected_status
    assert response.json() == {"status": "error", "message": expected_message}


def test_create_profile_success_persists_and_returns_contract(isolated_client):
    install_upstream_successes(isolated_client)

    response = create_profile(isolated_client, "ella")

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "success"

    data = payload["data"]
    assert data["name"] == "ella"
    assert data["gender"] == "female"
    assert data["gender_probability"] == pytest.approx(0.99)
    assert data["sample_size"] == 1234
    assert data["age"] == 46
    assert data["age_group"] == "adult"
    assert data["country_id"] == "DRC"
    assert data["country_probability"] == pytest.approx(0.85)
    assert UUID_V7_PATTERN.match(data["id"])
    assert UTC_ISO_PATTERN.match(data["created_at"])


def test_duplicate_profile_returns_existing_record(isolated_client):
    install_upstream_successes(isolated_client)

    first_response = create_profile(isolated_client, "ella")
    second_response = create_profile(isolated_client, "Ella")

    assert first_response.status_code == 201
    assert second_response.status_code == 200

    payload = second_response.json()
    assert payload == {
        "status": "success",
        "message": "Profile already exists",
        "data": first_response.json()["data"],
    }


def test_get_single_profile_returns_persisted_record(isolated_client):
    install_upstream_successes(isolated_client)

    created = create_profile(isolated_client, "emmanuel")
    profile_id = created.json()["data"]["id"]

    response = isolated_client.get(f"/api/profiles/{profile_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["data"] == created.json()["data"]


def test_get_single_profile_not_found_returns_404(isolated_client):
    response = isolated_client.get("/api/profiles/00000000-0000-7000-8000-000000000000")

    assert response.status_code == 404
    assert response.json() == {"status": "error", "message": "Profile not found"}


def test_get_all_profiles_returns_filtered_results_case_insensitively(isolated_client):
    install_upstream_successes(isolated_client)

    first = create_profile(isolated_client, "ella")
    second = create_profile(isolated_client, "sarah")

    assert first.status_code == 201
    assert second.status_code == 201

    response = isolated_client.get("/api/profiles?gender=FeMaLe&country_id=drc&age_group=Adult")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["count"] == 2
    assert len(payload["data"]) == 2
    for item in payload["data"]:
        assert set(item.keys()) == {"id", "name", "gender", "age", "age_group", "country_id"}
        assert item["gender"] == "female"
        assert item["age_group"] == "adult"
        assert item["country_id"] == "DRC"


def test_delete_profile_returns_204_and_removes_record(isolated_client):
    install_upstream_successes(isolated_client)

    created = create_profile(isolated_client, "ella")
    profile_id = created.json()["data"]["id"]

    delete_response = isolated_client.delete(f"/api/profiles/{profile_id}")
    assert delete_response.status_code == 204
    assert delete_response.content == b""

    follow_up = isolated_client.get(f"/api/profiles/{profile_id}")
    assert follow_up.status_code == 404


def test_delete_profile_not_found_returns_404(isolated_client):
    response = isolated_client.delete("/api/profiles/00000000-0000-7000-8000-000000000000")

    assert response.status_code == 404
    assert response.json() == {"status": "error", "message": "Profile not found"}


@pytest.mark.parametrize(
    "responses_by_service, expected_message",
    [
        (
            {
                "genderize": {"gender": None, "probability": 0.99, "count": 1234},
                "agify": {"age": 46, "count": 999},
                "nationalize": {"country": [{"country_id": "NG", "probability": 0.2}]},
            },
            "Genderize returned an invalid response",
        ),
        (
            {
                "genderize": {"gender": "female", "probability": 0.99, "count": 1234},
                "agify": {"age": None, "count": 999},
                "nationalize": {"country": [{"country_id": "NG", "probability": 0.2}]},
            },
            "Agify returned an invalid response",
        ),
        (
            {
                "genderize": {"gender": "female", "probability": 0.99, "count": 1234},
                "agify": {"age": 46, "count": 999},
                "nationalize": {"country": []},
            },
            "Nationalize returned an invalid response",
        ),
    ],
)
def test_create_profile_upstream_edge_cases_return_502_and_do_not_persist(
    isolated_client, responses_by_service, expected_message
):
    install_upstream_custom(isolated_client, responses_by_service)

    response = create_profile(isolated_client, "ella")

    assert response.status_code == 502
    assert response.json() == {"status": "error", "message": expected_message}

    get_response = isolated_client.get("/api/profiles")
    assert get_response.status_code == 200
    assert get_response.json()["count"] == 0
