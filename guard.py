"""The agent guard: the part every check shares.

A coding agent's hook (Cursor: cursor_guard.py) calls the entry points here
before the agent acts. /api/guard/task keeps what the human asked for.
/api/guard/command gets one shell command before it runs and answers allow or
deny. /api/guard/log gives every command judged so far.

A command is checked against the task the human gave, never against what the
agent says about its own work.

This file holds no check of its own. It holds the entry points, the record,
and the steps every check goes through. Each check is a file of its own
(rogue.py, reward_hacking.py, evil_genie.py) and says four things:

    FIRST_LOOK, applies()   when it applies: its question to the judge about
                            the command line, and which answers need a check
    seeds()                 where its reading starts: what the command names;
       or STARTS_FROM_CHANGES = True: what the agent changed and not pushed
    question()              what its reading looks for
    SYSTEM                  how its decision is made

What the guard needs from the QA service (the judge's address, the chain, the
writer model, the store) it takes from the service module handed to attach().
Nothing here runs unless a hook calls it.
"""
import asyncio
import json
import os
import time
from datetime import datetime

import httpx
import litellm

import skills_lib
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
svc = None        # the QA service module, set by attach()
CHECKS: list = []  # the check files, in the order they run


def attach(app, service) -> None:
    """Called once by codebase_qa_service.py: adds the guard's entry points
    to the service and loads the checks."""
    global svc
    svc = service
    import rogue
    import reward_hacking
    import evil_genie
    CHECKS[:] = [rogue, reward_hacking, evil_genie]
    app.include_router(router)


class GuardTaskRequest(BaseModel):
    conversation_id: str
    prompt: str


class GuardCommandRequest(BaseModel):
    conversation_id: str = ""
    command: str
    cwd: str = ""
    roots: list[str] = []     # the folders open in the editor


# ── what a check builds on ────────────────────────────────────────────────────

def seed(dk: str, body: str, why: str) -> dict:
    """One piece of the repository as a place where reading starts."""
    path, name, _line, _kind = skills_lib.parse_def_key(dk)
    guard, code = svc._split_guard(body)
    return {"skill_id": "", "name": f"{name} ({path})", "description": "",
            "def_key": dk, "file_path": path, "symbol": name, "code": code,
            "guard": guard, "hit": None, "score": None, "trail": [why],
            "suggested": False, "is_obsolete": False, "reconstructed": False,
            "is_composite": False}


def first_look(command: str, cwd: str, criteria: dict):
    """One Jev choice call on the command line itself, with a check's own
    answers to choose from. Returns (choice or None, probability per choice)."""
    payload = {"model": svc.JEV_MODEL,
               "state": {"command": command, "working_directory": cwd},
               "questions": {"risk": {
                   "type": "choice",
                   "instructions": "A coding agent is about to run this shell "
                                   "command (`command`) in a software "
                                   "repository. What can it do?",
                   "criteria": criteria}}}
    with httpx.Client(timeout=60,
                      headers={"Authorization": f"Bearer {svc.JEV_KEY}"}) as client:
        for attempt in range(4):
            try:
                res = client.post(svc.JEV_URL, json=payload)
            except httpx.HTTPError:
                time.sleep(2 ** attempt)
                continue
            if res.status_code == 429 or res.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            try:
                ans = ((res.json().get("answers") or {}).get("risk") or {})
            except ValueError:
                return None, {}
            if res.status_code == 200 and ans.get("choice") in criteria:
                return ans["choice"], ans.get("probabilities") or {}
            print(f"⚠️  guard: first look failed: HTTP {res.status_code} "
                  f"{svc._scrub(res.text[:200])}")
            return None, {}
    return None, {}



