"""Rules engine: intent + detected input type -> program/database.

Deterministic mapping from docs/blast-rules.md §1 (PRD §3). The model
never chooses the program directly; it may only propose a deviation
(logged, original preserved — see agent loop).
"""
from __future__ import annotations

from .search_backend import local_database_entry

ALL_PROGRAMS = ("blastn", "blastp", "blastx", "tblastn", "tblastx")

# Database type each program searches (blast-rules §3).
_PROGRAM_DBTYPE: dict[str, str] = {
    "blastn": "nucleotide", "tblastn": "nucleotide", "tblastx": "nucleotide",
    "blastp": "protein", "blastx": "protein",
}
# (query type, database type) -> the only simple local program, where one
# exists. Cross-type pairs need a translated program (tblastn/blastx),
# which LocalBlast does not run yet, so they fail with that reason.
_AUTO_FOR_DB: dict[tuple[str, str], str] = {
    ("protein", "protein"): "blastp",
    ("dna", "nucleotide"): "blastn",
}

# program -> (query type it accepts, default database)
_PROGRAM_CATALOG: dict[str, tuple[str, str]] = {
    "blastn": ("dna", "refseq_nucleotide"),
    "blastp": ("protein", "refseq_protein"),
    "blastx": ("dna", "refseq_protein"),
    "tblastn": ("protein", "est"),
    "tblastx": ("dna", "refseq_nucleotide"),
}


def applicable_programs(detected_type: str) -> list[str]:
    """Programs that can accept this query type (blast-rules §3 table)."""
    return [p for p in ALL_PROGRAMS if _PROGRAM_CATALOG[p][0] == detected_type]


def database_for_program(program: str) -> str:
    return _PROGRAM_CATALOG[program][1]


def _scoped_filters(entry: dict, intent: dict) -> tuple[str | None, str | None, str]:
    """Organism filters for a user-named database.

    Only the swissprot copy carries the seqid taxonomy map that local
    organism filtering uses. For any other named database the database
    itself is the scope, so filters are dropped and the reason says so —
    never silently, never applied against the wrong seqid space.
    """
    target = intent.get("target_organism")
    exclude = intent.get("exclude_organism")
    if entry["name"] == "swissprot":
        return target, exclude, ""
    if target or exclude:
        return None, None, (
            " Organism filter not applied: the named database is the "
            "search scope (local organism filtering exists only for swissprot).")
    return None, None, ""


