"""Search backend tests — Fixture behavior, BLAST XML parsing, pure helpers.

Every backend instance in this suite is Fixture. LocalBlast/NcbiRemote
policies are covered through their pure helpers only, so no test runs a
subprocess or touches the network. Run:

    cd backend && .venv/bin/python -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.search_backend import (  # noqa: E402
    Fixture,
    InflightGuard,
    SearchError,
    build_blast_command,
    expand_taxid,
    local_seqids_for_organism,
    map_search_status,
    ncbi_max_wait_seconds,
    ncbi_poll_interval_seconds,
    parse_blast_xml,
    parse_blastdbcmd_fasta,
    parse_names_dmp,
    parse_nodes_dmp,
    poll_delay_or_abort,
    resolve_blast_db_dir,
    resolve_organism_taxid,
    select_seqids,
)

SAMPLE_XML = """<?xml version="1.0"?>
<BlastOutput>
  <BlastOutput_program>blastp</BlastOutput_program>
  <BlastOutput_version>BLASTP 2.15.0+</BlastOutput_version>
  <BlastOutput_reference>test</BlastOutput_reference>
  <BlastOutput_db>refseq_protein</BlastOutput_db>
  <BlastOutput_query-ID>Query_1</BlastOutput_query-ID>
  <BlastOutput_query-def>query</BlastOutput_query-def>
  <BlastOutput_query-len>100</BlastOutput_query-len>
  <BlastOutput_param><Parameters>
    <Parameters_matrix>BLOSUM62</Parameters_matrix>
    <Parameters_expect>0.01</Parameters_expect>
    <Parameters_gap-open>11</Parameters_gap-open>
    <Parameters_gap-extend>1</Parameters_gap-extend>
    <Parameters_filter></Parameters_filter>
  </Parameters></BlastOutput_param>
  <BlastOutput_iterations><Iteration>
    <Iteration_iter-num>1</Iteration_iter-num>
    <Iteration_query-ID>Query_1</Iteration_query-ID>
    <Iteration_query-def>query</Iteration_query-def>
    <Iteration_query-len>100</Iteration_query-len>
    <Iteration_hits><Hit>
      <Hit_num>1</Hit_num>
      <Hit_id>ref|NP_TEST.1|</Hit_id>
      <Hit_def>globin family protein [Caenorhabditis elegans]</Hit_def>
      <Hit_accession>NP_TEST.1</Hit_accession>
      <Hit_len>120</Hit_len>
      <Hit_hsps><Hsp>
        <Hsp_num>1</Hsp_num>
        <Hsp_bit-score>150.5</Hsp_bit-score>
        <Hsp_score>390</Hsp_score>
        <Hsp_evalue>1e-20</Hsp_evalue>
        <Hsp_query-from>1</Hsp_query-from>
        <Hsp_query-to>90</Hsp_query-to>
        <Hsp_hit-from>5</Hsp_hit-from>
        <Hsp_hit-to>94</Hsp_hit-to>
        <Hsp_identity>81</Hsp_identity>
        <Hsp_positive>85</Hsp_positive>
        <Hsp_gaps>0</Hsp_gaps>
        <Hsp_align-len>90</Hsp_align-len>
        <Hsp_qseq>AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA</Hsp_qseq>
        <Hsp_hseq>AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA</Hsp_hseq>
        <Hsp_midline>AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA</Hsp_midline>
      </Hsp></Hit_hsps>
    </Hit></Iteration_hits>
    <Iteration_stat><Statistics>
      <Statistics_db-num>1000</Statistics_db-num>
      <Statistics_db-len>100000</Statistics_db-len>
      <Statistics_hsp-len>0</Statistics_hsp-len>
      <Statistics_eff-space>1000000</Statistics_eff-space>
      <Statistics_kappa>0.041</Statistics_kappa>
      <Statistics_lambda>0.267</Statistics_lambda>
      <Statistics_entropy>0.14</Statistics_entropy>
    </Statistics></Iteration_stat>
  </Iteration></BlastOutput_iterations>
