"""Library tests — file-drop inventory, confirmed sorting, custom DB registry.

File I/O only in temp directories; no subprocess and no network. Run:
    cd backend && .venv/bin/python -m unittest tests.test_library
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import library  # noqa: E402
from app.rules_engine import plan_programs  # noqa: E402
from app.search_backend import (LocalBlast, SearchError,  # noqa: E402
                                local_database_entry, register_custom_database)

GLOBIN = ">P68871 beta globin\nMVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLSTPDAVMGNPKVKAHGKKV\n"
MULTI = "".join(f">SEQ{i} protein {i}\nMVHLTPEEKSAVTALWGKV\n" for i in range(30))
DNA = ">16S fragment\nATGAGAGTTTGATCCTGGCTCAGAACGAACGCTGGCGGCAGGCTTAACACATGCAAGTCG\n"


class TestInventory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.inbox = root / "inbox"
        self.library_dir = root / "library"
        self.inbox.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _drop(self, name: str, text: str) -> Path:
        path = self.inbox / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_single_fasta_proposed_as_query(self):
        self._drop("globin.fasta", GLOBIN)
        items = library.inventory(self.inbox)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["kind"], "fasta")
        self.assertEqual(item["category_proposed"], "query")
        self.assertEqual(item["sequence_type"], "protein")
        self.assertTrue(item["can_search"])
        self.assertIn("P68871", item["first_header"])

    def test_many_fasta_proposed_as_database_source(self):
        self._drop("worm_proteins.faa", MULTI)
        items = library.inventory(self.inbox)
        self.assertEqual(items[0]["category_proposed"], "database_source")
        self.assertEqual(items[0]["sequence_count"], 30)
        self.assertTrue(items[0]["can_build_database"])

    def test_accession_list_and_document_and_unknown(self):
        self._drop("ids.txt", "NP_000509\nP68871\n")
        self._drop("notes.md", "# Lab notes\nWe searched globin today.\n")
        self._drop("blob.bin", "\x00\x01\x02not a sequence")
        items = {i["name"]: i for i in library.inventory(self.inbox)}
        self.assertEqual(items["ids.txt"]["kind"], "accession_list")
        self.assertEqual(items["notes.md"]["category_proposed"], "document")
        self.assertEqual(items["blob.bin"]["category_proposed"], "unknown")

    def test_query_text_returns_first_record(self):
        path = self._drop("globin.fasta", GLOBIN + ">OTHER\nAAAA\n")
        text = library.read_query_text(path)
        self.assertIn("P68871", text)
        self.assertNotIn("OTHER", text)


class TestSorting(unittest.TestCase):
    def test_sort_copies_never_moves_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox, lib = root / "inbox", root / "library"
            inbox.mkdir()
            src = inbox / "globin.fasta"
            src.write_text(GLOBIN, encoding="utf-8")
            result = library.sort_files(
                [{"path": "globin.fasta", "category": "query"}],
                inbox=inbox, library_dir=lib)
            self.assertTrue(src.exists())  # original kept
            dest = lib / "query" / "globin.fasta"
            self.assertTrue(dest.exists())
            self.assertEqual(result["sorted"][0]["category"], "query")
            listed = library.library_inventory(lib)
            self.assertEqual(listed[0]["category"], "query")
            # Sorting again is a no-op duplicate, not a second copy.
            again = library.sort_files(
                [{"path": "globin.fasta", "category": "query"}],
                inbox=inbox, library_dir=lib)
            self.assertTrue(again["sorted"][0]["duplicate"])

    def test_sort_rejects_escape_and_bad_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox, lib = root / "inbox", root / "library"
            inbox.mkdir()
            (inbox / "a.fasta").write_text(GLOBIN, encoding="utf-8")
            with self.assertRaises(ValueError):
                library.sort_files([{"path": "../secret.txt", "category": "query"}],
                                   inbox=inbox, library_dir=lib)
            with self.assertRaises(ValueError):
                library.sort_files([{"path": "a.fasta", "category": "trash"}],
                                   inbox=inbox, library_dir=lib)


class TestCustomDatabaseRegistry(unittest.TestCase):
    def test_name_validation(self):
        self.assertEqual(library.validate_database_name("worm_globins"), "worm_globins")
        for bad in ("SwissProt", "pdbaa", "1abc", "ab", "has space", "a-b"):
            with self.assertRaises(ValueError, msg=bad):
                library.validate_database_name(bad)
        self.assertEqual(library.suggest_database_name("Worm Proteins.faa"), "worm_proteins")

    def test_registered_custom_database_is_searchable_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "worm_globins.pdb").write_text("")
            register_custom_database(
                {"name": "worm_globins", "stem": "worm_globins", "dbtype": "protein",
                 "label": "Custom — worms", "description": "test"},
                db_dir=root)
            old = os.environ.get("BLASTDB")
            os.environ["BLASTDB"] = tmp
            try:
                entry = local_database_entry("worm_globins")
                self.assertIsNotNone(entry)
                self.assertEqual(entry["dbtype"], "protein")
                backend = LocalBlast(db_dir=root)
                self.assertEqual(backend._db_path("worm_globins"), root / "worm_globins")
                plan = plan_programs(intent={}, detected_type="protein", mode="auto",
                                     requested_database="worm_globins")
                self.assertEqual(plan[0]["database"], "worm_globins")
            finally:
                if old is None:
                    os.environ.pop("BLASTDB", None)
                else:
                    os.environ["BLASTDB"] = old

    def test_unknown_database_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBlast(db_dir=tmp)
            with self.assertRaises(SearchError):
                backend._db_path("worm_globins")


if __name__ == "__main__":
    unittest.main()