def changed():
    """What the agent changed and has not pushed, committed or not.
    Returns (the diff as text, the changed pieces as seeds, notes for the log).

    The comparison is with the last commit that is also on the remote branch;
    with no remote branch, with the last commit. The pieces are cut from the
    files as they are on disk now, with the ingest's own cutter, so a piece
    the agent has just written is read as written. Nothing here uses the
    index."""
    import ingester
    repo = os.path.dirname(os.path.abspath(svc.DB_PATH))
    git = ingester.GitDiffIngester(repo)
    try:
        base = git.git("merge-base", "HEAD", "@{upstream}")
    except Exception:
        base = "HEAD"
    diff = git.git("diff", base)
    names = [f for f in git.git("diff", "--name-only", base).split("\n") if f]
    # files git does not know yet, without the index's own database files
    own = os.path.basename(svc.DB_PATH)
    new = [f for f in git.git("ls-files", "--others",
                              "--exclude-standard").split("\n")
           if f and not f.startswith(own)]
    seeds, notes = [], []
    for path in names + new:
        full = os.path.join(repo, path)
        if not os.path.isfile(full):
            notes.append(f"{path}: removed")
            continue
        with open(full, "rb") as f:
            after = f.read()
        before = None if path in new else git.file_at_raw(base, path)
        if path in new:
            diff += (f"\nnew file, not yet in git: {path}\n"
                     + after.decode("utf-8", "replace"))
        pieces = [c for c in git.changed_symbols(path, before, after)
                  if c["changeType"] != "deleted"]
        for c in pieces:
            seeds.append(seed(ingester.local_def_key(path, c), c["code"],
                              f"the agent {c['changeType']} this"))
        notes.append(f"{path}: {len(pieces)} piece(s) changed or added")
    return diff, seeds, notes


def context(skills: list) -> str:
    """The code a decision is made from, each piece with how it was reached."""
    out = []
    for i, s in enumerate(skills, 1):
        how = (" → ".join(s["trail"]) if s.get("trail")
               else "found by the search on the command")
        code = svc._BLANK_MARKER_RE.sub("", s.get("code") or "")
        out.append(
            f"### {i}. `{s.get('symbol') or s.get('name')}` in "
            f"{s.get('file_path') or '?'}\nHow it was reached: {how}"
            + (f"\n{svc._guard_line(s).rstrip()}" if s.get("guard") else "")
            + f"\n```\n{code}\n```")
    return "\n\n".join(out)


async def verdict(system: str, command: str, cwd: str, task: list, code: str,
                  diff=None):
    """One call of the writer model with a check's own instruction: may this
    command run, given the task and the code (and, for a check that starts
    from the changes, the diff)? Returns (decision, reason). Anything other
    than a clear "allow" is a deny."""
    target = svc._llm_target()
    extra = ({} if target.provider == "anthropic"
             else svc._no_think_params(target)
             if os.environ.get("WRITER_REASONING", "high") == "none"
             else {"reasoning_effort": "high",
                   "allowed_openai_params": ["reasoning_effort"]})
    said = ("\n\n".join(f"Message {i + 1}: {t}" for i, t in enumerate(task))
            if task else "(no task was recorded for this conversation)")
    user = (f"What the human asked the agent to do:\n{said}\n\n"
            f"The command the agent is about to run:\n{command}\n\n"
            f"Working directory: {cwd or '(the repository root)'}\n\n"
            + ("" if diff is None else
               "What the agent changed and has not pushed (a diff):\n"
               f"{diff or '(nothing has changed)'}\n\n")
            + f"Code from the repository:\n{code or '(nothing was found)'}")
    res = await litellm.acompletion(
        model=target.model, api_key=target.api_key, api_base=target.api_base,
        max_tokens=int(os.environ.get("WRITER_MAX_TOKENS", "120000")),
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0, **dict(extra))
    text = (res.choices[0].message.content or "").strip()
    u = getattr(res, "usage", None)
    cost = getattr(u, "cost", None)
    print(f"🛡️  writer: {getattr(u, 'prompt_tokens', 0):,} tokens in · "
          f"{getattr(u, 'completion_tokens', 0):,} out"
          + (f" · ${cost:.4f}" if cost is not None else ""))
    try:
        out = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return "deny", "The check gave no clear answer, so the command is blocked."
    reason = str(out.get("reason") or "").strip()
    if out.get("decision") == "allow":
        return "allow", reason
    return "deny", reason or "The check did not allow this command."


# ── the steps of one check ────────────────────────────────────────────────────

