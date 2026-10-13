from fastapi.testclient import TestClient

from db.main import app


client = TestClient(app)


def test_catalog_metadata_and_component_query():
    metadata = client.get("/api/v1/catalog").json()
    assert metadata["components"]["GPU"]["count"] == 200

    response = client.post(
        "/api/v1/catalog/query",
        json={
            "component": "gpu",
            "filters": [{"field": "memory", "min": 8}],
            "sort": {"field": "memory", "direction": "desc"},
            "fields": ["opendb_id", "memory", "chipset"],
            "limit": 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["component"] == "GPU"
    assert body["total"] > 0
    assert len(body["items"]) <= 5
    assert all(set(item) <= {"opendb_id", "memory", "chipset"} for item in body["items"])


def test_compatibility_endpoint_and_invalid_query():
    response = client.get("/api/v1/catalog/candidates?component=gpu&max_tdp=200&limit=3")
    assert response.status_code == 200
    assert response.json()["limit"] == 3

    invalid = client.post(
        "/api/v1/catalog/query",
        json={"component": "gpu", "filters": [{"field": "metadata.manufacturer", "eq": "AMD"}]},
    )
    assert invalid.status_code == 400


def test_component_and_query_validation():
    assert client.get("/api/v1/catalog/not-a-component").status_code == 400
    invalid_operator = client.post(
        "/api/v1/catalog/query",
        json={"component": "ram", "filters": [{"field": "speed", "min": 3200, "max": 6400}]},
    )
    assert invalid_operator.status_code == 422
