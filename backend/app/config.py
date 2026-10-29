"""Configuration from environment variables (PRD §6: self-hostable).

Significance thresholds live here / in classify.py — never in model prompts.
Traceable to docs/blast-rules.md §6.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- NCBI ---
NCBI_EMAIL: str = _env("NCBI_EMAIL")
NCBI_TOOL: str = _env("NCBI_TOOL", "WhatsGene")
NCBI_API_KEY: str = _env("NCBI_API_KEY")

# --- URLs / storage ---
PUBLIC_BASE_URL: str = _env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
FRONTEND_BASE_URL: str = _env("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
DATABASE_PATH: Path = Path(_env("DATABASE_PATH", "./whatsgene.db"))

# --- WhatsApp Cloud API ---
WHATSAPP_TOKEN: str = _env("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID: str = _env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN: str = _env("WHATSAPP_VERIFY_TOKEN", "change-me")
WHATSAPP_TEMPLATE_NAME: str = _env("WHATSAPP_TEMPLATE_NAME", "whatsgene_job_done")

# --- Agent layer: Muse Spark Open via Modal Shared Endpoint (PRD §8) ---
# OpenAI-compatible endpoint. URL and model name are env-configurable.
MUSE_BASE_URL: str = _env("MUSE_BASE_URL", _env("MODAL_BASE_URL"))
MUSE_API_KEY: str = _env("MUSE_API_KEY")
MUSE_MODEL: str = _env("MUSE_MODEL", "muse-spark-open")

# --- Agent-loop run budget (PRD §4.1; defaults open — PRD Open questions #1) ---
MAX_SEARCHES_PER_JOB: int = int(_env("MAX_SEARCHES_PER_JOB", "6") or "6")
MAX_JOB_SECONDS: int = int(_env("MAX_JOB_SECONDS", "1800") or "1800")

# Whether a logged model deviation applies without user confirmation.
# Open in PRD (Open questions #7); default keeps the rules-engine choice.
DEVIATION_AUTO_APPLY: bool = _env("DEVIATION_AUTO_APPLY", "false").lower() in ("1", "true", "yes")

# Verification: query/subject length ratio above this flags a mismatch (§8).
VERIFY_MAX_LENGTH_RATIO: float = float(_env("VERIFY_MAX_LENGTH_RATIO", "3") or "3")

# --- Classification thresholds (docs/blast-rules.md §6) ---
# Implemented in code/config only. Change here, not in prompts.
STRONG_MAX_EVALUE: float = 1e-5
STRONG_MIN_COVERAGE: float = 70.0  # percent
BORDERLINE_MAX_EVALUE: float = 1e-2
BORDERLINE_MIN_COVERAGE: float = 30.0  # percent; below this = not significant

# --- Worker / NCBI polling etiquette ---
POLL_INTERVAL_SECONDS: float = 15.0
POLL_BACKOFF_MAX_SECONDS: float = 120.0
