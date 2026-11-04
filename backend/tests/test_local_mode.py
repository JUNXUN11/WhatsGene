"""Local-mode honesty: real database names, NCBI accession fallback,
web data notices, failed-search answers, and local MAFFT (verification
round, 4 Nov 2026).

No network and no BLAST+: a Fixture backend reports as "local", and a
fake mafft script stands in for MAFFT.
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import agent_loop, config, db, msa, qa  # noqa: E402
from app.agent_loop import process_job  # noqa: E402
from app.search_backend import Fixture, SearchError, local_database_name  # noqa: E402

QUERY = "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLSTPDAVMGNPKVKAHGKKVLGAFSDGLAHLDNLKGTFATLSELHCDKLHVDPENFRLLGNVLVCVLAHHFGKEFTPPVQAAYQKVVAGVANALAHKYH"


def _hits() -> list[dict]:
    return [{"accession": "P68873", "organism": "Pan troglodytes", "annotation": "Hemoglobin subunit beta",
             "identity": 100.0, "query_start": 1, "query_end": len(QUERY), "alignment_length": len(QUERY),
             "subject_length": len(QUERY), "bit_score": 300.0, "evalue": 1e-100, "sequence": QUERY}]


class _LocalFixture(Fixture):
    """Reports as LocalBlast; knows no accession, like an empty local copy."""

    name = "local"

    def __init__(self) -> None:
        super().__init__(primary_hits=_hits(), reciprocal_hits={
            "P68873": [{"accession": "P68871", "evalue": 1e-100, "annotation": "Hemoglobin subunit beta",
                        "query_start": 1, "query_end": len(QUERY), "subject_length": len(QUERY)}]})

    def fetch_by_accession(self, accession: str) -> dict:
        raise SearchError(f"Accession {accession} not found in the local databases.")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old = config.DATABASE_PATH, config.NCBI_EMAIL
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        db.init_db()

    def tearDown(self) -> None:
        config.DATABASE_PATH, config.NCBI_EMAIL = self._old
        self._tmp.cleanup()

    def _run(self, raw: str, backend=None) -> dict:
        job = db.create_job(question="Identify this protein", raw_input=raw, source="web", workflow_mode="auto")
        return process_job(job, backend or _LocalFixture())


class TestAccessionFormats(unittest.TestCase):
    def test_uniprot_accessions_with_mixed_letters_and_digits(self):
        from app.validate import looks_like_accession, parse_accession_query

        for acc in ("P0DTC2", "A0A023GPI8", "Q6GZX4", "P68871", "NP_000509.1", "NR_102783.2"):
            self.assertTrue(looks_like_accession(acc), acc)
        for raw in ("PNLHGLFGRKTG", "MVHLTPEEKSAV", "ACGTACGTACGT"):
            self.assertFalse(looks_like_accession(raw), raw)
        self.assertEqual(parse_accession_query("p0dtc2"), ("P0DTC2", None))


class TestHeaderlessFasta(unittest.TestCase):
    def test_fasta_pasted_without_its_marker(self):
        from app.validate import detect_type, normalise_sequence

        raw = ("P01308 Insulin OS=Homo sapiens OX=9606 GN=INS PE=1 SV=1\n"
               "MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVEALYLVCGERGFFYTPKTRREAEDLQVGQVELGGGPGAGSLQPL\n"
               "ALEGSLQKRGIVEQCCTSICSLYQLENYCN")
        seq, header = normalise_sequence(raw)
        self.assertEqual(header, "P01308 Insulin OS=Homo sapiens OX=9606 GN=INS PE=1 SV=1")
        self.assertEqual(len(seq), 110)
        self.assertEqual(detect_type(seq), "protein")

    def test_plain_multiline_sequence_is_not_a_header(self):
        from app.validate import normalise_sequence

        seq, header = normalise_sequence("MVHLTPEEKSAVTALWGK\nVNVDEVGGEALGRLLVVY")
        self.assertIsNone(header)
        self.assertEqual(seq, "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVY")


class TestRecordedDatabase(Base):
    def test_local_records_the_database_actually_searched(self):
        self.assertEqual(local_database_name("refseq_protein"), "swissprot")
        self.assertEqual(local_database_name("est"), "est")
        final = self._run(QUERY)
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["database"], "swissprot")
        self.assertTrue(all(s["database"] == "swissprot" for s in db.get_searches(final["id"])))
        self.assertIn("swissprot", final["summary"])
        self.assertIn("database_local", [s["step"] for s in db.get_step_log(final["id"])])

    def test_other_backends_keep_the_rules_engine_name(self):
        final = self._run(QUERY, backend=Fixture(primary_hits=_hits()))
        self.assertEqual(final["database"], "refseq_protein")


class TestNcbiAccessionFallback(Base):
    def test_missing_accession_is_fetched_from_ncbi(self):
        config.NCBI_EMAIL = "lab@example.org"
        record = {"accession": "NP_000509.1", "sequence": QUERY, "organism": "",
                  "annotation": "hemoglobin subunit beta [Homo sapiens]"}
        with mock.patch.object(agent_loop.NcbiRemote, "fetch_by_accession", return_value=record) as fetch:
            final = self._run("NP_000509")
        fetch.assert_called_once_with("NP_000509")
        self.assertEqual(final["status"], "done")
        decisions = [s["decision"] for s in db.get_step_log(final["id"]) if s["step"] == "fetch_accession"]
        self.assertIn("fetch the sequence from NCBI E-utilities", decisions)

        from app.main import _public_job

        notice = _public_job(final)["data_notice"]
        self.assertIn("accession ID was sent to NCBI only", notice)
        self.assertNotIn("forget my history", notice)

    def test_no_email_fails_with_a_plain_hint(self):
        config.NCBI_EMAIL = ""
        final = self._run("NP_000509")
        self.assertEqual(final["status"], "failed")
        self.assertIn("NCBI_EMAIL", final["error"])

    def test_ncbi_backend_never_double_fetches(self):
        backend = Fixture(primary_hits=_hits())  # name "fixture": no fallback
        with mock.patch.object(agent_loop.NcbiRemote, "fetch_by_accession") as fetch:
            final = self._run("NOPE_123", backend=backend)
        fetch.assert_not_called()
        self.assertEqual(final["status"], "failed")


class TestDataNotice(Base):
    def test_web_and_whatsapp_notices(self):
        from app.main import _public_job

        web = self._run(QUERY)
        self.assertIn("nothing was sent to NCBI", _public_job(web)["data_notice"])
        self.assertIn("delete it from its page", _public_job(web)["data_notice"])
        wa = db.create_job(question="q", raw_input=QUERY, source="whatsapp", whatsapp_user_id="u1")
        self.assertIn("on WhatsApp", _public_job(wa)["data_notice"])


class TestCompareQuotesFailures(Base):
    def test_failed_program_quotes_its_reason(self):
        job = db.create_job(question="q", raw_input=QUERY, source="web", workflow_mode="all")
        ok = db.create_search(job["id"], kind="primary", program="blastp", database="swissprot",
                              parameters={}, rid="R1")
        db.complete_search(ok, hits=[{**_hits()[0], "query_coverage": 100.0, "classification": "strong"}],
                           status="done")
        bad = db.create_search(job["id"], kind="primary", program="tblastn", database="est",
                               parameters={}, rid=None)
        db.complete_search(bad, hits=[], status="failed", error="LocalBlast does not serve database 'est'")
        answer = qa.answer_question(job=db.get_job(job["id"]), question="Compare the programs",
                           searches=db.get_searches(job["id"]))
        self.assertIn("tblastn: search failed (LocalBlast does not serve database 'est')", answer)


class TestLocalMafft(Base):
    def _fake_mafft(self) -> Path:
        script = Path(self._tmp.name) / "mafft"
        script.write_text("#!/bin/sh\n# fake mafft: echo the input FASTA (last argument)\n"
                          "for last; do :; done\ncat \"$last\"\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script

    def test_local_mafft_aligns_and_is_preferred(self):
        script = self._fake_mafft()
        out = msa.LocalMafft(str(script)).align([{"label": "A", "sequence": "MKV"}, {"label": "B", "sequence": "MKI"}])
        self.assertIn(">A\nMKV", out)
        with mock.patch.dict(os.environ, {"PATH": f"{script.parent}{os.pathsep}{os.environ['PATH']}"}):
            self.assertEqual(msa.get_msa_backend().name, "local-mafft")

    def test_ebi_when_mafft_missing(self):
        config.NCBI_EMAIL = "lab@example.org"
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(msa.get_msa_backend().name, "ebi-mafft")



class _TimeoutReciprocal(Fixture):
    """The primary search works; every reciprocal poll hits the NCBI wait cap."""

    def __init__(self) -> None:
        super().__init__(primary_hits=_hits())
        self._polls = 0

    def poll(self, token: str) -> str:
        self._polls += 1
        if self._polls > 1:
            raise SearchError(f"NCBI search {token} did not finish within 30 minutes and was aborted.")
        return super().poll(token)


class TestNoStuckWorkflows(Base):
    def test_reciprocal_timeout_finishes_with_primary_hits(self):
        final = self._run(QUERY, backend=_TimeoutReciprocal())
        self.assertEqual(final["status"], "done")
        self.assertNotEqual(final["outcome"], "confirmed")
        self.assertTrue(final["hits"])
        recip = [s for s in db.get_searches(final["id"]) if s["kind"] == "reciprocal"]
        self.assertTrue(recip and recip[0]["status"] == "failed")
        self.assertIn("30 minutes", recip[0]["error"])

    def test_unexpected_error_fails_the_workflow(self):
        from app import worker

        job = db.create_job(question="q", raw_input=QUERY, source="web")
        with mock.patch.object(worker, "_run_loop", side_effect=RuntimeError("boom")):
            final = worker.run_job(job, backend=Fixture(primary_hits=_hits()))
        self.assertEqual(final["status"], "failed")
        self.assertIn("boom", db.get_job(job["id"])["error"])


if __name__ == "__main__":
    unittest.main()
