"""Multi-workflow tests: short-query profile (Lab 04), fan-out, parallel
jobs, per-search storage, grounded Q&A, WhatsApp payloads, web API.

All searches run on the Fixture backend; no network, no BLAST+.
Run: cd backend && .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import agent, chat, config, db, worker  # noqa: E402
from app.agent_loop import process_job  # noqa: E402
from app.blast_params import parameters_for  # noqa: E402
from app.intent import parse_intent as parse_intent_local  # noqa: E402
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


class _StuckNcbi(Fixture):
    """Reports as the NCBI backend and waits in submit until released."""

    name = "ncbi"

    def __init__(self) -> None:
        super().__init__(primary_hits=_hits())
        self.release = threading.Event()

    def submit(self, **kw) -> str:
        self.release.wait(timeout=30)
        return super().submit(**kw)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        config.DATABASE_PATH = Path(self._tmp.name) / "test.db"
        # Plain-http test client: keep a split-hosting backend/.env from
        # forcing a Secure session cookie the client never sends back.
        self._old_cookie = config.COOKIE_SAMESITE, config.COOKIE_SECURE
        config.COOKIE_SAMESITE, config.COOKIE_SECURE = "lax", False
        db.init_db()

    def tearDown(self) -> None:
        config.COOKIE_SAMESITE, config.COOKIE_SECURE = self._old_cookie
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

    def test_requested_database_overrides_rules_database(self):
        plan = plan_programs(intent={}, detected_type="protein", mode="auto",
                             requested_database="pdbaa")
        self.assertEqual(plan[0]["program"], "blastp")
        self.assertEqual(plan[0]["database"], "pdbaa")
        self.assertIn("pdbaa", plan[0]["reason"])

    def test_requested_database_adapts_auto_program(self):
        plan = plan_programs(intent={}, detected_type="dna", mode="auto",
                             requested_database="16s_rrna")
        self.assertEqual(plan[0]["program"], "blastn")
        self.assertEqual(plan[0]["database"], "16s_rrna")

    def test_requested_database_type_mismatch_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            plan_programs(intent={}, detected_type="protein", mode="single",
                          requested_program="blastp", requested_database="16s_rrna")
        self.assertIn("nucleotide", str(ctx.exception))

    def test_requested_database_cross_type_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            plan_programs(intent={}, detected_type="protein", mode="auto",
                          requested_database="mito_genomic")
        self.assertIn("tblastn", str(ctx.exception))

    def test_requested_database_drops_unappliable_organism_filter(self):
        intent = {"target_organism": "nematodes", "goal": "find_related_gene",
                  "raw_question": "globin gene in nematodes"}
        plan = plan_programs(intent=intent, detected_type="protein", mode="auto",
                             requested_database="pdbaa")
        self.assertIsNone(plan[0]["organism_filter"])
        self.assertIn("not applied", plan[0]["reason"])

    def test_requested_swissprot_keeps_organism_filter(self):
        intent = {"target_organism": "nematodes", "goal": "identify_sequence",
                  "raw_question": "what is this"}
        plan = plan_programs(intent=intent, detected_type="protein", mode="auto",
                             requested_database="swissprot")
        self.assertEqual(plan[0]["organism_filter"], "nematodes")

    def test_requested_database_unknown_rejected(self):
        with self.assertRaises(ValueError):
            plan_programs(intent={}, detected_type="protein", mode="auto",
                          requested_database="nr_huge")

    def test_requested_database_all_mode_rejected(self):
        with self.assertRaises(ValueError):
            plan_programs(intent={}, detected_type="protein", mode="all",
                          requested_database="pdbaa")


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

    def test_stuck_ncbi_workflow_does_not_hold_a_local_slot(self):
        old_max = config.MAX_CONCURRENT_JOBS
        old_pools = worker._executor, worker._ncbi_executor
        config.MAX_CONCURRENT_JOBS = 1  # one local slot: holding it would block
        worker._executor = worker._ncbi_executor = None
        ncbi = _StuckNcbi()
        try:
            stuck = db.create_job(question="q", raw_input=SHORT_QUERY, source="web")
            local = db.create_job(question="q", raw_input=SHORT_QUERY, source="web")
            self.assertTrue(worker.submit_async(stuck, ncbi))
            self.assertTrue(worker.submit_async(local, _backend()))
            deadline = time.time() + 10
            while time.time() < deadline:
                if (db.get_job(local["id"]) or {}).get("status") == "done":
                    break
                time.sleep(0.05)
            self.assertEqual((db.get_job(local["id"]) or {}).get("status"), "done")
            self.assertEqual((db.get_job(stuck["id"]) or {}).get("status"), "running")
        finally:
            ncbi.release.set()
            for pool in (worker._executor, worker._ncbi_executor):
                if pool is not None:
                    pool.shutdown(wait=True)
            worker._executor, worker._ncbi_executor = old_pools
            config.MAX_CONCURRENT_JOBS = old_max
        self.assertEqual((db.get_job(stuck["id"]) or {}).get("status"), "done")

    def test_unbuildable_backend_fails_instead_of_staying_queued(self):
        old_email = config.NCBI_EMAIL
        config.NCBI_EMAIL = ""  # NcbiRemote refuses to start without it
        try:
            job = db.create_job(question="q", raw_input=SHORT_QUERY, source="web",
                                backend_choice="ncbi")
            self.assertFalse(worker.submit_async(job))
        finally:
            config.NCBI_EMAIL = old_email
        final = db.get_job(job["id"]) or {}
        self.assertEqual(final.get("status"), "failed")
        self.assertIn("NCBI_EMAIL", final.get("error") or "")

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


class TestCharterCases(Base):
    """Owner charter cases from real lab work (Lab 04 Q3 neuroglobin)."""

    def test_neuroglobin_moss_hits_at_e10ish_are_not_significant(self):
        from app.classify import classify_hit

        for evalue in (9.9, 12.0, 18.0):
            self.assertEqual(classify_hit(evalue, 88.0), "not_significant")

    def test_raised_threshold_hits_never_become_a_claim(self):
        sequence = "MVHLTPEEKSAV" * 13  # ~156 aa neuroglobin-like query
        hits = [{
            "accession": "XP_001764902", "organism": "Physcomitrella patens",
            "annotation": "predicted protein", "identity": 27.0,
            "query_start": 1, "query_end": 138, "alignment_length": 138,
            "subject_length": 150, "bit_score": 45.0, "evalue": 12.0,
            "sequence": "MVHLTP",
        }]
        backend = Fixture(primary_hits=hits, reciprocal_hits={})
        job = db.create_job(question="Do mosses have globins?", raw_input=sequence,
                            whatsapp_user_id="u1", source="web", workflow_mode="auto")
        final = process_job(job, backend)
        self.assertEqual(final["hits"][0]["classification"], "not_significant")
        self.assertEqual(final["outcome"], "not_confirmed")
        searches = db.get_searches(final["id"])
        self.assertEqual(searches[0]["hits"][0]["evalue"], 12.0)


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


def _login(client) -> None:
    """Seed credentials are set before TestClient starts (lifespan seeds)."""
    resp = client.post("/auth/login", json={"username": "reviewer", "password": "test-password"})
    assert resp.status_code == 200, resp.text


class TestWebApi(Base):
    def test_submit_ask_and_cancel(self):
        from fastapi.testclient import TestClient

        from app.main import app

        old_backend, old_case = config.SEARCH_BACKEND, config.FIXTURE_CASE
        old_user, old_pw = config.AUTH_USERNAME, config.AUTH_PASSWORD
        config.SEARCH_BACKEND, config.FIXTURE_CASE = "fixture", ""
        config.AUTH_USERNAME, config.AUTH_PASSWORD = "reviewer", "test-password"
        try:
            with TestClient(app) as client:
                _login(client)
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
            config.AUTH_USERNAME, config.AUTH_PASSWORD = old_user, old_pw


if __name__ == "__main__":
    unittest.main()


class TestAccessionSubrange(Base):
    """Lab 04 Q2: RBP4 CDS slice NM_006744.4 bases 84-689."""

    def test_parse_accession_query(self):
        from app.validate import parse_accession_query

        self.assertEqual(parse_accession_query("NM_006744.4:84-689"),
                         ("NM_006744.4", (84, 689)))
        self.assertEqual(parse_accession_query("NP_000509"), ("NP_000509", None))

    def test_workflow_searches_only_the_cds_slice(self):
        full = "C" * 83 + "ATGAAA" + "ACGT" * 150 + "TAA"  # 692 bases
        backend = Fixture(
            sequences={"NM_006744.4": {"accession": "NM_006744.4", "organism": "Homo sapiens",
                                       "annotation": "retinol binding protein 4", "sequence": full}},
            primary_hits=[], reciprocal_hits={})
        job = db.create_job(question="Identify this coding sequence",
                            raw_input="NM_006744.4:84-689", source="web")
        final = process_job(job, backend)
        self.assertEqual(final["query_length"], 606)  # 689-84+1
        self.assertTrue(final["sequence"].startswith("ATGAAA"))
        self.assertEqual(final["parameters"]["subrange"],
                         {"accession": "NM_006744.4", "start": 84, "end": 689})
        steps = [s["step"] for s in db.get_step_log(final["id"])]
        self.assertIn("fetch_accession", steps)


class TestHIVExclusion(Base):
    """Lab 04 Q4: HIV-1 pol excluding HIV-1, both backends + taxa flag."""

    def test_intent_extracts_hiv1_exclusion(self):
        intent = parse_intent_local("Is HIV-1 pol closer to HIV-2 or SIV, excluding HIV-1?")
        self.assertEqual(intent["exclude_organism"], "Human immunodeficiency virus 1")

    def test_entrez_query_builds_not_exclusion(self):
        from app.search_backend import build_entrez_query

        self.assertEqual(build_entrez_query(None, "Human immunodeficiency virus 1"),
                         'NOT "Human immunodeficiency virus 1"[Organism]')
        self.assertEqual(build_entrez_query("nematodes", None), '"nematodes"[Organism]')
        self.assertEqual(build_entrez_query("viruses", "Human immunodeficiency virus 1"),
                         '"viruses"[Organism] NOT "Human immunodeficiency virus 1"[Organism]')
        self.assertIsNone(build_entrez_query(None, None))

    def test_local_filter_excludes_taxon(self):
        from app.search_backend import select_seqids_filtered

        taxid_map = "sp|P1|HIV1\t11676\nsp|P2|ECOLI\t562\nsp|P3|HUMAN\t9606\n"
        self.assertEqual(select_seqids_filtered(taxid_map, None, {11676}),
                         ["sp|P2|ECOLI", "sp|P3|HUMAN"])
        self.assertEqual(select_seqids_filtered(taxid_map, {9606}, {11676}), ["sp|P3|HUMAN"])

    def test_taxa_flag_marks_bacterial_hit_only(self):
        from app.classify import flag_unexpected_taxa

        hits = [
            {"accession": "HIV2POL", "organism": "Human immunodeficiency virus 2", "annotation": "pol protein"},
            {"accession": "SIVPOL", "organism": "Simian immunodeficiency virus", "annotation": "pol protein"},
            {"accession": "ECTNP", "organism": "Escherichia coli", "annotation": "transposase"},
        ]
        flagged = flag_unexpected_taxa(hits, query_organism="Human immunodeficiency virus 1",
                                       query_annotation="Gag-Pol polyprotein")
        self.assertIsNone(flagged[0]["taxa_flag"])
        self.assertIsNone(flagged[1]["taxa_flag"])
        self.assertEqual(flagged[2]["taxa_flag"], "unexpected_taxa")

    def test_workflow_stores_exclusion_and_flags(self):
        sequence = "MVHLTPEEKSAV" * 120  # long viral-like protein query
        hits = [
            {"accession": "HIV2POL", "organism": "Human immunodeficiency virus 2",
             "annotation": "pol protein", "identity": 55.0, "query_start": 1, "query_end": 1400,
             "alignment_length": 1400, "subject_length": 1450, "bit_score": 900.0,
             "evalue": 0.0, "sequence": "MVHLTP"},
            {"accession": "ECTNP", "organism": "Escherichia coli", "annotation": "transposase",
             "identity": 30.0, "query_start": 10, "query_end": 400, "alignment_length": 390,
             "subject_length": 420, "bit_score": 120.0, "evalue": 1e-20, "sequence": "MVHLTP"},
        ]
        backend = Fixture(
            sequences={"NP_057849": {"accession": "NP_057849.4", "organism": "Human immunodeficiency virus 1",
                                     "annotation": "Gag-Pol polyprotein", "sequence": sequence}},
            primary_hits=hits, reciprocal_hits={})
        job = db.create_job(question="Is HIV-1 pol closer to HIV-2 or SIV, excluding HIV-1?",
                            raw_input="NP_057849", source="web", workflow_mode="auto")
        final = process_job(job, backend)
        searches = db.get_searches(final["id"])
        self.assertEqual(searches[0]["parameters"]["exclude_organism"],
                         "Human immunodeficiency virus 1")
        by_acc = {h["accession"]: h for h in final["hits"]}
        self.assertIsNone(by_acc["HIV2POL"]["taxa_flag"])
        self.assertEqual(by_acc["ECTNP"]["taxa_flag"], "unexpected_taxa")
        self.assertIn("flagged unexpected taxa", final["summary"])


class TestMsaTree(Base):
    """Tier 2: MSA (Lab 06) -> NJ tree, Poisson + complete deletion (Lab 07)."""

    def test_complete_deletion_drops_gap_columns(self):
        from app.msa import complete_deletion

        records = [{"label": "a", "sequence": "ACGT"}, {"label": "b", "sequence": "A-GT"}]
        cleaned = complete_deletion(records)
        self.assertEqual([r["sequence"] for r in cleaned], ["AGT", "AGT"])

    def test_poisson_distance(self):
        from app.msa import poisson_distance

        self.assertEqual(poisson_distance("AAAA", "AAAA"), 0.0)
        self.assertAlmostEqual(poisson_distance("AAAA", "AATT"), 0.6931, places=3)

    def test_tree_needs_three_sequences(self):
        from app.msa import MsaError, build_tree_newick

        with self.assertRaises(MsaError):
            build_tree_newick([{"label": "a", "sequence": "AAAA"},
                               {"label": "b", "sequence": "AAAT"}])

    def test_workflow_continues_into_alignment_and_tree(self):
        from app.msa import FixtureMsa, run_alignment

        hits = [
            {"accession": "HIT1", "organism": "C. elegans", "annotation": "globin-like protein",
             "identity": 60.0, "query_start": 1, "query_end": 12, "alignment_length": 12,
             "subject_length": 14, "bit_score": 40.0, "evalue": 1e-12, "sequence": SHORT_QUERY},
            {"accession": "HIT2", "organism": "C. briggsae", "annotation": "globin-like protein",
             "identity": 55.0, "query_start": 1, "query_end": 12, "alignment_length": 12,
             "subject_length": 14, "bit_score": 38.0, "evalue": 1e-11, "sequence": "PNLHGLFGRKTA"},
        ]
        backend = Fixture(primary_hits=hits, reciprocal_hits={
            "HIT1": [{"accession": "RECIP1", "evalue": 1e-10, "annotation": "globin",
                      "query_start": 1, "query_end": 12, "subject_length": 14}]})
        job = db.create_job(question="Identify this protein", raw_input=SHORT_QUERY,
                            whatsapp_user_id="u1", source="web", workflow_mode="auto")
        final = process_job(job, backend)
        self.assertEqual(final["outcome"], "confirmed")
        aligned = run_alignment(job=final, search_backend=backend, msa_backend=FixtureMsa())
        self.assertIn("HIT1", aligned["msa_alignment"])
        self.assertIn("HIT2", aligned["tree_newick"])
        steps = [s["step"] for s in db.get_step_log(final["id"])]
        self.assertIn("align", steps)
        self.assertIn("tree", steps)


class TestResearchMemory(Base):
    """Related earlier workflows were removed from results (owner, 2 Nov).

    The store helper, the API field, and the results-page section are gone;
    repeat runs of the same sequence still complete as independent jobs.
    """

    def _run_globin(self, backend) -> dict:
        job = db.create_job(question="Identify this protein", raw_input=SHORT_QUERY,
                            whatsapp_user_id="mem", source="web", workflow_mode="auto")
        return process_job(job, backend)

    def test_repeat_run_completes_without_related_linking(self):
        self._run_globin(_backend())
        second = self._run_globin(_backend())
        self.assertEqual(second["status"], "done")
        self.assertFalse(hasattr(db, "related_jobs"))

    def test_public_job_has_no_related_jobs_field(self):
        from app.main import _public_job

        job = self._run_globin(_backend())
        self.assertNotIn("related_jobs", _public_job(job))


class TestBackendChoice(Base):
    """Per-workflow backend switch: local server vs real NCBI API."""

    def test_normalize_and_pacing_helpers(self):
        from app.search_backend import (SearchError, ncbi_submit_wait_seconds,
                                        normalize_backend_choice)

        self.assertEqual(normalize_backend_choice(None), "server")
        self.assertEqual(normalize_backend_choice("NCBI"), "ncbi")
        self.assertEqual(normalize_backend_choice("default"), "server")
        with self.assertRaises(SearchError):
            normalize_backend_choice("bogus")
        self.assertEqual(ncbi_submit_wait_seconds(last_submit_at=None, now=100.0), 0.0)
        self.assertEqual(ncbi_submit_wait_seconds(last_submit_at=100.0, now=104.0), 6.0)
        self.assertEqual(ncbi_submit_wait_seconds(last_submit_at=100.0, now=115.0), 0.0)

    def test_server_choice_keeps_configured_fixture(self):
        from app import worker

        job = db.create_job(question="q", raw_input=SHORT_QUERY, source="web")
        self.assertEqual(job["backend_choice"], "server")
        old = config.SEARCH_BACKEND
        config.SEARCH_BACKEND = "fixture"
        try:
            self.assertEqual(worker.backend_for_job(job).name, "fixture")
        finally:
            config.SEARCH_BACKEND = old

    def test_choice_is_stored_on_the_job(self):
        job = db.create_job(question="q", raw_input=SHORT_QUERY, source="web",
                            backend_choice="ncbi")
        self.assertEqual(job["backend_choice"], "ncbi")
        self.assertEqual((db.get_job(job["id"]) or {})["backend_choice"], "ncbi")

    def test_api_stores_user_backend_choice(self):
        from fastapi.testclient import TestClient

        from app.main import app

        old_backend = config.SEARCH_BACKEND
        old_user, old_pw = config.AUTH_USERNAME, config.AUTH_PASSWORD
        config.SEARCH_BACKEND = "fixture"
        config.AUTH_USERNAME, config.AUTH_PASSWORD = "reviewer", "test-password"
        try:
            with TestClient(app) as client:
                _login(client)
                created = client.post("/jobs", json={
                    "sequence": SHORT_QUERY, "question": "parameters?",
                    "workflow_mode": "single", "program": "blastp",
                    "search_backend": "server"})
                self.assertEqual(created.status_code, 201)
                self.assertEqual(created.json()["backend_choice"], "server")
        finally:
            config.SEARCH_BACKEND = old_backend
            config.AUTH_USERNAME, config.AUTH_PASSWORD = old_user, old_pw
