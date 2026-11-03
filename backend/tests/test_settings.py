"""Per-user settings: validation, presets, storage, API gating (no network)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db, settings  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = config.DATABASE_PATH
        self._old_user = config.AUTH_USERNAME
        self._old_pw = config.AUTH_PASSWORD
        self._old_samesite = config.COOKIE_SAMESITE
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        config.AUTH_USERNAME = "reviewer"
        config.AUTH_PASSWORD = "s3cret-review"
        # Local .env may set split-host "none" (Secure cookie, dropped over
        # the test client's http); the session flow here needs the default.
        config.COOKIE_SAMESITE = "lax"
        db.init_db()

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._old_db
        config.AUTH_USERNAME = self._old_user
        config.AUTH_PASSWORD = self._old_pw
        config.COOKIE_SAMESITE = self._old_samesite
        self._tmp.cleanup()


class TestValidate(Base):
    def test_defaults_when_empty(self):
        self.assertEqual(settings.validate_settings({}), settings.DEFAULT_SETTINGS)

    def test_rejects_bad_backend_and_strictness(self):
        with self.assertRaises(ValueError):
            settings.validate_settings({"default_backend": "moon"})
        with self.assertRaises(ValueError):
            settings.validate_settings({"strictness": "wild"})

    def test_trims_and_caps_text(self):
        out = settings.validate_settings({"lab_name": "  My Lab  ", "default_organism": " nematodes "})
        self.assertEqual(out["lab_name"], "My Lab")
        self.assertEqual(out["default_organism"], "nematodes")


class TestPresets(Base):
    def test_loose_raises_submission_threshold_only(self):
        params = settings.apply_strictness({"evalue_threshold": 0.01}, "loose")
        self.assertEqual(params["evalue_threshold"], 10.0)
        self.assertEqual(params["strictness_preset"], "loose")

    def test_strict_caps_at_strong_boundary(self):
        params = settings.apply_strictness({"evalue_threshold": 0.01}, "strict")
        self.assertEqual(params["evalue_threshold"], 1e-5)

    def test_balanced_keeps_rules_default(self):
        params = settings.apply_strictness({"evalue_threshold": 0.01}, "balanced")
        self.assertEqual(params["evalue_threshold"], 0.01)

    def test_short_query_profile_never_overridden(self):
        params = settings.apply_strictness(
            {"evalue_threshold": 200000.0, "short_query_adjusted": True}, "strict")
        self.assertEqual(params["evalue_threshold"], 200000.0)

    def test_classification_cutoffs_unchanged_by_presets(self):
        cutoffs = settings.classification_cutoffs()
        self.assertEqual(cutoffs["strong_max_evalue"], config.STRONG_MAX_EVALUE)
        self.assertEqual(cutoffs["borderline_max_evalue"], config.BORDERLINE_MAX_EVALUE)


class TestStorage(Base):
    def test_roundtrip_and_user_isolation(self):
        user_a = db.create_user("alice", "hash-a")
        user_b = db.create_user("bob", "hash-b")
        settings.save_settings(user_a["id"], {"lab_name": "Alice Lab", "strictness": "loose"})
        self.assertEqual(settings.get_settings(user_a["id"])["lab_name"], "Alice Lab")
        self.assertEqual(settings.get_settings(user_a["id"])["strictness"], "loose")
        self.assertEqual(settings.get_settings(user_b["id"]), settings.DEFAULT_SETTINGS)


class TestApi(Base):
    def _client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app)

    def test_settings_require_login(self):
        with self._client() as client:
            self.assertEqual(client.get("/settings").status_code, 401)
            self.assertEqual(client.put("/settings", json={}).status_code, 401)

    def test_save_get_and_job_snapshot(self):
        with self._client() as client:
            login = client.post("/auth/login", json={"username": "reviewer", "password": "s3cret-review"})
            self.assertEqual(login.status_code, 200)
            saved = client.put("/settings", json={
                "lab_name": "Review Lab", "default_organism": "nematodes",
                "default_backend": "local", "strictness": "loose"})
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json()["settings"]["strictness"], "loose")
            full = client.get("/settings")
            self.assertEqual(full.status_code, 200)
            body = full.json()
            self.assertEqual(body["settings"]["default_organism"], "nematodes")
            self.assertIn("balanced", body["presets"])
            self.assertEqual(body["standard_cutoffs"]["strong_max_evalue"], 1e-5)
            bad = client.put("/settings", json={"strictness": "wild"})
            self.assertEqual(bad.status_code, 422)

    def test_custom_cutoffs_and_classify(self):
        from app.classify import classify_hit

        custom = {"strong_max_evalue": 1e-3, "strong_min_coverage": 50.0,
                  "borderline_max_evalue": 0.1, "borderline_min_coverage": 20.0}
        out = settings.validate_settings({"cutoff_mode": "custom", "cutoffs": custom})
        self.assertEqual(out["cutoffs"], custom)
        # Same hit, different ruler: standard says borderline, custom says strong.
        self.assertEqual(classify_hit(1e-4, 60.0), "borderline")
        self.assertEqual(classify_hit(1e-4, 60.0, custom), "strong")
        self.assertEqual(settings.job_cutoffs(out)["mode"], "custom")
        with self.assertRaises(ValueError):
            settings.validate_settings({"cutoff_mode": "custom", "cutoffs": {
                "strong_max_evalue": 0.5, "strong_min_coverage": 50.0,
                "borderline_max_evalue": 0.1, "borderline_min_coverage": 20.0}})

    def test_muse_key_write_only(self):
        user = db.create_user("carol", "hash-c")
        settings.save_settings(user["id"], {"muse_api_key": "sk-demo-1234567890"})
        self.assertEqual(settings.get_muse_key(user["id"]), "sk-demo-1234567890")
        self.assertNotIn("muse_api_key", settings.get_settings(user["id"]))
        hint = settings.muse_key_hint(user["id"])
        self.assertTrue(hint["muse_key_set"])
        self.assertEqual(hint["muse_key_last4"], "7890")
        settings.save_settings(user["id"], {"clear_muse_key": True})
        self.assertEqual(settings.get_muse_key(user["id"]), "")

    def test_ai_setup_demo_without_key(self):
        with self._client() as client:
            client.post("/auth/login", json={"username": "reviewer", "password": "s3cret-review"})
            res = client.post("/settings/ai-setup", json={"database": "swissprot", "message": "help"})
            self.assertEqual(res.status_code, 200)
            body = res.json()
            self.assertEqual(body["mode"], "demo")
            self.assertTrue(body["plan"]["steps"])
            self.assertIn("local BLAST setup plan", body["reply"])


if __name__ == "__main__":
    unittest.main()
