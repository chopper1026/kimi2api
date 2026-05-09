import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class PublicRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_root_does_not_expose_service_metadata(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Kimi2API", response.text)
        self.assertNotIn("/v1/chat/completions", response.text)

    def test_healthz_remains_public(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
