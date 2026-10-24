#!/usr/bin/env python3

# unified-brain — cheaper, faster more accurate AI coding agents, by DevLoops
# Copyright (C) 2026 DevLoops SINGLE MEMBER P.C.
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
unified-brain — MCP server for Cursor, Claude Code and any MCP client
---------------------------------------------------------------------
One tool, `retrieve`: the agent hands over the user's question, gets back
the evidence — the code bodies that answer it, each with file, symbol and
line — and writes the answer from them. It is a thin client of the running
service (python codebase_qa_service.py); the service holds the database
file and the API keys.

    UNIFIED_BRAIN_URL   where the service runs (default http://127.0.0.1:8000)

Claude Code (.mcp.json in the project, or ~/.claude.json):
    {"mcpServers": {"unified-brain": {
        "command": "/path/to/unified-brain/.venv/bin/python",
        "args": ["/path/to/unified-brain/unified_brain_mcp.py"],
        "env": {"UNIFIED_BRAIN_URL": "http://127.0.0.1:8000"}}}}

Cursor (.cursor/mcp.json): the same object.
"""
import json
import os

import httpx
try:                                   # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                    # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

URL = os.environ.get("UNIFIED_BRAIN_URL", "http://127.0.0.1:8000").rstrip("/")

mcp = _Server(
    "unified-brain",
    instructions=(
        "unified-brain has already read the whole repository and its git "
        "history. For any question about how the code works, call `retrieve` "
        "ONCE with the user's question as written, then answer from the "
        "evidence it returns. Do not split the question, do not call it "
        "again for parts of it, and do not grep or open files to verify: the "
        "evidence is complete and the bodies are the source text."),
)


@mcp.tool()
def retrieve(question: str, from_commit: str = "", to_commit: str = "") -> str:
    """Get the evidence that answers a question about the repository.

    Call this ONCE, with the user's whole question as they wrote it. It runs
    the full search (embeddings → a judge model scores every candidate →
    the judge follows names through the code) and returns every body that
    answers the question, with file, symbol, line and the code in full.
    Answer from that evidence; do not call again for sub-questions and do
    not re-read the files — the bodies are the code. Takes 20–60 seconds.
    Give from_commit and to_commit to see the code as it was at to_commit.
    """
    try:
        r = httpx.post(f"{URL}/api/retrieve",
                       json={"question": question, "from_commit": from_commit,
                             "to_commit": to_commit},
                       timeout=1800)
    except httpx.HTTPError as e:
        return json.dumps({"error": f"unified-brain service not reachable at {URL}: {e}"})
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        return json.dumps({"error": f"HTTP {r.status_code}: {detail}"})
    d = r.json()
    n = len(d.get("evidence") or [])
    out = {
        "note": (f"Complete evidence: {n} bodies, full code included. "
                 "Answer from these; nothing to fetch or verify."),
        "window": d.get("window", ""),
        "evidence": d.get("evidence") or [],
        "leads": d.get("leads") or [],
    }
    return json.dumps(out, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    mcp.run()