</BlastOutput>
"""


class TestParse(unittest.TestCase):
    def test_parse_hit_fields(self):
        hits = parse_blast_xml(SAMPLE_XML)
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit["accession"], "NP_TEST.1")
        self.assertEqual(hit["organism"], "Caenorhabditis elegans")
        self.assertAlmostEqual(hit["identity"], 90.0)
        self.assertEqual((hit["query_start"], hit["query_end"]), (1, 90))
        self.assertEqual(hit["evalue"], 1e-20)

    def test_parse_swissprot_os_organism(self):
        xml = SAMPLE_XML.replace(
            "globin family protein [Caenorhabditis elegans]",
            "Hemoglobin subunit beta OS=Homo sapiens OX=9606 GN=HBB")
        hits = parse_blast_xml(xml)
        self.assertEqual(hits[0]["organism"], "Homo sapiens")


class TestFixtureFiles(unittest.TestCase):
    def test_load_case_round_trip(self):
        backend = Fixture("globin_nematode")
        record = backend.fetch_by_accession("NP_000509")
        self.assertTrue(record["sequence"])
        rid = backend.submit(sequence=record["sequence"], program="tblastn",
                             database="est", parameters={})
        self.assertEqual(backend.poll(rid), "ready")
        hits = backend.fetch_results(rid)
        self.assertTrue(hits)
        self.assertIn("query_start", hits[0])

    def test_reciprocal_routing_from_file(self):
        backend = Fixture("globin_nematode.json")  # extension accepted
        rid = backend.submit(sequence="MVHLTP", program="blastp",
                             database="refseq_protein",
                             parameters={"kind": "reciprocal",
                                         "candidate_accession": "EST_NEMATODE_GLOBIN_1"})
        reciprocal = backend.fetch_results(rid)
        self.assertTrue(reciprocal)

    def test_explicit_data_overrides_file(self):
        backend = Fixture("globin_nematode", primary_hits=[])
        rid = backend.submit(sequence="MVHLTP", program="blastp",
                             database="refseq_protein", parameters={})
        self.assertEqual(backend.fetch_results(rid), [])

    def test_unknown_case_lists_available(self):
        with self.assertRaises(SearchError) as ctx:
            Fixture("no_such_case")
        self.assertIn("globin_nematode", str(ctx.exception))

    def test_path_traversal_rejected(self):
        with self.assertRaises(SearchError):
            Fixture("../secret")

    def test_missing_accession_fails_loudly(self):
        backend = Fixture("globin_nematode")
        with self.assertRaises(SearchError):
            backend.fetch_by_accession("NP_999999")

    def test_unknown_token_is_expired(self):
        self.assertEqual(Fixture().poll("NOPE"), "expired")


class TestStatusMap(unittest.TestCase):
    def test_ready(self):
        self.assertEqual(map_search_status("Status=READY"), "ready")

    def test_failed(self):
        self.assertEqual(map_search_status("Status=FAILED"), "failed")

    def test_unknown_is_expired(self):
        self.assertEqual(map_search_status("Status=UNKNOWN"), "expired")

    def test_anything_else_is_waiting(self):
        self.assertEqual(map_search_status("Status=WAITING"), "waiting")
        self.assertEqual(map_search_status("<html>queued</html>"), "waiting")


class TestNcbiPolicy(unittest.TestCase):
    def test_poll_interval_defaults_to_60(self):
        self.assertEqual(ncbi_poll_interval_seconds(), 60.0)

    def test_poll_interval_never_below_60(self):
        old = config.NCBI_POLL_INTERVAL_SECONDS
        config.NCBI_POLL_INTERVAL_SECONDS = 5.0
        try:
            self.assertEqual(ncbi_poll_interval_seconds(), 60.0)
        finally:
            config.NCBI_POLL_INTERVAL_SECONDS = old

    def test_poll_interval_honours_slower_setting(self):
        old = config.NCBI_POLL_INTERVAL_SECONDS
        config.NCBI_POLL_INTERVAL_SECONDS = 120.0
        try:
            self.assertEqual(ncbi_poll_interval_seconds(), 120.0)
        finally:
            config.NCBI_POLL_INTERVAL_SECONDS = old

    def test_max_wait_defaults_to_30_minutes(self):
        self.assertEqual(ncbi_max_wait_seconds(), 1800.0)

    def test_delay_within_budget(self):
        self.assertEqual(poll_delay_or_abort(elapsed=10.0, rid="R1"), 60.0)

    def test_abort_past_budget_is_clear(self):
        with self.assertRaises(SearchError) as ctx:
            poll_delay_or_abort(elapsed=1800.0, rid="R1")
        message = str(ctx.exception)
        self.assertIn("R1", message)
        self.assertIn("30 minutes", message)
        self.assertIn("aborted", message)

    def test_inflight_guard_single_search(self):
        guard = InflightGuard()
        guard.check_free()
        guard.acquire("RID-1")
        with self.assertRaises(SearchError) as ctx:
            guard.check_free()
        self.assertIn("RID-1", str(ctx.exception))
        with self.assertRaises(SearchError):
            guard.acquire("RID-2")
        guard.release()
        guard.check_free()
        guard.acquire("RID-2")  # free again after release


class TestLocalHelpers(unittest.TestCase):
    def test_resolve_db_dir_requires_blastdb(self):
        old = os.environ.pop("BLASTDB", None)
        try:
            with self.assertRaises(SearchError) as ctx:
                resolve_blast_db_dir()
            self.assertIn("BLASTDB is not set", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["BLASTDB"] = old

    def test_resolve_db_dir_requires_directory(self):
        old = os.environ.get("BLASTDB")
        os.environ["BLASTDB"] = "/nonexistent-dir-xyz"
        try:
            with self.assertRaises(SearchError):
                resolve_blast_db_dir()
        finally:
            if old is None:
                os.environ.pop("BLASTDB", None)
            else:
                os.environ["BLASTDB"] = old

    def test_resolve_db_dir_accepts_directory(self):
        old = os.environ.get("BLASTDB")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["BLASTDB"] = tmp
            try:
                self.assertEqual(resolve_blast_db_dir(), Path(tmp))
            finally:
                if old is None:
                    os.environ.pop("BLASTDB", None)
                else:
                    os.environ["BLASTDB"] = old

    def test_build_blastp_command(self):
        cmd = build_blast_command(
            program="blastp", db_path=Path("/db/swissprot"),
            query_fasta=Path("/tmp/q.fasta"), evalue=0.01, word_size=3,
            matrix="BLOSUM62", seqidlist_path=Path("/tmp/n.seq"))
        self.assertEqual(cmd[:7], ["blastp", "-db", "/db/swissprot", "-query",
                                  "/tmp/q.fasta", "-outfmt", "5"])
        self.assertIn("-out", cmd)
        self.assertEqual(cmd[cmd.index("-evalue") + 1], "0.01")
        self.assertEqual(cmd[cmd.index("-word_size") + 1], "3")
        self.assertEqual(cmd[cmd.index("-matrix") + 1], "BLOSUM62")
        self.assertEqual(cmd[cmd.index("-seqidlist") + 1], "/tmp/n.seq")
        # -entrez_query must never be used: BLAST+ requires -remote for it.

    def test_build_blastn_command_minimal(self):
        cmd = build_blast_command(program="blastn", db_path=Path("/db/swissprot"),
                                  query_fasta=Path("/tmp/q.fasta"))
        self.assertEqual(cmd[0], "blastn")
        self.assertNotIn("-seqidlist", cmd)
        self.assertNotIn("-entrez_query", cmd)

    def test_build_command_rejects_other_programs(self):
        with self.assertRaises(SearchError) as ctx:
            build_blast_command(program="tblastn", db_path=Path("/db/x"),
                                query_fasta=Path("/tmp/q.fasta"))
        self.assertIn("tblastn", str(ctx.exception))

    def test_parse_swissprot_defline(self):
        record = parse_blastdbcmd_fasta(
            ">sp|P68871|HBB_HUMAN Hemoglobin subunit beta OS=Homo sapiens GN=HBB\n"
            "MVHLTPEEK\nSAVTALWGK\n")
        self.assertEqual(record["accession"], "P68871")
        self.assertEqual(record["organism"], "Homo sapiens")
        self.assertEqual(record["sequence"], "MVHLTPEEKSAVTALWGK")
        self.assertIn("Hemoglobin", record["annotation"])

    def test_parse_refseq_style_defline(self):
        record = parse_blastdbcmd_fasta(
            ">NP_000509.1 hemoglobin subunit beta [Homo sapiens]\nMVHLTP\n")
        self.assertEqual(record["accession"], "NP_000509.1")
        self.assertEqual(record["organism"], "Homo sapiens")

    def test_parse_empty_output_fails_loudly(self):
        with self.assertRaises(SearchError):
            parse_blastdbcmd_fasta("")


NAMES_DMP = (
    "9606\t|\tHomo sapiens\t|\t\t|\tscientific name\t|\n"
    "9606\t|\tHuman\t|\t\t|\tcommon name\t|\n"
    "6231\t|\tNematoda\t|\t\t|\tscientific name\t|\n"
)

NODES_DMP = (
    "9606\t|\t9605\t|\n"
    "6231\t|\t33317\t|\n"
    "6238\t|\t6231\t|\n"
)

TAXID_MAP = (
    "sp|P68871|HBB_HUMAN\t9606\n"
    "sp|Q23121|FAKE_CAEEL\t6238\n"
)


class TestLocalTaxonomy(unittest.TestCase):
    def test_names_scientific_only(self):
        names = parse_names_dmp(NAMES_DMP)
        self.assertEqual(names["Homo sapiens"], 9606)
        self.assertEqual(names["Nematoda"], 6231)
        self.assertNotIn("Human", names)

    def test_resolve_exact_and_case_insensitive(self):
        names = parse_names_dmp(NAMES_DMP)
        self.assertEqual(resolve_organism_taxid("Nematoda", names), 6231)
        self.assertEqual(resolve_organism_taxid("homo sapiens", names), 9606)

    def test_resolve_unknown_fails_loudly(self):
        with self.assertRaises(SearchError) as ctx:
            resolve_organism_taxid("No Such Organism", parse_names_dmp(NAMES_DMP))
        self.assertIn("No Such Organism", str(ctx.exception))

    def test_expand_includes_descendants(self):
        children = parse_nodes_dmp(NODES_DMP)
        self.assertEqual(expand_taxid(6231, children), {6231, 6238})
        self.assertEqual(expand_taxid(9606, children), {9606})

    def test_select_seqids(self):
        self.assertEqual(select_seqids(TAXID_MAP, {9606}), ["sp|P68871|HBB_HUMAN"])
        self.assertEqual(select_seqids(TAXID_MAP, {6231, 6238}),
                         ["sp|Q23121|FAKE_CAEEL"])

    def _taxonomy_dir(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / "names.dmp").write_text(NAMES_DMP, encoding="utf-8")
        (root / "nodes.dmp").write_text(NODES_DMP, encoding="utf-8")
        (root / "sprot.taxidmap").write_text(TAXID_MAP, encoding="utf-8")
        return root

    def test_end_to_end_species(self):
        with tempfile.TemporaryDirectory() as tmp:
            seqids = local_seqids_for_organism("Homo sapiens", self._taxonomy_dir(tmp))
        self.assertEqual(seqids, ["sp|P68871|HBB_HUMAN"])

    def test_end_to_end_higher_taxon_covers_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            seqids = local_seqids_for_organism("Nematoda", self._taxonomy_dir(tmp))
        self.assertEqual(seqids, ["sp|Q23121|FAKE_CAEEL"])

    def test_missing_files_fail_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SearchError) as ctx:
                local_seqids_for_organism("Homo sapiens", Path(tmp))
            self.assertIn("names.dmp", str(ctx.exception))

    def test_organism_without_local_seqids_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._taxonomy_dir(tmp)
            (root / "sprot.taxidmap").write_text("sp|X|Y\t1\n", encoding="utf-8")
            with self.assertRaises(SearchError) as ctx:
                local_seqids_for_organism("Homo sapiens", root)
            self.assertIn("Homo sapiens", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
