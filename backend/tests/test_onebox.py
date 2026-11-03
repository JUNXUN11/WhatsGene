"""One Box serving: /api dual mount, static files, SPA fallback (no network)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db  # noqa: E402
from app import main as app_main  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = config.DATABASE_PATH
        self._old_user = config.AUTH_USERNAME
        self._old_pw = config.AUTH_PASSWORD
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        config.AUTH_USERNAME = "reviewer"
        config.AUTH_PASSWORD = "s3cret-review"
        db.init_db()
        self._old_dist = app_main._FRONTEND_DIST
        dist = Path(self._tmp.name) / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>app shell</html>", encoding="utf-8")
        (dist / "app.js").write_text("console.log(1)", encoding="utf-8")
        (dist / "jobs").mkdir()
        (dist / "jobs" / "index.html").write_text("<html>jobs page</html>", encoding="utf-8")
        app_main._FRONTEND_DIST = dist

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._old_db
        config.AUTH_USERNAME = self._old_user
        config.AUTH_PASSWORD = self._old_pw
        app_main._FRONTEND_DIST = self._old_dist
        self._tmp.cleanup()


class TestOneBox(Base):
    def _client(self):
        from fastapi.testclient import TestClient

        return TestClient(app_main.app)

    def test_api_lives_at_root_and_under_api(self):
        with self._client() as client:
            root = client.get("/health")
            prefixed = client.get("/api/health")
        self.assertEqual(root.status_code, 200)
        self.assertEqual(prefixed.status_code, 200)
        self.assertEqual(root.json(), prefixed.json())

    def test_api_routes_win_over_spa_fallback(self):
        with self._client() as client:
            res = client.get("/api/jobs")  # gated: proves the API route ran
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.headers["content-type"], "application/json")

    def test_page_address_serves_shell_to_browsers(self):
        with self._client() as client:
            res = client.get("/jobs", headers={"Accept": "text/html"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("jobs page", res.text)

    def test_page_address_serves_api_to_api_clients(self):
        with self._client() as client:
            res = client.get("/jobs", headers={"Accept": "application/json"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.headers["content-type"], "application/json")

    def test_job_page_deep_link_serves_shell_to_browsers(self):
        with self._client() as client:
            res = client.get("/jobs/WG-123", headers={"Accept": "text/html"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("app shell", res.text)

    def test_docs_still_win_for_browsers(self):
        with self._client() as client:
            res = client.get("/docs", headers={"Accept": "text/html"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("swagger", res.text.lower())

    def test_static_file_served(self):
        with self._client() as client:
            res = client.get("/app.js")
        self.assertEqual(res.status_code, 200)
        self.assertIn("console.log", res.text)

    def test_unknown_page_falls_back_to_shell(self):
        with self._client() as client:
            res = client.get("/new")  # client-side route, no such file
        self.assertEqual(res.status_code, 200)
        self.assertIn("app shell", res.text)

    def test_unknown_api_path_is_json_404(self):
        with self._client() as client:
            res = client.get("/api/nope")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.headers["content-type"], "application/json")

    def test_missing_build_is_helpful_404(self):
        app_main._FRONTEND_DIST = None
        with self._client() as client:
            res = client.get("/")
        self.assertEqual(res.status_code, 404)
        self.assertIn("npm run generate", res.json()["detail".lower()])


if __name__ == "__main__":
    unittest.main()
