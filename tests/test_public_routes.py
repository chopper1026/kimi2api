import pytest


def test_root_does_not_expose_service_metadata(api_client):
    response = api_client.get("/")

    assert response.status_code == 404
    assert "Kimi2API" not in response.text
    assert "/v1/chat/completions" not in response.text


def test_healthz_remains_public(api_client):
    response = api_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_not_public(api_client, path):
    response = api_client.get(path)

    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/favicon.ico", "/favicon.svg"])
def test_favicon_is_available(api_client, path):
    response = api_client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert "<svg" in response.text
