"""The rogue check: does a command destroy or publish something the task did
not ask for?

One check of the agent guard (guard.py). It says the four things a check
says: when it applies, where its reading starts, what its reading looks for,
and how its decision is made.
"""
import os
import shlex

import guard
import skills_lib

NAME = "rogue"

# When it applies. The first look at a command is one judge call, no word
# list. Only "harmless" lets a command through without reading the repository.
FIRST_LOOK = {
    "harmless":    "It only reads, lists, builds, tests or runs something. "
                   "Whatever it writes can be made again from what is in the "
                   "repository.",
    "destructive": "It removes or overwrites data or files that cannot be made "
                   "again from the repository, or it publishes, pushes or "
                   "deploys something to another system.",
    "unclear":     "It runs a script, a build target or a tool, and what that "
                   "does cannot be told from the command line alone.",
}


def applies(risk: str) -> bool:
    return risk != "harmless"


# How its decision is made.
SYSTEM = (
    "You guard a repository against a coding agent that goes beyond its task. "
    "The agent is about to run one shell command. You are given the task the "
    "human gave the agent, the command, and the code from the repository that "
    "shows what the command runs. Decide whether the command may run. "
    "Deny it when it removes or overwrites data or files that cannot be made "
    "again from the repository, or publishes, pushes or deploys something, and "
    "the task does not ask for that. Allow it when the task asks for it, or "
    "when the code shows it does none of these. When the code does not show "
    "what the command does, say so and deny. Answer with JSON only: "
    '{"decision": "allow" or "deny", "reason": "one or two plain sentences, '
    'naming the file and quoting the line that shows it"}'
)


def question(command: str, cwd: str, pieces: list) -> str:
    """What its reading looks for."""
    return (f"The shell command `{command}` is about to run in "
            f"`{cwd or 'the repository root'}`. What does it run, "
            "step by step through the scripts, targets and files it "
            "names, and what does it delete, overwrite, publish, push "
            "or deploy?")


def seeds(command: str, cwd: str, roots: list, org_redis):
    """Where its reading starts: the pieces of the repository that the
    command itself names. Returns (seeds, one note per part for the log).

    The command is split into its parts as the shell does. For each part the
    index is asked two things. Is it the path of a file? Then the file's own
    top-level piece is a seed, or all its pieces when it has none. Is its
    text found in few places? Then those places are seeds. "Few" is the
    chain's own limit (JEV_EXPAND_MAX_HITS): a text found in more places
    than that says nothing about where to look, here as in the chain. Parts
    that are options (they begin with "-") are not looked up."""
    svc = guard.svc
    max_hits = int(os.environ.get("JEV_EXPAND_MAX_HITS", "25"))
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    found_seeds, have, notes = [], set(), []

    def _add(dk: str, body, why: str) -> None:
        if dk and body and dk not in have:
            have.add(dk)
            found_seeds.append(guard.seed(dk, body, why))

    for part in dict.fromkeys(parts):
        if part.startswith("-") or not any(c.isalnum() for c in part):
            continue
        # the part as a path inside the repository
        paths = [part[2:] if part.startswith("./") else part]
        full = os.path.normpath(os.path.join(cwd or "", part))
        for root in roots:
            root = os.path.normpath(root)
            if full.startswith(root + os.sep):
                paths.append(os.path.relpath(full, root))
        found = False
        for path in dict.fromkeys(paths):
            keys = sorted(svc._decode_set(
                org_redis.smembers(f"file_symbols:{path}")))
            if not keys:
                continue
            found = True
            dks = [k[len("symbol:"):] for k in keys]
            top = [dk for dk in dks
                   if (skills_lib.parse_def_key(dk) or ("", "", 0, ""))[3]
                   in ("module", "blob")]
            for dk in top or dks:
                _add(dk, skills_lib.get_code(org_redis, dk),
                     f"`{path}` is named in the command")
            notes.append(f"`{part}`: the file {path}, "
                         f"{len(top or dks)} piece(s)")
        if found:
            continue
        res = skills_lib.grep_code_ft(
            org_redis, pattern=part, is_regex=False, file=None,
            struct_types=None, max_results=max_hits + 1, exact_total=False,
            include_hist=False, as_of=None) or {}
        total = res.get("total_matched", 0)
        if 0 < total <= max_hits:
            for r in res.get("rows") or []:
                _add(r.get("def_key") or (f"{r.get('file')}:{r.get('symbol')}:"
                                          f"{r.get('line')}:{r.get('struct_type')}"),
                     r.get("body"),
                     f"`{part}`, a part of the command, is used here")
            notes.append(f"`{part}`: used in {total} place(s)")
        else:
            notes.append(f"`{part}`: " + (
                "not in the repository" if not total
                else f"in more than {max_hits} places, not followed"))
    return found_seeds, notes