def plan_programs(*, intent: dict, detected_type: str, mode: str = "auto",
                  requested_program: str | None = None,
                  requested_database: str | None = None) -> list[dict]:
    """Plan the searches for one workflow.

    mode="auto": the rules engine's single best search (model intent only).
    mode="single": one user-chosen program; incompatible choices raise.
    mode="all": every program that accepts the query type — blastp+tblastn
    for protein, blastn+blastx+tblastx for DNA. A program that cannot
    accept the query alphabet is never submitted; the plan step logs why.

    requested_database (a canonical local database name) is a user choice:
    it overrides the rules database, and in auto mode the program adapts
    to the database type. Incompatible pairs raise; "all" mode rejects it.
    """
    mode = (mode or "auto").lower()
    if requested_database:
        entry = local_database_entry(requested_database)
        if entry is None:
            raise ValueError(
                f"Unknown local database {requested_database!r}. "
                "Choose one from the local database list, or leave it automatic.")
        if mode == "all":
            raise ValueError(
                "A specific database cannot be combined with All programs. "
                "Choose Auto or one program with that database.")
        if mode == "auto":
            program = _AUTO_FOR_DB.get((detected_type, entry["dbtype"]))
            if program is None:
                needed = "tblastn" if detected_type == "protein" else "blastx"
                raise ValueError(
                    f"Database {entry['name']} is a {entry['dbtype']} database. "
                    f"Searching it with a {detected_type} query needs {needed}, "
                    "which local search does not run yet. Pick a matching "
                    "database or use the real NCBI backend.")
            organism_filter, exclude, filter_note = _scoped_filters(entry, intent)
            return [{"program": program, "database": entry["name"],
                     "organism_filter": organism_filter,
                     "exclude_organism": exclude,
                     "reason": (f"User selected local database {entry['name']} "
                                f"({entry['label']}); {program} searches it for "
                                f"this {detected_type} query." + filter_note),
                     "rule": "blast-rules §1/§3: user-selected local database, program validated in code"}]
        # single mode falls through; its spec is type-checked below.
    if mode == "auto":
        return [choose_search(intent=intent, detected_type=detected_type)]
    if mode == "single":
        program = (requested_program or "").lower()
        if program not in ALL_PROGRAMS:
            raise ValueError(
                f"Unknown BLAST program {requested_program!r}. Choose one of: {', '.join(ALL_PROGRAMS)}.")
        if _PROGRAM_CATALOG[program][0] != detected_type:
            raise ValueError(
                f"{program} needs a {_PROGRAM_CATALOG[program][0]} query, but this query was "
                f"detected as {detected_type}. Applicable programs: {', '.join(applicable_programs(detected_type))}.")
        target = intent.get("target_organism")
        if requested_database:
            entry = local_database_entry(requested_database)
            assert entry is not None  # validated above
            if _PROGRAM_DBTYPE[program] != entry["dbtype"]:
                raise ValueError(
                    f"Database {entry['name']} is a {entry['dbtype']} database, "
                    f"but {program} searches a {_PROGRAM_DBTYPE[program]} database. "
                    "Pick a program that matches the database type.")
            organism_filter, exclude, filter_note = _scoped_filters(entry, intent)
            return [{"program": program, "database": entry["name"],
                     "organism_filter": organism_filter, "exclude_organism": exclude,
                     "reason": (f"User selected {program} against local database "
                                f"{entry['name']} ({entry['label']})." + filter_note),
                     "rule": "blast-rules §3: user-selected program and database, validated in code"}]
        return [{"program": program, "database": database_for_program(program),
                 "organism_filter": target, "exclude_organism": intent.get("exclude_organism"),
                 "reason": f"User selected {program} for this {detected_type} query.",
                 "rule": "blast-rules §3: user-selected program, validated in code"}]
    if mode == "all":
        target = intent.get("target_organism")
        return [{"program": p, "database": database_for_program(p),
                 "organism_filter": target, "exclude_organism": intent.get("exclude_organism"),
                 "reason": (f"Fan-out requested: run every program that accepts a "
                            f"{detected_type} query ({p} against {database_for_program(p)})."),
                 "rule": "blast-rules §3: all applicable programs"} for p in applicable_programs(detected_type)]
    raise ValueError(f"Unknown workflow mode {mode!r}. Use auto, single, or all.")


def choose_search(*, intent: dict, detected_type: str) -> dict:
    """Return {program, database, organism_filter, reason, rule}.

    organism_filter is the intent's target organism/group (or None).
    """
    target = intent.get("target_organism")
    goal = intent.get("goal", "find_related_gene")
    raw_q = (intent.get("raw_question") or "").lower()
    wants_gene_discovery = "gene" in raw_q

    if detected_type == "protein" and goal == "find_related_gene" and target and wants_gene_discovery:
        return {
            "program": "tblastn",
            "database": "est",
            "organism_filter": target, "exclude_organism": intent.get("exclude_organism"),
            "reason": (
                f"Protein query looking for a related gene in {target}: search the "
                "protein against DNA/EST sequences (tblastn, Find-a-Gene pattern)."
            ),
            "rule": "blast-rules §1: protein + find-in-target-group -> tblastn/est",
        }
    if detected_type == "protein":
        return {
            "program": "blastp",
            "database": "refseq_protein",
            "organism_filter": target, "exclude_organism": intent.get("exclude_organism"),
            "reason": "Protein query against a protein database (blastp).",
            "rule": "blast-rules §1: protein identify -> blastp/refseq_protein",
        }
    if detected_type == "dna" and goal == "find_related_gene" and target:
        return {
            "program": "blastn",
            "database": "refseq_nucleotide",
            "organism_filter": target, "exclude_organism": intent.get("exclude_organism"),
            "reason": f"DNA query searched against nucleotide sequences, limited to {target} (blastn).",
            "rule": "blast-rules §1: DNA + target group -> blastn/refseq_nucleotide",
        }
    return {
        "program": "blastn",
        "database": "refseq_nucleotide",
        "organism_filter": target, "exclude_organism": intent.get("exclude_organism"),
        "reason": "DNA query against a nucleotide database (blastn).",
        "rule": "blast-rules §1: DNA identify -> blastn/refseq_nucleotide",
    }
