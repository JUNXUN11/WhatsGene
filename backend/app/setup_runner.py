"""Local BLAST setup runner — executes the steps setup_plan describes.

The wizard runs fixed, approved steps against URLs in this module:
download SwissProt FASTA and NCBI taxonomy, derive the taxid map from
FASTA headers, build with makeblastdb, and prove the result with
blastdbcmd before the database is trusted. Every step reports into one
in-process state that the UI polls. Failures keep the real error; a
step that cannot run fails the job loudly, never a fake success.

Downloads go through fetch() so tests can substitute local files
(file:// works too; WHATSGENE_SETUP_FASTA_URL / WHATSGENE_SETUP_TAX_URL
override for mirrors). No model code runs here: Muse explains the
plan, this module executes it.
"""
from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from . import config
from .settings import setup_status

FASTA_URL = os.environ.get(
    "WHATSGENE_SETUP_FASTA_URL",
    "https://ftp.uniprot.org/pub/databases/uniprot/current_release/"
    "knowledgebase/complete/uniprot_sprot.fasta.gz",
)
TAX_URL = os.environ.get(
    "WHATSGENE_SETUP_TAX_URL",
    "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdmp.zip",
)
VERIFY_ACCESSION = "P68871"
_STEP_IDS = ("check_blast", "download", "build", "verify")
_STEP_TITLES = {
    "check_blast": "Check BLAST+ programs",
    "download": "Download the database files",
    "build": "Build the search database (makeblastdb)",
    "verify": "Verify with a sample search",
}

_lock = threading.Lock()


def _idle_state() -> dict[str, Any]:
    return {
        "running": False,
        "status": "idle",  # idle | running | done | failed
        "database": "swissprot",
        "steps": [
            {"id": sid, "title": _STEP_TITLES[sid], "status": "pending", "detail": ""}
            for sid in _STEP_IDS
        ],
        "log": [],
        "started_at": None,
        "finished_at": None,
    }


_state: dict[str, Any] = _idle_state()


def get_state() -> dict[str, Any]:
    with _lock:
        return {**_state, "steps": [dict(s) for s in _state["steps"]],
                "log": list(_state["log"]), "setup": setup_status()}


def blastdb_dir() -> Path:
    raw = os.environ.get("BLASTDB", "").strip() or config.BLASTDB
    return Path(raw).expanduser() if raw else Path.home() / "blastdb"


def is_running() -> bool:
    with _lock:
        return bool(_state["running"])


def start(database: str = "swissprot") -> dict[str, Any]:
    """Queue the setup run. Refuses while another run is active."""
    with _lock:
        if _state["running"]:
            return get_state()
        _state.update(_idle_state())
        _state["running"] = True
        _state["status"] = "running"
        _state["database"] = database or "swissprot"
        _state["started_at"] = _now()
    thread = threading.Thread(target=_run, daemon=True, name="whatsgene-setup")
    thread.start()
    return get_state()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _set_step(step_id: str, status: str, detail: str = "") -> None:
    with _lock:
        for step in _state["steps"]:
            if step["id"] == step_id:
                step["status"] = status
                if detail:
                    step["detail"] = detail


def _log(line: str) -> None:
    with _lock:
        _state["log"].append(line)
        _state["log"] = _state["log"][-60:]


class _SetupError(RuntimeError):
    pass


