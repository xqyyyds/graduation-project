import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


import Backend.app.core.config as config_module


class ConfigDefaultsTests(unittest.TestCase):
    def test_resolve_backend_path_anchors_relative_paths_to_backend_root(self):
        expected = BACKEND_ROOT / "app" / "scripts" / "chroma_db"
        resolved = config_module._resolve_backend_path(
            "___UNSET_TEST_PATH___", str(Path("app") / "scripts" / "chroma_db")
        )
        self.assertEqual(Path(resolved).resolve(), expected.resolve())

    def test_config_source_keeps_empty_default_api_key_placeholder(self):
        source = Path(config_module.__file__).read_text(encoding="utf-8")
        self.assertIn('os.getenv("ZHIPU_API_KEY", "")', source)
        self.assertNotIn("bad91148-3e61-4cb2-9615-3b838333849c", source)

    def test_force_audit_update_defaults_to_false(self):
        source = Path(config_module.__file__).read_text(encoding="utf-8")
        self.assertIn('os.getenv("FORCE_AUDIT_UPDATE", "False")', source)


if __name__ == "__main__":
    unittest.main()
