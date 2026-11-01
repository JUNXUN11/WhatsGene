"""Model Ask guardrails: flag, quotas, cache, call log (no network).

The live Muse call is always mocked here; these tests prove the disabled
path costs nothing and the enabled path is capped, cached and logged.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import agent, auth, config, db  # noqa: E402


def _job(user_id: int) -> dict:
    job = db.create_job(question="q", raw_input="NP_000509", user_id=user_id, source="web")
    db.create_search(job["id"], kind="primary", program="blastp",
                     database="refseq_protein", parameters={"evalue_threshold": 10.0},
                     rid=None)
    return db.get_job(job["id"]) or job


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = {k: getattr(config, k) for k in (
            "DATABASE_PATH", "MODEL_ASK_ENABLED", "MUSE_API_KEY",
            "ASK_DAILY_LIMIT", "JOBS_DAILY_LIMIT")}
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        config.MODEL_ASK_ENABLED = False
        config.MUSE_API_KEY = ""
        config.ASK_DAILY_LIMIT = 20
        config.JOBS_DAILY_LIMIT = 10
        db.init_db()
        owner = db.create_user("owner", auth.hash_password("password-1234"))
        self.user_id = owner["id"]

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            setattr(config, key, value)
        self._tmp.cleanup()


class TestDisabledPath(Base):
    def test_disabled_returns_deterministic_and_logs_nothing(self):
        job = _job(self.user_id)
        with mock.patch("app.model_client.chat_completion") as chat:
            answer = agent.answer_followup(job=job, question="What program ran?",
                                           searches=db.get_searches(job["id"]),
                                           user_id=self.user_id)
        chat.assert_not_called()
        self.assertIn("blastp", answer)
        self.assertEqual(db.get_usage(self.user_id, db.today_iso(), "asks"), 0)
        self.assertEqual(db.list_model_calls(), [])

    def test_enabled_without_key_falls_back(self):
        config.MODEL_ASK_ENABLED = True
        job = _job(self.user_id)
        with mock.patch("app.model_client.chat_completion") as chat:
            answer = agent.answer_followup(job=job, question="What program ran?",
                                           searches=db.get_searches(job["id"]),
                                           user_id=self.user_id)
        chat.assert_not_called()
        self.assertIn("blastp", answer)


class TestLivePath(Base):
    def _enable(self):
        config.MODEL_ASK_ENABLED = True
        config.MUSE_API_KEY = "test-key"

    def test_success_is_cached_and_logged(self):
        self._enable()
        job = _job(self.user_id)
        canned = {"text": "The search ran blastp. E-value cutoff 10.", "usage": {"total_tokens": 42}}
        with mock.patch("app.model_client.chat_completion", return_value=canned) as chat:
            first = agent.answer_followup(job=job, question="What program ran?",
                                          searches=db.get_searches(job["id"]),
                                          user_id=self.user_id)
            second = agent.answer_followup(job=job, question="  what program ran? ",
                                           searches=db.get_searches(job["id"]),
                                           user_id=self.user_id)
        self.assertEqual(first, canned["text"])
        self.assertEqual(second, canned["text"])
        self.assertEqual(chat.call_count, 1)  # second ask served from cache
        self.assertEqual(db.get_usage(self.user_id, db.today_iso(), "asks"), 1)
        calls = db.list_model_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["job_id"], job["id"])
        self.assertIn("total_tokens", calls[0]["usage"] or "")

    def test_quota_blocks_before_any_model_call(self):
        self._enable()
        config.ASK_DAILY_LIMIT = 1
        job = _job(self.user_id)
        with mock.patch("app.model_client.chat_completion",
                        return_value={"text": "ok", "usage": None}) as chat:
            agent.answer_followup(job=job, question="first?",
                                  searches=db.get_searches(job["id"]), user_id=self.user_id)
            with self.assertRaises(agent.QuotaError):
                agent.answer_followup(job=job, question="second?",
                                      searches=db.get_searches(job["id"]), user_id=self.user_id)
        self.assertEqual(chat.call_count, 1)

    def test_model_failure_falls_back_to_deterministic(self):
        self._enable()
        job = _job(self.user_id)
        from app.model_client import ModelError

        with mock.patch("app.model_client.chat_completion", side_effect=ModelError("down")):
            answer = agent.answer_followup(job=job, question="What program ran?",
                                           searches=db.get_searches(job["id"]),
                                           user_id=self.user_id)
        self.assertIn("blastp", answer)
        calls = db.list_model_calls()
        self.assertEqual(len(calls), 1)
        self.assertIn("down", calls[0]["error"] or "")

    def test_forget_history_never_reaches_model(self):
        self._enable()
        job = _job(self.user_id)
        with mock.patch("app.model_client.chat_completion") as chat:
            answer = agent.answer_followup(job=job, question="forget my history",
                                           searches=db.get_searches(job["id"]),
                                           user_id=self.user_id)
        chat.assert_not_called()
        self.assertEqual(answer, "__FORGET_HISTORY__")


class TestJobsQuota(Base):
    def test_second_job_same_day_is_429(self):
        from fastapi import HTTPException

        from app.main import JobCreate, create_job

        old_backend, old_case = config.SEARCH_BACKEND, config.FIXTURE_CASE
        config.SEARCH_BACKEND, config.FIXTURE_CASE = "fixture", ""
        config.JOBS_DAILY_LIMIT = 1
        try:
            user = {"id": self.user_id, "username": "owner"}
            create_job(JobCreate(sequence="PNLHGLFGRKTG", question="q"), user=user)
            with self.assertRaises(HTTPException) as ctx:
                create_job(JobCreate(sequence="PNLHGLFGRKTG", question="q"), user=user)
            self.assertEqual(ctx.exception.status_code, 429)
        finally:
            config.SEARCH_BACKEND, config.FIXTURE_CASE = old_backend, old_case


if __name__ == "__main__":
    unittest.main()
