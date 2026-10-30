"""Offline eval harness — textbook cases (PRD §4.3, blast-rules §11).

Runs the full agent loop on recorded NCBI responses (tests/fixtures).
Checks behaviour, not exact hit names. No network. Run:

    cd backend && .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db  # noqa: E402
from app.agent_loop import process_job  # noqa: E402
from app.search_backend import Fixture  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load_case(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class EvalCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        db.init_db()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_case(self, fixture_name: str) -> tuple[dict, dict, Fixture]:
        case = load_case(fixture_name)
        backend = Fixture(fixture_name)
        job = db.create_job(question=case["question"], raw_input=case["accession"],
                            whatsapp_user_id="eval")
        final = process_job(job, backend)
        return case, final, backend


class TestGlobin(EvalCase):
    def test_program_choice_is_tblastn_for_gene_discovery(self):
        _case, final, _backend = self.run_case("globin_nematode.json")
        self.assertEqual(final["program"], "tblastn")
        self.assertEqual(final["database"], "est")

    def test_true_hit_confirmed(self):
        _case, final, _backend = self.run_case("globin_nematode.json")
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["outcome"], "confirmed")
        top = final["hits"][0]
        self.assertEqual(top["classification"], "strong")
        self.assertGreater(top["query_coverage"], 70)

    def test_step_log_records_reasons(self):
        _case, final, _backend = self.run_case("globin_nematode.json")
        steps = [s["step"] for s in db.get_step_log(final["id"])]
        for expected in ("validate", "choose_search", "submit", "classify", "verify", "summarise"):
            self.assertIn(expected, steps)
        self.assertTrue(all(s["reason"] for s in db.get_step_log(final["id"])))


class TestInsulin(EvalCase):
    def test_program_choice_is_blastp(self):
        _case, final, _backend = self.run_case("insulin_celegans.json")
        self.assertEqual(final["program"], "blastp")
        self.assertEqual(final["database"], "refseq_protein")

    def test_hit_classified_borderline_not_oversold(self):
        _case, final, _backend = self.run_case("insulin_celegans.json")
        self.assertEqual(final["hits"][0]["classification"], "borderline")
        # Settings must be recorded because composition moves this E-value.
        self.assertIn("matrix", final["parameters"])


class TestRBP4(EvalCase):
    def test_weak_hit_is_not_significant(self):
        _case, final, _backend = self.run_case("rbp4_cg8.json")
        weak = next(h for h in final["hits"] if h["accession"] == "CG8_WEAK")
        self.assertEqual(weak["classification"], "not_significant")

    def test_false_positive_rejected(self):
        _case, final, _backend = self.run_case("rbp4_cg8.json")
        self.assertEqual(final["outcome"], "not_confirmed")
        verify_steps = [s for s in db.get_step_log(final["id"]) if s["step"] == "verify"]
        self.assertTrue(verify_steps)
        self.assertIn("not confirmed", verify_steps[0]["decision"])


if __name__ == "__main__":
    unittest.main()
