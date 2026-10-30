"""Agent-loop budget, rules engine, verification and chat routing tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import chat, config, db  # noqa: E402
from app.agent_loop import process_job  # noqa: E402
from app.search_backend import Fixture  # noqa: E402
from app.intent import parse_intent  # noqa: E402
from app.rules_engine import choose_search  # noqa: E402
from app.verify import coverage_from_coordinates, verify_candidate  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        db.init_db()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestRulesEngine(Base):
    def test_intent_extracts_nematode_target(self):
        intent = parse_intent("Is there a related gene in nematodes?")
        self.assertEqual(intent["target_organism"], "nematodes")

    def test_protein_identify_maps_to_blastp(self):
        choice = choose_search(intent=parse_intent("Identify this protein"), detected_type="protein")
        self.assertEqual(choice["program"], "blastp")


class TestVerify(Base):
    def test_coverage_from_coordinates(self):
        self.assertEqual(coverage_from_coordinates(query_start=1, query_end=50, query_length=100), 50.0)

    def test_length_mismatch_fails(self):
        candidate = {"classification": "strong", "query_coverage": 90.0,
                     "subject_length": 2000, "annotation": "globin"}
        result = verify_candidate(candidate=candidate,
                                  reciprocal_hits=[{"accession": "Q1", "evalue": 1e-20, "annotation": "globin"}],
                                  query_accession="Q1", query_length=100, query_annotation="globin")
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["failing_check"], "length")


class TestBudget(Base):
    def test_budget_exhaustion_reports_incomplete(self):
        backend = Fixture(primary_hits=[], reciprocal_hits={})
        job = db.create_job(question="Is there a related gene in nematodes?",
                            raw_input=">q\nMVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQ", whatsapp_user_id="u1")
        old = config.MAX_SEARCHES_PER_JOB
        config.MAX_SEARCHES_PER_JOB = 1
        try:
            final = process_job(job, backend)
        finally:
            config.MAX_SEARCHES_PER_JOB = old
        self.assertEqual(final["status"], "done")
        self.assertIn(final["outcome"], ("incomplete_budget", "not_confirmed"))
        self.assertLessEqual(final["searches_used"], 2)  # primary (+reciprocal none) within cap logic


class TestReciprocal(Base):
    SEQ = "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQ"

    def _backend(self, cls: type[Fixture] = Fixture) -> Fixture:
        case_hits = [{
            "accession": "HIT1", "organism": "C. elegans", "annotation": "hemoglobin family protein",
            "identity": 60.0, "query_start": 1, "query_end": 40, "alignment_length": 40,
            "subject_length": 45, "bit_score": 100.0, "evalue": 1e-12, "sequence": "MVHLTP",
        }]
        return cls(
            sequences={"NP_000509": {"accession": "NP_000509.1", "organism": "",
                                     "annotation": "hemoglobin subunit beta [Homo sapiens]",
                                     "sequence": self.SEQ}},
            primary_hits=case_hits,
            reciprocal_hits={"HIT1": [{"accession": "NP_000509", "evalue": 1e-10,
                                       "annotation": "hemoglobin subunit beta [Homo sapiens]",
                                       "query_start": 1, "query_end": 40, "subject_length": 44}]},
        )

    def _run(self, backend: Fixture) -> dict:
        job = db.create_job(question="Is there a related gene in nematodes?",
                            raw_input="NP_000509", whatsapp_user_id="u1")
        return process_job(job, backend)

    def test_reciprocal_targets_query_organism(self):
        backend = self._backend()
        final = self._run(backend)
        self.assertEqual(final["outcome"], "confirmed")
        kinds = {s["parameters"].get("kind", "primary"): s for s in backend.submissions}
        self.assertEqual(kinds["primary"]["parameters"]["organism_filter"], "nematodes")
        self.assertEqual(kinds["reciprocal"]["parameters"]["organism_filter"], "Homo sapiens")

    def test_fetch_step_names_resolving_backend(self):
        backend = self._backend()
        final = self._run(backend)
        fetch = next(s for s in db.get_step_log(final["id"]) if s["step"] == "fetch_accession")
        self.assertIn(backend.name, fetch["reason"])

    def test_incomplete_reciprocal_tries_next_candidate(self):
        class RecipFailBackend(Fixture):
            def poll(self, rid: str) -> str:
                sub = next((s for s in self.submissions if s["rid"] == rid), None)
                if sub and sub["parameters"].get("kind") == "reciprocal":
                    return "failed"
                return "ready"

        final = self._run(self._backend(RecipFailBackend))
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["outcome"], "not_confirmed")
        decisions = [s["decision"] for s in db.get_step_log(final["id"])]
        self.assertIn("try next candidate", decisions)


class TestChat(Base):
    def _backend(self) -> Fixture:
        case_hits = [{
            "accession": "HIT1", "organism": "C. elegans", "annotation": "globin",
            "identity": 60.0, "query_start": 1, "query_end": 40, "alignment_length": 40,
            "subject_length": 45, "bit_score": 100.0, "evalue": 1e-12, "sequence": "MVHLTP",
        }]
        return Fixture(
            sequences={"NP_000509": {"accession": "NP_000509", "organism": "human",
                                     "annotation": "globin",
                                     "sequence": "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQ"}},
            primary_hits=case_hits,
            reciprocal_hits={"HIT1": [{"accession": "NP_000509", "evalue": 1e-10, "annotation": "globin",
                                       "query_start": 1, "query_end": 40, "subject_length": 44}]},
        )

    def test_sequence_message_starts_job(self):
        result = chat.handle_message(whatsapp_user_id="u9", text="NP_000509 related gene in nematodes?",
                                     backend=self._backend())
        self.assertEqual(result["action"], "job")
        self.assertIsNotNone(result["job_id"])

    def test_followup_quotes_stored_values(self):
        backend = self._backend()
        chat.handle_message(whatsapp_user_id="u9", text="NP_000509 related gene in nematodes?", backend=backend)
        result = chat.handle_message(whatsapp_user_id="u9", text="What was the E-value?", backend=backend)
        self.assertEqual(result["action"], "followup")
        self.assertIn("1e-12", result["reply"])

    def test_followup_without_job_says_so(self):
        result = chat.handle_message(whatsapp_user_id="new", text="What was the E-value?",
                                     backend=self._backend())
        self.assertIn("no jobs yet", result["reply"].lower())


if __name__ == "__main__":
    unittest.main()
