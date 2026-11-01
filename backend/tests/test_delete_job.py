"""DELETE /jobs/{id} contract + db.delete_job (no network)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, config, db  # noqa: E402
from app.main import delete_job  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class TestDeleteJob(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        db.init_db()
        owner = db.create_user("owner", auth.hash_password("password-1234"))
        self.user = {"id": owner["id"], "username": owner["username"]}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_delete_finished_job_removes_searches_and_steps(self):
        job = db.create_job(question="q", raw_input="NP_000509", user_id=self.user["id"])
        db.add_step(job["id"], step="validate", observation="ok", decision="accept", reason="test")
        db.create_search(job["id"], kind="primary", program="blastp",
                         database="refseq_protein", parameters={}, rid="X")
        db.update_job(job["id"], status="done")
        result = delete_job(job["id"], user=self.user)
        self.assertEqual(result, {"status": "deleted", "id": job["id"]})
        self.assertIsNone(db.get_job(job["id"]))
        self.assertEqual(db.get_searches(job["id"]), [])
        self.assertEqual(db.get_step_log(job["id"]), [])

    def test_delete_missing_job_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            delete_job("WG-NOPE", user=self.user)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_delete_running_job_is_409(self):
        job = db.create_job(question="q", raw_input="NP_000509", user_id=self.user["id"])
        db.update_job(job["id"], status="running")
        with self.assertRaises(HTTPException) as ctx:
            delete_job(job["id"], user=self.user)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIsNotNone(db.get_job(job["id"]))

    def test_delete_unowned_job_is_404(self):
        other = db.create_user("other", auth.hash_password("password-1234"))
        job = db.create_job(question="q", raw_input="NP_000509", user_id=other["id"])
        db.update_job(job["id"], status="done")
        with self.assertRaises(HTTPException) as ctx:
            delete_job(job["id"], user=self.user)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIsNotNone(db.get_job(job["id"]))


if __name__ == "__main__":
    unittest.main()
