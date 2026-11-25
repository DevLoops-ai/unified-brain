#!/usr/bin/env python3
"""Cursor hook for the unified-brain agent guard.

Cursor starts this program before it sends a prompt (beforeSubmitPrompt) and
before the agent runs a shell command (beforeShellExecution). It hands the
event to the running unified-brain service and prints the answer in the form
Cursor expects. It uses only the Python standard library.

UNIFIED_BRAIN_URL: where the service runs (default http://127.0.0.1:8000).
"""
import json
import os
import sys
import urllib.request

URL = os.environ.get("UNIFIED_BRAIN_URL", "http://127.0.0.1:8000").rstrip("/")


def call(path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        URL + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def answer(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def main() -> None:
    event = json.load(sys.stdin)
    name = event.get("hook_event_name") or ""
    conversation = event.get("conversation_id") or ""

    if name == "beforeSubmitPrompt":
        # The prompt is never held back. If it could not be stored, a later
        # command is judged with no task on record, which the guard is told.
        try:
            call("/api/guard/task",
                 {"conversation_id": conversation,
                  "prompt": event.get("prompt") or ""}, 10)
        except Exception:
            pass
        answer({"continue": True})
        return

    if name == "beforeShellExecution":
        command = event.get("command") or ""
        try:
            res = call("/api/guard/command",
                       {"conversation_id": conversation, "command": command,
                        "cwd": event.get("cwd") or "",
                        "roots": event.get("workspace_roots") or []}, 110)
        except Exception as e:
            msg = (f"unified-brain guard: no answer from {URL} "
                   f"({type(e).__name__}). The command was not checked, so "
                   "it is blocked.")
            answer({"permission": "deny", "user_message": msg,
                    "agent_message": msg})
            return
        if res.get("decision") == "allow":
            answer({"permission": "allow"})
            return
        msg = "unified-brain guard blocked this command. " + (
            res.get("reason") or "No reason was given.")
        answer({"permission": "deny", "user_message": msg,
                "agent_message": msg + " Do not try another way to do the "
                                       "same thing. Tell the user."})
        return

    answer({})


if __name__ == "__main__":
    main()