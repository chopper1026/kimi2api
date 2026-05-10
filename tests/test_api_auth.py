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


def test_v1_models_returns_dynamic_kimi_web_models(api_client, configured_api_key):
    response = api_client.get(
        "/v1/models",
        headers={"Authorization": f"Bearer {configured_api_key.key}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert [model["id"] for model in data] == [
        "kimi-k2.6",
        "kimi-k2.6-thinking",
        "kimi-k2.6-agent",
        "kimi-k2.6-agent-swarm",
    ]
    assert "kimi-k2.5-search" not in {model["id"] for model in data}
    assert data[0]["scenario"] == "SCENARIO_K2D5"
    assert data[1]["thinking"] is True


def test_v1_model_detail_rejects_unknown_model(api_client, configured_api_key):
    response = api_client.get(
        "/v1/models/kimi-k2.5-search",
        headers={"Authorization": f"Bearer {configured_api_key.key}"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_chat_rejects_conflicting_thinking_flag(api_client, configured_api_key):
    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {configured_api_key.key}"},
        json={
            "model": "kimi-k2.6",
            "enable_thinking": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_chat_rejects_unknown_model(api_client, configured_api_key):
    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {configured_api_key.key}"},
        json={
            "model": "kimi-k2.5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