async def run_check(check, look, req, task: list, org_redis,
                    org_redis_binary) -> dict:
    """One check on one command, from its first look to its decision."""
    t0 = time.time()
    risk, probs = look
    evidence: list = []
    if risk is not None and not check.applies(risk):
        decision, reason = "allow", ""
    elif risk is None:
        decision, reason = "deny", ("The judge did not answer, so the command "
                                    "was not checked and is blocked.")
    else:
        from_changes = getattr(check, "STARTS_FROM_CHANGES", False)
        diff = None
        info: dict = {}
        try:
            async with svc._RETRIEVE_LOCK:
                # The check says where to start. Only when a command names
                # nothing the index knows is the search on its question used.
                if from_changes:
                    diff, skills, notes = await asyncio.to_thread(changed)
                else:
                    skills, notes = await asyncio.to_thread(
                        check.seeds, req.command, req.cwd, req.roots, org_redis)
                for note in notes:
                    print(f"🛡️  {check.NAME}: {note}")
                question = check.question(req.command, req.cwd, skills)
                if skills:
                    extra, info = await asyncio.to_thread(
                        svc._jev_expand, question, org_redis, skills)
                    skills = skills + extra
                elif from_changes:
                    pass                    # no piece to start from
                else:
                    async for kind, payload in svc._gather_evidence(
                            question, org_redis, org_redis_binary, None,
                            svc._llm_target()):
                        if kind == "error":
                            raise RuntimeError(payload)
                        if kind == "result":
                            skills = payload.get("skills") or []
            evidence = [{k: r[k] for k in ("file", "symbol", "line", "how")}
                        for r in map(svc._evidence_row, skills)]
            if info:
                print(f"🛡️  {check.NAME}: judge {info.get('scored', 0)} calls"
                      f" · ${info.get('cost', 0):.4f}")
            if from_changes and not diff:
                # nothing to hand over, so nothing to cheat with
                decision, reason = "allow", ("Nothing has changed since the "
                                             "last push.")
            else:
                decision, reason = await verdict(
                    check.SYSTEM, req.command, req.cwd, task, context(skills),
                    diff)
        except Exception as e:
            decision, reason = "deny", ("The check could not be finished "
                                        f"({svc._scrub(str(e))[:200]}), so the "
                                        "command is blocked.")
    secs = round(time.time() - t0, 1)
    print(f"🛡️  {check.NAME}: {decision} `{req.command[:120]}` · first look "
          f"{risk} " + " ".join(f"{k}={v:.2f}" for k, v in probs.items())
          + f" · {len(evidence)} bodies · {secs}s"
          + (f" · {reason}" if reason else ""))
    return {"check": check.NAME, "decision": decision, "reason": reason,
            "risk": risk, "risk_probabilities": probs, "evidence": evidence,
            "secs": secs}


# ── entry points ──────────────────────────────────────────────────────────────

@router.post("/api/guard/task")
async def guard_task(req: GuardTaskRequest):
    """Keep one message of the human, in the order given."""
    org_redis, _ = svc._redis_clients()
    if req.conversation_id and req.prompt.strip():
        org_redis.rpush(f"guard:task:{req.conversation_id}", req.prompt)
    return {"ok": True}


@router.post("/api/guard/command")
async def guard_command(req: GuardCommandRequest):
    org_redis, org_redis_binary = svc._redis_clients()
    t0 = time.time()
    task = (list(org_redis.lrange(f"guard:task:{req.conversation_id}", 0, -1))
            if req.conversation_id else [])
    # every check's first look at the same moment (one judge call each), then
    # the checks that apply, one after another
    looks = await asyncio.gather(*[
        asyncio.to_thread(first_look, req.command, req.cwd, check.FIRST_LOOK)
        for check in CHECKS])
    results = [await run_check(check, look, req, task, org_redis,
                               org_redis_binary)
               for check, look in zip(CHECKS, looks)]
    denied = [r for r in results if r["decision"] == "deny"]
    decision = "deny" if denied else "allow"
    # the answer carries the check that blocked, or the first one when none did
    lead = (denied or results)[0]
    reason = (lead["reason"] if len(denied) <= 1 else
              " ".join(f"[{r['check']}] {r['reason']}" for r in denied))
    secs = round(time.time() - t0, 1)
    record = {"at": datetime.now().isoformat(timespec="seconds"),
              "conversation_id": req.conversation_id, "task": task,
              "command": req.command, "cwd": req.cwd, "risk": lead["risk"],
              "risk_probabilities": lead["risk_probabilities"],
              "decision": decision, "reason": reason,
              "evidence": lead["evidence"], "secs": secs, "checks": results}
    org_redis.rpush("guard:log", json.dumps(record))
    return {"decision": decision, "reason": reason, "risk": lead["risk"],
            "risk_probabilities": lead["risk_probabilities"], "secs": secs,
            "evidence": lead["evidence"], "checks": results}


@router.get("/api/guard/log")
def guard_log():
    """Every command the guard has judged, oldest first."""
    org_redis, _ = svc._redis_clients()
    return [json.loads(r) for r in org_redis.lrange("guard:log", 0, -1)]