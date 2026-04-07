import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.services.category_classifier import CategoryClassifier


class CategoryClassifierConfigTests(unittest.TestCase):
    def test_classifier_uses_llm_factory_chat_model(self):
        classifier = CategoryClassifier()
        self.assertEqual(getattr(classifier.llm, "temperature", None), 0.1)
        self.assertTrue(hasattr(classifier.llm, "with_structured_output"))


if __name__ == "__main__":
    unittest.main()
