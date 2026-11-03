"""WhatsGene MCP server — the library and BLAST tools as MCP tools.

Run (stdio, for any MCP host such as a Muse client):

    cd backend && .venv/bin/python -m app.mcp_server

The model may choose tools and explain results; deterministic code
validates, copies, builds, searches, classifies, and verifies. Every
tool is a thin wrapper over app.library / app.agent_loop /
app.search_backend, the same code the web app runs — no tool
reimplements science, and no threshold comes from a prompt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import db, library
from .agent_loop import process_job
from .search_backend import (LocalBlast, local_database_catalog,
                             local_database_entry)

mcp = FastMCP("WhatsGene")


def tool_inventory_files() -> dict[str, Any]:
    """Classify every file in the inbox plus what is already sorted."""
    return {
        "inbox_dir": str(library.inbox_dir()),
        "library_dir": str(library.library_dir()),
        "inbox": library.inventory(),
        "library": library.library_inventory(),
        "note": "category_proposed is code's proposal. Nothing is sorted "
                "until sort_files is called with confirm=True.",
    }


def tool_explain_file(name: str) -> dict[str, Any]:
    """Explain one dropped or sorted file by name or path."""
    items = library.inventory() + library.library_inventory()
    for item in items:
        if name in (item["name"], item["path"]):
            return {"file": item, "explanation": library.explain_file(item)}
    return {"error": f"No file named {name!r} in the inbox or library."}


def tool_sort_files(items: list[dict[str, Any]], confirm: bool = False) -> dict[str, Any]:
    """Copy confirmed files into the library. Originals never move."""
    if not confirm:
        return {"error": "Sorting needs confirm=True with the categories "
                         "the user approved. Call inventory_files first, "
                         "show the proposal, then confirm.",
                "categories": list(library.CATEGORIES)}
    return library.sort_files(items)


def tool_list_databases() -> dict[str, Any]:
    """Local databases a search can name, with built/not-built status."""
    return {"databases": local_database_catalog()}


def _resolve_source(spec: str) -> Path:
    if spec.startswith("inbox:"):
        return library.resolve_within(library.inbox_dir(), spec[6:])
    if spec.startswith("library:"):
        return library.resolve_within(library.library_dir(), spec[8:])
    path = Path(spec).expanduser()
    for root in (library.inbox_dir(), library.library_dir()):
        try:
            return library.resolve_within(root, str(path.relative_to(root)))
        except (ValueError, Exception):
            continue
    raise ValueError("Source must be 'inbox:<path>', 'library:<path>', "
                     "or a file inside one of those folders.")


def tool_build_custom_database(source: str, name: str) -> dict[str, Any]:
    """Build a small local BLAST database from one sorted FASTA file."""
    return library.build_custom_database(_resolve_source(source), name)


def tool_build_database_from_taxon(organism: str, name: str) -> dict[str, Any]:
    """Build a small protein database from one taxon's SwissProt subset."""
    return library.build_database_from_taxon(organism, name)


def tool_run_search(sequence: str, question: str = "",
                    database: str | None = None) -> dict[str, Any]:
    """Run one local workflow synchronously and return verified facts."""
    if database and local_database_entry(database) is None:
        return {"error": f"Unknown local database {database!r}. "
                         "Call list_databases for the choices."}
    db.init_db()
    job = db.create_job(question=question or "Identify this sequence",
                        raw_input=sequence, source="mcp", workflow_mode="auto",
                        backend_choice="local", requested_database=database)
    final = process_job(job, LocalBlast())
    return _workflow_summary(final)


def _workflow_summary(job: dict[str, Any]) -> dict[str, Any]:
    hits = (job.get("hits") or [])[:5]
    return {
        "job_id": job["id"], "status": job.get("status"),
        "outcome": job.get("outcome"), "program": job.get("program"),
        "database": job.get("database"), "summary": job.get("summary"),
        "error": job.get("error"),
        "top_hits": [{"accession": h.get("accession"),
                      "organism": h.get("organism"),
                      "evalue": h.get("evalue"),
                      "identity": h.get("identity"),
                      "query_coverage": h.get("query_coverage"),
                      "classification": h.get("classification")} for h in hits],
    }


def tool_get_workflow(job_id: str) -> dict[str, Any]:
    """Stored facts for one workflow: summary, searches, step log."""
    db.init_db()
    job = db.get_job(job_id)
    if not job:
        return {"error": f"Job {job_id} not found."}
    out = _workflow_summary(job)
    out["searches"] = [{"program": s["program"], "database": s["database"],
                         "status": s["status"], "hits": len(s["hits"]),
                         "parameters": s["parameters"]}
                        for s in db.get_searches(job_id)]
    out["step_log"] = [{"step": s["step"], "decision": s["decision"],
                         "reason": s["reason"]} for s in db.get_step_log(job_id)]
    return out


def tool_explain_workflow(job_id: str) -> dict[str, Any]:
    """Plain explanation of a workflow, from stored values only."""
    data = tool_get_workflow(job_id)
    if "error" in data:
        return data
    lines = [data.get("summary") or "No summary stored for this workflow."]
    if data.get("outcome"):
        lines.append(f"Outcome: {data['outcome']} "
                     f"({data.get('program')} against {data.get('database')}).")
    for hit in data["top_hits"]:
        lines.append(
            f"Top hit {hit['accession']} ({hit['organism']}): "
            f"E={hit['evalue']}, identity {hit['identity']}%, "
            f"coverage {hit['query_coverage']}%, classed {hit['classification']}.")
    return {"job_id": job_id, "explanation": " ".join(lines), "facts": data}


for _fn in (tool_inventory_files, tool_explain_file, tool_sort_files,
            tool_list_databases, tool_build_custom_database,
            tool_build_database_from_taxon, tool_run_search,
            tool_get_workflow, tool_explain_workflow):
    mcp.tool(name=_fn.__name__.removeprefix("tool_"))(_fn)


if __name__ == "__main__":
    mcp.run(transport="stdio")
