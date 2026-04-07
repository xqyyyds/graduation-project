import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class LLMFactoryUsageTests(unittest.TestCase):
    def test_active_category_classifier_uses_llm_factory(self):
        source = (BACKEND_ROOT / "app" / "services" / "category_classifier.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from app.core.llm_factory import get_main_llm", source)
        self.assertNotIn("ChatOpenAI(", source)

    def test_active_chroma_manager_hyde_uses_llm_factory(self):
        source = (BACKEND_ROOT / "app" / "db" / "chroma_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from app.core.llm_factory import get_main_llm", source)
        self.assertNotIn("ChatOpenAI(", source)

    def test_historical_service_also_uses_llm_factory(self):
        source = (BACKEND_ROOT / "app" / "services" / "historical.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from app.core.llm_factory import get_main_llm", source)
        self.assertNotIn("ChatOpenAI(", source)


if __name__ == "__main__":
    unittest.main()
