from app.kimi.model_catalog import parse_model_catalog


def test_parse_model_catalog_builds_stable_openai_model_ids():
    catalog = parse_model_catalog(
        {
            "availableModels": [
                {
                    "scenario": "SCENARIO_K2D5",
                    "displayName": "K2.6 Instant",
                    "description": "Quick response",
                },
                {
                    "scenario": "SCENARIO_K2D5",
                    "displayName": "K2.6 Thinking",
                    "description": "Deep thinking",
                    "thinking": True,
                },
                {
                    "scenario": "SCENARIO_OK_COMPUTER",
                    "displayName": "K2.6 Agent",
                    "description": "Agent mode",
                    "kimiPlusId": "ok-computer",
                    "agentMode": "TYPE_NORMAL",
                },
                {
                    "scenario": "SCENARIO_OK_COMPUTER",
                    "displayName": "K2.6 Agent Swarm",
                    "description": "Agent swarm mode",
                    "kimiPlusId": "ok-computer",
                    "agentMode": "TYPE_ULTRA",
                },
            ],
            "defaultScenario": {"scenario": "SCENARIO_K2D5"},
        }
    )

    assert [model.id for model in catalog.models] == [
        "kimi-k2.6",
        "kimi-k2.6-thinking",
        "kimi-k2.6-agent",
        "kimi-k2.6-agent-swarm",
    ]
    assert catalog.default_model_id == "kimi-k2.6"
    assert catalog.by_id("kimi-k2.6-agent").agent_mode == "TYPE_NORMAL"

