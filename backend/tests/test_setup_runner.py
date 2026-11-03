"""Setup runner tests — taxid map + one tiny full run (offline, tiny files)."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import setup_runner  # noqa: E402

FASTA = (
    ">sp|P68871|HBB_HUMAN Hemoglobin subunit beta OS=Homo sapiens OX=9606 GN=HBB\n"
    "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGD\n"
    ">sp|Q9CQV8|1433B_MOUSE 14-3-3 protein OS=Mus musculus OX=10090 GN=Ywhab\n"
    "MTMDKSELVQKAKLAEQAERYDDMAAAMKAVTEQGHELSNEERNLLSV\n"
    ">tr|A0A000|XYZ_XXXX No taxon id on this record OS=Nowhere\n"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
)


class TestTaxidMap(unittest.TestCase):
    def test_derives_bare_accessions_and_skips_missing_ox(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta = Path(tmp) / "in.fasta"
            fasta.write_text(FASTA, encoding="utf-8")
            out = Path(tmp) / "map.txt"
            count = setup_runner.build_taxid_map(fasta, out)
            lines = out.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(count, 2)
        self.assertEqual(lines[0], "P68871\t9606")
        self.assertEqual(lines[1], "Q9CQV8\t10090")


class TestStateMachine(unittest.TestCase):
    def test_idle_shape(self):
        state = setup_runner.get_state()
        self.assertIn(state["status"], ("idle", "running", "done", "failed"))
        self.assertEqual([s["id"] for s in state["steps"]],
                         ["check_blast", "download", "build", "verify"])

    @unittest.skipUnless(shutil.which("makeblastdb"), "needs BLAST+ for the build step")
    def test_tiny_run_fails_at_verify_with_real_error(self):
        # Taxonomy zip missing → the run must fail loudly, not fake success.
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir(parents=True)

            def fake_fetch(url, dest, label=""):
                dest.parent.mkdir(parents=True, exist_ok=True)
                if str(dest).endswith(".fasta.gz"):
                    import gzip
                    with gzip.open(dest, "wt", encoding="utf-8") as fh:
                        fh.write(FASTA)
                else:
                    dest.write_bytes(b"not a zip")
                return None

            old = setup_runner.blastdb_dir
            setup_runner.blastdb_dir = lambda: Path(tmp)  # type: ignore[assignment]
            try:
                setup_runner._run(fetch_fn=fake_fetch)
            finally:
                setup_runner.blastdb_dir = old  # type: ignore[assignment]
            state = setup_runner.get_state()
            self.assertEqual(state["status"], "failed")
            failed = [s for s in state["steps"] if s["status"] == "failed"]
            self.assertTrue(failed)
            self.assertTrue(any("Setup stopped" in line for line in state["log"]))


if __name__ == "__main__":
    unittest.main()
