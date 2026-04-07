import sys
import unittest
import importlib
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

backend_app = importlib.import_module("Backend.app")
sys.modules["app"] = backend_app

from app.api.main import app


class SettingsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "client_cm"):
            cls.client_cm.__exit__(None, None, None)

    def test_search_settings_endpoint_exists(self):
        with patch("app.api.main.settings.TAVILY_API_KEY", ""):
            response = self.client.get("/api/settings/search")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("tavily_api_key", payload)
        self.assertEqual(payload.get("persistence_mode"), "runtime")

    def test_search_test_endpoint_returns_structured_result(self):
        with patch("app.api.main.settings.TAVILY_API_KEY", ""):
            response = self.client.post("/api/settings/search/test", json={})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("status", payload)
        self.assertIn(payload["status"], ["ok", "error"])

    def test_llm_settings_endpoint_returns_single_main_model_shape(self):
        response = self.client.get("/api/settings/llm")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("main", payload)
        self.assertNotIn("fast", payload)
        self.assertNotIn("strong", payload)
        self.assertTrue(payload.get("single_llm_mode"))

    def test_update_llm_settings_accepts_single_main_model_payload(self):
        response = self.client.post(
            "/api/settings/llm",
            json={
                "main": {
                    "model": "gpt-5-mini",
                    "base_url": "https://example.com/v1",
                    "api_key": "sk-test",
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["single_llm_mode"])


if __name__ == "__main__":
    unittest.main()
