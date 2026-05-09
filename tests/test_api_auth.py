def test_v1_models_requires_api_key_even_when_no_keys_are_configured(
    api_client,
    reset_key_store,
):
    response = api_client.get("/v1/models")

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_v1_models_rejects_unknown_api_key_when_no_keys_are_configured(
    api_client,
    reset_key_store,
):
    response = api_client.get(
        "/v1/models",
        headers={"Authorization": "Bearer sk-unknown"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_v1_models_accepts_configured_api_key(api_client, configured_api_key):
    response = api_client.get(
        "/v1/models",
        headers={"Authorization": f"Bearer {configured_api_key.key}"},
    )

    assert response.status_code == 200
    assert response.json()["object"] == "list"
