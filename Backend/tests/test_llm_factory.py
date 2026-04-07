import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from Backend.app.core.llm_factory import resolve_llm_config


class LLMFactoryConfigTests(unittest.TestCase):
    ENV_KEYS = [
        "LLM_MODEL",
        "LLM_BASE_URL",
        "ZHIPU_API_KEY",
        "FAST_LLM_MODEL",
        "FAST_LLM_BASE_URL",
        "FAST_LLM_API_KEY",
        "STRONG_LLM_MODEL",
        "STRONG_LLM_BASE_URL",
        "STRONG_LLM_API_KEY",
    ]

    def setUp(self):
        self.original_env = os.environ.copy()
        for key in self.ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_single_legacy_config_is_used_as_main_model(self):
        os.environ["LLM_MODEL"] = "legacy-model"
        os.environ["LLM_BASE_URL"] = "https://legacy.example/v1"
        os.environ["ZHIPU_API_KEY"] = "legacy-key"

        config = resolve_llm_config()

        self.assertEqual(config.model, "legacy-model")
        self.assertEqual(config.base_url, "https://legacy.example/v1")
        self.assertEqual(config.api_key, "legacy-key")

    def test_fast_config_overrides_legacy_config(self):
        os.environ["LLM_MODEL"] = "legacy-model"
        os.environ["LLM_BASE_URL"] = "https://legacy.example/v1"
        os.environ["ZHIPU_API_KEY"] = "legacy-key"
        os.environ["FAST_LLM_MODEL"] = "main-model"
        os.environ["FAST_LLM_BASE_URL"] = "https://main.example/v1"
        os.environ["FAST_LLM_API_KEY"] = "main-key"

        config = resolve_llm_config()

        self.assertEqual(config.model, "main-model")
        self.assertEqual(config.base_url, "https://main.example/v1")
        self.assertEqual(config.api_key, "main-key")

    def test_strong_env_is_ignored_in_single_model_mode(self):
        os.environ["FAST_LLM_MODEL"] = "main-model"
        os.environ["FAST_LLM_BASE_URL"] = "https://main.example/v1"
        os.environ["FAST_LLM_API_KEY"] = "main-key"
        os.environ["STRONG_LLM_MODEL"] = "old-strong-model"
        os.environ["STRONG_LLM_BASE_URL"] = "https://strong.example/v1"
        os.environ["STRONG_LLM_API_KEY"] = "strong-key"

        config = resolve_llm_config()

        self.assertEqual(config.model, "main-model")
        self.assertEqual(config.base_url, "https://main.example/v1")
        self.assertEqual(config.api_key, "main-key")


if __name__ == "__main__":
    unittest.main()
