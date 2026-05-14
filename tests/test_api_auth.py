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
        "kimi-k2.6-search",
        "kimi-k2.6-thinking-search",
    ]
    assert "kimi-k2.5-search" not in {model["id"] for model in data}
    assert data[0]["scenario"] == "SCENARIO_K2D5"
    assert data[1]["thinking"] is True
    assert data[4]["thinking"] is False
    assert data[5]["thinking"] is True
    assert all("supports_web_search" not in model for model in data)


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


async def test_openai_responses_web_search_tool_enables_search():
    from app.api.models import _resolve_model

    for tool_type in ("web_search", "web_search_preview"):
        features = await _resolve_model(
            {
                "model": "kimi-k2.6-thinking",
                "tools": [{"type": tool_type}],
                "input": "today's Shenzhen weather",
            }
        )

        assert features["enable_web_search"] is True


async def test_openai_chat_web_search_options_enables_search():
    from app.api.models import _resolve_model

    features = await _resolve_model(
        {
            "model": "kimi-k2.6",
            "web_search_options": {},
            "messages": [{"role": "user", "content": "today's Shenzhen weather"}],
        }
    )

    assert features["enable_web_search"] is True


async def test_legacy_web_search_parameter_still_enables_search():
    from app.api.models import _resolve_model

    features = await _resolve_model(
        {
            "model": "kimi-k2.6-thinking",
            "enable_web_search": True,
            "messages": [{"role": "user", "content": "today's Shenzhen weather"}],
        }
    )

    assert features["enable_web_search"] is True


async def test_search_alias_models_enable_search_automatically():
    from app.api.models import _resolve_model

    instant = await _resolve_model(
        {
            "model": "kimi-k2.6-search",
            "messages": [{"role": "user", "content": "today's Shenzhen weather"}],
        }
    )
    thinking = await _resolve_model(
        {
            "model": "kimi-k2.6-thinking-search",
            "messages": [{"role": "user", "content": "today's Shenzhen weather"}],
        }
    )

    assert instant["model"] == "kimi-k2.6"
    assert instant["request_model"] == "kimi-k2.6-search"
    assert instant["enable_web_search"] is True
    assert instant["enable_thinking"] is False
    assert thinking["model"] == "kimi-k2.6-thinking"
    assert thinking["request_model"] == "kimi-k2.6-thinking-search"
    assert thinking["enable_web_search"] is True
    assert thinking["enable_thinking"] is True


def test_chat_rejects_web_search_for_agent_model(api_client, configured_api_key):
    response = api_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {configured_api_key.key}"},
        json={
            "model": "kimi-k2.6-agent",
            "tools": [{"type": "web_search"}],
            "messages": [{"role": "user", "content": "today's Shenzhen weather"}],
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["type"] == "invalid_request_error"
    assert "does not support web search" in body["error"]["message"]
