"""Multi-workflow tests: short-query profile (Lab 04), fan-out, parallel
jobs, per-search storage, grounded Q&A, WhatsApp payloads, web API.

All searches run on the Fixture backend; no network, no BLAST+.
Run: cd backend && .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import agent, chat, config, db, worker  # noqa: E402
from app.agent_loop import process_job  # noqa: E402
from app.blast_params import parameters_for  # noqa: E402
from app.rules_engine import applicable_programs, plan_programs  # noqa: E402
from app.search_backend import Fixture  # noqa: E402
from app import whatsapp_client  # noqa: E402

SHORT_QUERY = "PNLHGLFGRKTG"  # Lab 04 Q1: 12-aa protein query


def _hits() -> list[dict]:
    return [{
        "accession": "HIT1", "organism": "C. elegans", "annotation": "globin-like protein",
        "identity": 60.0, "query_start": 1, "query_end": 12, "alignment_length": 12,
        "subject_length": 14, "bit_score": 40.0, "evalue": 1e-12, "sequence": SHORT_QUERY,
    }]


def _backend() -> Fixture:
    return Fixture(primary_hits=_hits(), reciprocal_hits={
        "HIT1": [{"accession": "RECIP1", "evalue": 1e-10, "annotation": "globin",
                  "query_start": 1, "query_end": 12, "subject_length": 14}]})


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        db.init_db()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestShortQueryProfile(Base):
    def test_lab04_short_blastp_parameters(self):
        params = parameters_for(program="blastp", detected_type="protein", query_length=12)
        self.assertEqual(params["evalue_threshold"], 200000.0)
        self.assertEqual(params["word_size"], 2)
        self.assertEqual(params["matrix"], "PAM30")
        self.assertTrue(params["short_query_adjusted"])
        self.assertEqual(params["ncbi_defaults"],
                         {"evalue_threshold": 10.0, "word_size": 3, "matrix": "BLOSUM62"})

    def test_long_protein_uses_standard_parameters(self):
        params = parameters_for(program="blastp", detected_type="protein", query_length=147)
        self.assertEqual(params["word_size"], 3)
        self.assertEqual(params["matrix"], "BLOSUM62")
        self.assertFalse(params["short_query_adjusted"])

    def test_applicable_programs_by_query_type(self):
        self.assertEqual(applicable_programs("protein"), ["blastp", "tblastn"])
        self.assertEqual(applicable_programs("dna"), ["blastn", "blastx", "tblastx"])

    def test_single_incompatible_program_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            plan_programs(intent={}, detected_type="protein", mode="single",
                          requested_program="blastn")
        self.assertIn("blastp", str(ctx.exception))


class TestFanoutWorkflow(Base):
    def _run_short_all(self) -> dict:
        job = db.create_job(question="What parameters were used?", raw_input=SHORT_QUERY,
                            whatsapp_user_id="u1", source="web", workflow_mode="all")
        return process_job(job, _backend())

    def test_all_mode_stores_each_program_with_its_parameters(self):
        final = self._run_short_all()
        self.assertEqual(final["status"], "done")
        searches = db.get_searches(final["id"])
        primaries = [s for s in searches if s["kind"] == "primary"]
        self.assertEqual([s["program"] for s in primaries], ["blastp", "tblastn"])
        blastp = primaries[0]["parameters"]
        self.assertEqual(blastp["evalue_threshold"], 200000.0)
        self.assertEqual(blastp["word_size"], 2)
        self.assertEqual(blastp["matrix"], "PAM30")
        self.assertTrue(all(s["hits"] for s in primaries))
        steps = [s["step"] for s in db.get_step_log(final["id"])]
        self.assertIn("plan_workflow", steps)
        self.assertIn("short_query", steps)

    def test_grounded_answers_quote_stored_lab04_values(self):
        final = self._run_short_all()
        searches = db.get_searches(final["id"])
        evalue = agent.answer_followup(job=final, searches=searches,
                                       question="What is the E-value cutoff?")
        self.assertIn("200000", evalue)
        word = agent.answer_followup(job=final, searches=searches,
                                     question="What is the word size?")
        self.assertIn("word size 2", word)
        self.assertIn("BLOSUM62", word)  # default shown for comparison
        compare = agent.answer_followup(job=final, searches=searches,
                                        question="Compare the programs")
        self.assertIn("blastp", compare)
        self.assertIn("tblastn", compare)
        unknown = agent.answer_followup(job=final, searches=searches,
                                        question="What is the weather today?")
        self.assertIn("can't answer that from the stored results", unknown)


class TestParallelJobs(Base):
    def test_two_workflows_for_one_user_both_finish(self):
        backend = _backend()
        jobs = [db.create_job(question="q", raw_input=SHORT_QUERY,
                              whatsapp_user_id="multi", source="web", workflow_mode="all")
                for _ in range(2)]
        for job in jobs:
            self.assertTrue(worker.submit_async(job, backend))
        deadline = time.time() + 30
        while time.time() < deadline:
            if all((db.get_job(j["id"]) or {}).get("status") == "done" for j in jobs):
                break
            time.sleep(0.05)
        self.assertTrue(all((db.get_job(j["id"]) or {}).get("status") == "done" for j in jobs))
        self.assertEqual(len(db.list_jobs_for_user("multi")), 2)

    def test_second_whatsapp_sequence_is_not_blocked(self):
        backend = _backend()
        first = chat.handle_message(whatsapp_user_id="wa1", text=SHORT_QUERY, backend=backend)
        second = chat.handle_message(whatsapp_user_id="wa1", text=SHORT_QUERY, backend=backend)
        self.assertEqual(first["action"], "job")
        self.assertEqual(second["action"], "job")
        self.assertNotEqual(first["job_id"], second["job_id"])

    def test_whatsapp_followup_can_target_an_older_job(self):
        backend = _backend()
        first = chat.handle_message(whatsapp_user_id="wa2", text=SHORT_QUERY, backend=backend)
        chat.handle_message(whatsapp_user_id="wa2", text=SHORT_QUERY, backend=backend)
        result = chat.handle_message(
            whatsapp_user_id="wa2",
            text=f"What was the E-value cutoff for {first['job_id']}?", backend=backend)
        self.assertEqual(result["job_id"], first["job_id"])
        self.assertIn("200000", result["reply"])


class TestWhatsAppClient(Base):
    def test_payload_builders(self):
        text = whatsapp_client.build_text_payload(to="123", body="done")
        self.assertEqual(text["type"], "text")
        template = whatsapp_client.build_template_payload(to="123", job_id="WG-1")
        self.assertEqual(template["template"]["name"], config.WHATSAPP_TEMPLATE_NAME)

    def test_send_without_credentials_fails_without_raising(self):
        old_token, old_id = config.WHATSAPP_TOKEN, config.WHATSAPP_PHONE_NUMBER_ID
        config.WHATSAPP_TOKEN, config.WHATSAPP_PHONE_NUMBER_ID = "", ""
        try:
            result = whatsapp_client.send_job_done(
                to="123", job_id="WG-1", summary="s", results_url="http://x/jobs/WG-1")
            self.assertEqual(result["status"], "failed")
        finally:
            config.WHATSAPP_TOKEN, config.WHATSAPP_PHONE_NUMBER_ID = old_token, old_id


class TestWebApi(Base):
    def test_submit_ask_and_cancel(self):
        from fastapi.testclient import TestClient

        from app.main import app

        old_backend, old_case = config.SEARCH_BACKEND, config.FIXTURE_CASE
        config.SEARCH_BACKEND, config.FIXTURE_CASE = "fixture", ""
        try:
            with TestClient(app) as client:
                created = client.post("/jobs", json={
                    "sequence": SHORT_QUERY, "question": "parameters?",
                    "workflow_mode": "single", "program": "blastp"})
                self.assertEqual(created.status_code, 201)
                job = created.json()
                self.assertEqual(job["searches"][0]["parameters"]["evalue_threshold"], 200000.0)
                asked = client.post(f"/jobs/{job['id']}/ask",
                                    json={"question": "What is the word size?"})
                self.assertIn("word size 2", asked.json()["answer"])
                listed = client.get("/jobs")
                self.assertTrue(any(j["id"] == job["id"] for j in listed.json()))
                self.assertNotIn("notify_to", job)
        finally:
            config.SEARCH_BACKEND, config.FIXTURE_CASE = old_backend, old_case


if __name__ == "__main__":
    unittest.main()
