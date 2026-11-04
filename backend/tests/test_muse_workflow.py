"""Muse inside the workflow: intent reading, summary writing, and the
number guard on summaries and Ask. The model client is mocked; no network.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import agent, auth, config, db  # noqa: E402
from app.agent_loop import process_job  # noqa: E402
from app.search_backend import Fixture  # noqa: E402

QUERY = "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLSTPDAVMGNPKVKAHGKKVLGAFSDGLAHLDNLKGTFATLSELHCDKLHVDPENFRLLGNVLVCVLAHHFGKEFTPPVQAAYQKVVAGVANALAHKYH"


def _backend() -> Fixture:
    hit = {"accession": "P68873", "organism": "Pan troglodytes", "annotation": "Hemoglobin subunit beta",
           "identity": 100.0, "query_start": 1, "query_end": len(QUERY), "alignment_length": len(QUERY),
           "subject_length": len(QUERY), "bit_score": 300.0, "evalue": 6.55889e-106, "sequence": QUERY}
    return Fixture(primary_hits=[hit], reciprocal_hits={
        "P68873": [{"accession": "P68871", "evalue": 6.55889e-106, "annotation": "Hemoglobin subunit beta",
                    "query_start": 1, "query_end": len(QUERY), "subject_length": len(QUERY)}]})


def _reply(text: str) -> dict:
    return {"text": text, "usage": None}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old = config.DATABASE_PATH, config.MODEL_ASK_ENABLED
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        config.MODEL_ASK_ENABLED = False
        db.init_db()
        self.user = db.create_user("owner", auth.hash_password("pw"))
        # A key saved in Settings is the user's own opt-in for live calls.
        db.save_user_settings(self.user["id"], {"muse_api_key": "test-key"})

    def tearDown(self) -> None:
        config.DATABASE_PATH, config.MODEL_ASK_ENABLED = self._old
        self._tmp.cleanup()

    def _run(self, question: str, user_id: int | None = None) -> dict:
        job = db.create_job(question=question, raw_input=QUERY, source="web",
                            user_id=self.user["id"] if user_id is None else user_id)
        return process_job(job, _backend())


class TestIntent(Base):
    def test_muse_reads_the_question_and_fills_a_missing_organism(self):
        reply = json.dumps({"goal": "find_related_gene", "target_organism": "Drosophila melanogaster",
                            "exclude_organism": None, "unclear": []})
        with mock.patch("app.model_client.chat_completion", return_value=_reply(reply)):
            intent = agent.get_intent("Does a fruit fly have anything like this?", user_id=self.user["id"])
        self.assertEqual(intent["source"], "muse")
        self.assertEqual(intent["goal"], "find_related_gene")
        self.assertEqual(intent["target_organism"], "Drosophila melanogaster")

    def test_rules_organism_wins_over_muse(self):
        reply = json.dumps({"goal": "find_related_gene", "target_organism": "Caenorhabditis",
                            "exclude_organism": None, "unclear": []})
        with mock.patch("app.model_client.chat_completion", return_value=_reply(reply)):
            intent = agent.get_intent("Is there a related gene in nematodes?", user_id=self.user["id"])
        self.assertEqual(intent["target_organism"], "nematodes")

    def test_bad_json_or_bad_fields_fall_back_to_rules(self):
        for reply in ("not json", json.dumps({"goal": "pick_tblastn"}),
                      '```json\n{"goal": "identify_sequence", "target_organism": "<script>"}\n```'):
            with mock.patch("app.model_client.chat_completion", return_value=_reply(reply)):
                intent = agent.get_intent("Identify this protein", user_id=self.user["id"])
            if intent["source"] == "muse":  # fenced JSON is fine; the bad organism is dropped
                self.assertIsNone(intent["target_organism"])
            else:
                self.assertEqual(intent["goal"], "identify_sequence")

    def test_no_key_means_no_call(self):
        other = db.create_user("nokey", auth.hash_password("pw"))
        with mock.patch("app.model_client.chat_completion") as chat:
            intent = agent.get_intent("Identify this protein", user_id=other["id"])
        chat.assert_not_called()
        self.assertEqual(intent["source"], "rules")


class TestSummary(Base):
    def test_grounded_muse_summary_is_used_and_logged(self):
        intent = json.dumps({"goal": "identify_sequence", "target_organism": None,
                             "exclude_organism": None, "unclear": []})
        summary = ("This is most likely hemoglobin subunit beta: the top hit P68873 has E-value "
                   "6.55889e-106 with 100% identity, and reciprocal verification confirmed it.")
        with mock.patch("app.model_client.chat_completion",
                        side_effect=[_reply(intent), _reply(summary)]):
            final = self._run("Identify this protein")
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["summary"], summary)
        steps = {s["step"]: s for s in db.get_step_log(final["id"])}
        self.assertIn("intent", steps)
        self.assertIn("Muse Spark wrote the summary", steps["summarise"]["reason"])
        self.assertEqual({c["kind"] for c in db.list_model_calls()}, {"intent", "summary"})

    def test_invented_number_keeps_the_code_summary(self):
        intent = json.dumps({"goal": "identify_sequence", "target_organism": None,
                             "exclude_organism": None, "unclear": []})
        bad = "The top hit has E-value 1e-40 and 87% identity."
        with mock.patch("app.model_client.chat_completion", side_effect=[_reply(intent), _reply(bad)]):
            final = self._run("Identify this protein")
        self.assertNotEqual(final["summary"], bad)
        self.assertIn("P68873", final["summary"])
        errors = [c["error"] for c in db.list_model_calls() if c["error"]]
        self.assertTrue(any("not in the stored results" in e for e in errors))

    def test_model_down_keeps_the_workflow_running(self):
        from app.model_client import ModelError

        with mock.patch("app.model_client.chat_completion", side_effect=ModelError("timeout")):
            final = self._run("Identify this protein")
        self.assertEqual(final["status"], "done")
        self.assertIn("P68873", final["summary"])


class TestAskGuard(Base):
    def test_ask_source_and_number_guard(self):
        final = self._run("Identify this protein", user_id=db.create_user("plain", auth.hash_password("pw"))["id"])
        searches = db.get_searches(final["id"])
        kw = dict(job=db.get_job(final["id"]), searches=searches, user_id=self.user["id"],
                  muse_api_key="test-key")
        with mock.patch("app.model_client.chat_completion",
                        return_value=_reply("The top hit P68873 has E-value 6.55889e-106.")):
            good = agent.answer_followup_detailed(question="How strong is the top hit?", **kw)
        self.assertEqual(good["source"], "muse")
        with mock.patch("app.model_client.chat_completion",
                        return_value=_reply("The E-value is 3e-12, so it is moderate.")):
            bad = agent.answer_followup_detailed(question="Is it significant?", **kw)
        self.assertEqual(bad["source"], "stored")
        self.assertNotIn("3e-12", bad["answer"])

    def test_numbers_grounded_rules(self):
        facts = "hit P68873 (Pan troglodytes): E 6.55889e-106, id 100.0%, cov 100.0%"
        self.assertTrue(agent.numbers_grounded("E-value 6.56e-106, identity 100%, two hits", facts))
        self.assertTrue(agent.numbers_grounded("Job WG-89AE and P68873 match", facts))
        self.assertFalse(agent.numbers_grounded("identity 92%", facts))


if __name__ == "__main__":
    unittest.main()