def fetch(url: str, dest: Path, label: str = "") -> None:
    """Download url to dest with incremental progress on the step."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "WhatsGene-setup/0.3"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    done = 0
    total = 0
    with urllib.request.urlopen(request) as response, tmp.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if label:
                detail = f"{label}: {_mb(done)}"
                if total:
                    detail += f" of {_mb(total)} ({done * 100 // total}%)"
                _set_step("download", "running", detail)
    tmp.replace(dest)


def _mb(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB"


_OX_RE = re.compile(r"\bOX=(\d+)\b")


def build_taxid_map(fasta_path: Path, out_path: Path) -> int:
    """Derive accession->taxid lines from UniProt FASTA headers.

    Header shape: >sp|P68871|HBB_HUMAN ... OX=9606 ... The accession
    written is the bare accession, the form blastdbcmd -entry uses.
    Returns the number of map lines written.
    """
    count = 0
    with fasta_path.open(encoding="utf-8", errors="replace") as src, \
            out_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.startswith(">"):
                continue
            match = _OX_RE.search(line)
            if not match:
                continue
            token = line[1:].split()[0]
            parts = token.split("|")
            accession = parts[1] if len(parts) >= 3 and parts[0] in ("sp", "tr") else token
            out.write(f"{accession}\t{match.group(1)}\n")
            count += 1
    return count


def _run(*, fetch_fn=fetch) -> None:
    db_dir = blastdb_dir()
    src_dir = db_dir / "src"
    try:
        # --- check_blast --------------------------------------------
        _set_step("check_blast", "running")
        if not shutil.which("blastp") or not shutil.which("makeblastdb"):
            raise _SetupError(
                "BLAST+ not found on PATH. Install NCBI BLAST+ "
                "(Mac: brew install blast; Ubuntu: sudo apt-get install "
                "ncbi-blast+) and run setup again.")
        _set_step("check_blast", "done", "blastp and makeblastdb found.")
        _log(f"BLAST+ ready. Database folder: {db_dir}")

        # --- download -----------------------------------------------
        db_dir.mkdir(parents=True, exist_ok=True)
        src_dir.mkdir(parents=True, exist_ok=True)
        fasta_gz = src_dir / "uniprot_sprot.fasta.gz"
        fasta = src_dir / "uniprot_sprot.fasta"
        tax_zip = src_dir / "taxdmp.zip"
        _set_step("download", "running")
        if fasta_gz.is_file() and fasta_gz.stat().st_size > 0:
            _log(f"SwissProt FASTA already downloaded ({_mb(fasta_gz.stat().st_size)}); skipping download.")
        else:
            fetch_fn(FASTA_URL, fasta_gz, "SwissProt FASTA")
            _log(f"SwissProt FASTA downloaded ({_mb(fasta_gz.stat().st_size)}).")
        if tax_zip.is_file() and tax_zip.stat().st_size > 0:
            _log("Taxonomy archive already downloaded; skipping download.")
        else:
            fetch_fn(TAX_URL, tax_zip, "NCBI taxonomy")
            _log("NCBI taxonomy downloaded.")
        if fasta.is_file():
            _log("Plain FASTA already extracted; skipping extraction.")
        else:
            _set_step("download", "running", "Extracting the FASTA file")
            with gzip.open(fasta_gz, "rb") as src, fasta.open("wb") as out:
                shutil.copyfileobj(src, out, length=1 << 20)
            _log(f"FASTA extracted ({_mb(fasta.stat().st_size)}).")
        _set_step("download", "running", "Reading taxonomy files")
        with zipfile.ZipFile(tax_zip) as archive:
            names = set(archive.namelist())
            for member in ("names.dmp", "nodes.dmp"):
                target = src_dir / member
                if target.is_file():
                    continue
                if member not in names:
                    raise _SetupError(f"taxdmp.zip has no {member}; cannot continue.")
                with archive.open(member) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
        _log("Taxonomy files ready (names.dmp, nodes.dmp).")
        _set_step("download", "done", "Files downloaded and extracted.")

        # --- build ---------------------------------------------------
        _set_step("build", "running", "Deriving the taxonomy map from FASTA headers")
        taxid_map = src_dir / "sprot.taxidmap"
        if taxid_map.is_file() and taxid_map.stat().st_size > 0:
            _log("Taxonomy map already present; skipping derivation.")
        else:
            lines = build_taxid_map(fasta, taxid_map)
            if not lines:
                raise _SetupError("No OX= taxids found in the FASTA headers; cannot build the map.")
            _log(f"Taxonomy map derived ({lines} sequences).")
        stem = db_dir / "swissprot"
        if list(db_dir.glob("swissprot.*")):
            _set_step("build", "running", "Database files already exist; verifying instead of rebuilding")
            _log("swissprot.* files exist in the database folder; skipping rebuild.")
        else:
            _set_step("build", "running", "Running makeblastdb (can take a few minutes)")
            _log("Running makeblastdb with the taxonomy map.")
            proc = subprocess.run(
                ["makeblastdb", "-in", str(fasta), "-dbtype", "prot",
                 "-parse_seqids", "-taxid_map", str(taxid_map),
                 "-out", str(stem)],
                capture_output=True, text=True,
                timeout=config.LOCAL_BLAST_TIMEOUT_SECONDS)
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip()[-500:]
                raise _SetupError(f"makeblastdb failed: {tail}")
        _set_step("build", "done", "Database built.")

        # --- verify ---------------------------------------------------
        _set_step("verify", "running", f"Looking up {VERIFY_ACCESSION}")
        proc = subprocess.run(
            ["blastdbcmd", "-db", str(stem), "-entry", VERIFY_ACCESSION,
             "-outfmt", "%f"],
            capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or VERIFY_ACCESSION not in proc.stdout:
            tail = (proc.stderr or "").strip()[-300:]
            raise _SetupError(
                f"Verification failed: {VERIFY_ACCESSION} did not resolve "
                f"in the built database. {tail}")
        _set_step("verify", "done", f"{VERIFY_ACCESSION} resolved in the new database.")
        _log("Setup complete: local search is ready.")
        with _lock:
            _state["status"] = "done"
    except _SetupError as exc:
        _fail(str(exc))
    except Exception as exc:  # keep the real error, never a fake success
        _fail(f"{type(exc).__name__}: {exc}")
    finally:
        with _lock:
            _state["running"] = False
            _state["finished_at"] = _now()


def _fail(message: str) -> None:
    with _lock:
        for step in _state["steps"]:
            if step["status"] == "running":
                step["status"] = "failed"
                step["detail"] = message
        _state["status"] = "failed"
        _state["log"].append(f"Setup stopped: {message}")
