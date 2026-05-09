import unittest

from fastapi.testclient import TestClient

from app.core import keys
from app.main import create_app


class ApiAuthTest(unittest.TestCase):
    def setUp(self):
        keys._key_store.clear()
        self.client = TestClient(create_app())

    def tearDown(self):
        keys._key_store.clear()

    def test_v1_models_requires_api_key_even_when_no_keys_are_configured(self):
        response = self.client.get("/v1/models")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["type"], "invalid_request_error")

    def test_v1_models_rejects_unknown_api_key_when_no_keys_are_configured(self):
        response = self.client.get(
            "/v1/models",
            headers={"Authorization": "Bearer sk-unknown"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["type"], "invalid_request_error")

    def test_v1_models_accepts_configured_api_key(self):
        api_key = "sk-test-key"
        keys._key_store[api_key] = keys.ApiKey(
            key=api_key,
            name="Test key",
            created_at=0.0,
        )

        response = self.client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["object"], "list")


if __name__ == "__main__":
    unittest.main()
