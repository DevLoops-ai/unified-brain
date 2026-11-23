# unified-brain

**Persistent memory for System One coding agents, by [DevLoops](https://devloops.ai).**

On 24/10/2026 I have published as open source software a framework I call unified-brain: fast, cheap but also close -if not better- to frontier inner agent loops, evidence gathering for AI assisted SWE. The magic sauce is an intermediary SQLITE memory layer that facilitates retrieval, filtering and judging through System One decision models for the efficient evidence gathering — pplx-decider, an open-weights 27B (Apache-2.0) or pplx-decider-flash or Jev, a proprietary one.

Evidence gathering is the most expensive part of -in terms of time and computational resources- getting an answer from an AI agent. So logically, a product optimizing this can be useful.

The idea behind this architecture is to address cost and environmental burdens in AI assisted SWE through architectural elegance, rather than relying primarily on brute force model scaling.

Unified-brain is an open source architecture that inspires to be what unreliable RAGs and not easy to scale Graph-RAGs never managed to be: a simplified way to reach cheap, fast and compute-efficient evidence gathering engines.

Unified-brain has the capability to be always up-to-date and to never depend from session memory, since all the info lives in a local SQLite updatable memory. It replaces the need for turn based LLM agents with a cheap retrieval and System One discovery algorithm that does not require energy intensive computations.

The writer is a totally separate phase that works in one go with ANY LLM the user wants.

The agent spawned from unified-brain runs through MCP on Cursor, OpenCode or Claude Code etc. allowing you to use it through your favorite harness.

> So to be clear here: unified-brain is not a harness but a perception layer any harness plugs in!

The evals on two large OS libraries (xz and open62541, in `evals/` on this repo) are close enough to the frontier agents, at a fraction of their cost, that I believe this is a missing link to make AI more reliable.

Since 23/11/2026 it also answers from plain Markdown, not only from code. On GitHub's own help centre its high-reasoning mode reached 47.75 of 50 points, 0.75 behind a Claude Fable 5.2 agent at high effort (48.5), at 41 times lower cost ($0.091 against $3.76; the footnotes there say how each figure is made); its fast mode reached 46.0 in a sixth of the agent's time (see "Not only code" below).

This is because the limits holding back AI are:

- **The Reasoning and Hallucination Gap**:

The LLM turn reasoning it is introducing uncertainty and probabilistic outcomes.

BUT.. Unified-brain's System One discovery engine breaks the task into hundreds of yes-or-no calls, so the search itself does not reason in prose and while a single decision can be wrong, no path can be invented -at least in the sense of prose drifting.

- **Context Loss and Memory Limits**:

Long-running coding tasks consume massive amounts of tokens, causing the agent to forget early instructions or lose track of large-scale architecture.

BUT.. Unified-brain doesn't need cached memory thanks to the SQLITE persistent layer of context it operates with. It simply retrieves what it needs on the fly: the writer reads 80 k tokens per question on average (2 k to 166 k) against 1.1–2.2 M billed tokens per question for the frontier agents, and nothing builds up across questions. Every question is independent from one another as git diffs and commits will automatically be absorbed from the project's memory layer (still working on that last part).

---

Perhaps the most exciting development however from this proposed shift (established turn based exploration to System One evidence gathering) might be that avoiding unnecessary autoregressive investigation can reduce repeated weight and attention-state memory traffic. By using persistent retrieval and non-autoregressive judgments for discovery, unified-brain has a credible mechanism for reducing energy per correctly answered question — even when the conventional agent uses prompt caching.

**Several architectural factors support this optimism:**

- **Fewer intermediate decoding steps—even with caching.** In a conventional full-attention agent, each generated reasoning or tool-selection token attends to the accumulated context through its KV cache. Caching avoids recomputing earlier token states, but does not eliminate the attention work and memory access needed for subsequent generation. By replacing many intermediate generated tokens with bounded non-autoregressive judgments, unified-brain can avoid those repeated accesses during discovery.

- **Reduced KV-cache pressure.** Keeping investigation state outside the generative model can reduce the intermediate tokens whose attention states must be stored, accessed, or recomputed.

- **Less attention over exploration history.** The writer can receive selected evidence without repeatedly attending to unsuccessful searches, redundant tool results, and earlier investigative discussion.

- **Less repeated prefill work when caching misses.** Separating discovery from synthesis reduces opportunities for growing or changing prompts to trigger redundant computation.

- **Reusable repository preparation.** Persistent symbol and history indexes spread the cost of parsing and organizing evidence across many questions.

- **Efficient execution of independent judgments.** Non-autoregressive decisions can be batched or run concurrently, creating opportunities for better hardware utilization without generating intermediate prose.

- **Reduced demand for frontier-model execution.** Reserving the generative model primarily for synthesis can reduce its total inference workload, potentially lowering the serving capacity needed for a fixed volume of tasks.

- **Potentially greater serving capacity.** Reducing generative investigation could allow existing infrastructure to serve more correctly answered questions per minute by freeing model execution time and KV-cache capacity. The gain depends on the serving bottleneck and the resources required by the judge, retrieval, and final synthesis.

- **Potentially fewer corrective attempts.** If structured discovery improves evidence completeness and accuracy, it can reduce costly follow-up investigation and answer regeneration.

None of the energy savings has been measured. The measured quantities are tokens, dollars and seconds, in `evals/`.

On the same nine-question, 74-point xz benchmark (`evals/questions/xz.md`) it has four measured profiles (`env.example`). The strongest agent I have measured is Claude Fable 5.2 at max reasoning effort: 72.75 / 74, in 5,372 s, for about $50 (`evals/results/qa-xz-2026-11-13-fable-5-2-agents.md`). Against it:

| Profile | Score | Share of Fable 5.2 max's points | Cost, nine questions | Cheaper by | Time, nine questions | Faster by |
|---|---|---|---|---|---|---|
| **Full** | 70 / 74 | 96 % | $0.660 for six questions ¹ | about 50× ¹ | 435 s for six questions ¹ | 8.6× ¹ |
| **Cheap** | 68.75 / 74 | 94.5 % | $0.253 | about 196× | 519 s | 10.4× |
| **Hybrid-reliable** | 66.5 / 74 | 91.4 % | $0.135 | about 367× | 396 s | 13.6× |
| **Ultra-fast local** | 62.0 / 74 | 85.2 % | $0.161 | about 308× | 90.7 s | 59× |
| Claude Fable 5.2, max effort | 72.75 / 74 | — | about $50 (estimated) | — | 5,372 s | — |

¹ The Full run has complete footers for six of the nine questions (Q1, Q2, Q3, Q7, Q8, Q9). Its cost and time are compared with Fable 5.2 on those same six: about $33.21 and 3,752 s.

How to read the table:

- Fable 5.2's cost is an estimate from the tokens the harness reported, at list prices with prompt caching on ($42 to $57 for the nine; the table uses the middle). It is not a bill, and thinking tokens are not counted, so it is more likely too low than too high. Our costs are measured from the answer footers.
- Full and Cheap were measured on xz at `45d08abc` with the writer on Fireworks; Hybrid-reliable, Ultra-fast local and Fable 5.2 on xz at `7baf6835`, ours with the writer on Isoquant, which is cheaper.
- Ultra-fast local is the Jev-judge run of 2026-11-13; its eval file is not in `evals/results/` yet. The same profile with the pplx judges is (`qa-xz-2026-11-13-ultrafast-local-k40-pplx.md`: 62.25 / 74, $0.065, 12.1 s per answer).
- A later run of the ultra-fast profile, with the changes of 11-14 to 11-16, scored 64.0 / 74 with no wrong claim and nine of nine answers presentable as they are (`qa-xz-2026-11-16-ultrafast-improved.md`: $0.320, 8.0 s of evidence gathering per answer).
- One run per question for every row, and one grader (Claude Fable) for all of them.

Full also equals a Claude Opus 5.5 agent (70 / 74) and is above a Claude Fable 5.1 agent (69 / 74), both at high effort (`qa-xz-2026-10-29.md`). It started at 86.5% on 29/10; every retrieval change on the way is written up in `evals/results/`. The evaluator is done by a decision judge model (Jev, or the open-weights pplx-decider), not by the writer model that can be anything you want.

**Not only code: a help centre in Markdown.** The same engine was pointed at the Markdown of GitHub's documentation (github/docs at `a8dbaf5`: 3,805 articles, cut at their headings into 25,688 pieces) and asked nine questions an end user could ask, 50 reference points (`evals/questions/github-docs.md`). The agent to beat is Claude Fable 5.2 at high reasoning effort, with shell access to the same files:

| Mode | Score | Share of the agent's points | Wrong claims | Time, nine questions | Cost, nine questions |
|---|---|---|---|---|---|
| **High-reasoning** (writer thinks first; everything through OpenRouter) | 47.75 / 50 (95.5 %) | 98.5 % | 1 | 397 s (44 s per answer) | $0.091 ² |
| **Fast** (writer does not think; direct providers) | 46.0 / 50 (92.0 %) | 94.8 % | 1 | 57 s (6.4 s per answer) | writer $0.007; judge not reported ³ |
| Claude Fable 5.2 agent, high effort | 48.5 / 50 (97.0 %) | — | 0 found | 359 s (40 s per answer) | $3.76 ⁴ |

² Judge $0.070, as billed by OpenRouter (the answer footers). Writer $0.021: its measured tokens (103,771 in, 26,497 out) at the weighted average price OpenRouter's customers pay for DeepSeek V4.1 Flash ($0.02555 in, $0.6891 out per million, read 2026-11-23). OpenRouter picks a provider per request and the footer does not record which, so the writer's part is priced, not billed; at the cheapest and the dearest provider it would be $0.011 and $0.094.
³ Writer: its measured tokens at Isoquant's price. The fast run used the direct TypeSafe key, which reports no cost. The same judge work cost $0.070 through OpenRouter in the high-reasoning run (93 seeds and 168 bodies against 92 and 169).
⁴ The harness reported one figure for the agent: 188,180 tokens, 47 tool calls. Priced with the method of `qa-xz-2026-11-13-fable-5-2-agents.md` at Anthropic's list prices for Fable 5.2 with prompt caching on: cache write $1.88, cache read $0.90 to $1.81, output $0.52 (the nine answers only; no thinking tokens), so $3.30 to $4.21. The table uses the middle. It is a floor, not a bill.

How to read the table:

- High-reasoning is 0.75 points (1.5 percentage points) behind the agent, at 41 times lower cost ($0.091 against $3.76). It is not faster than the agent: 397 s against 359 s. Almost half of its time (190 s) is one step, the question's vector fetched through OpenRouter; with the direct provider that step took about 1 s per question.
- Fast is 2.5 points behind the agent and 6 times faster.
- The two modes differ in two things at once (the writer's thinking and the provider route), so the 1.75 points between them cannot be credited to thinking alone. What is measured: the evidence was the same in both (93 and 92 seeds, 168 and 169 bodies), and the points lost by the writer fell from 3.25 to 1.5. Evidence gathering lost 0.75 in both.
- A help article does not hold all its text: it includes shared files by name (`{% data reusables.a.b %}`). Following those names is what `JEV_POINTERS=1` does; the same questions scored 42.75 that morning, before it and `QA_SKIP_PATHS` existed.
- The agent was one agent for all nine questions, which is an easier setting than one fresh agent per question. Its cost is priced from the one token figure the harness reported (footnote ⁴), not a bill.
- One question (Q5) is the one the two new switches were developed on. One run per question, one grader (Claude Fable) for all three rows.
- Sources: `evals/results/qa-github-docs-2026-11-23-openrouter-reasoning-high.md`, `qa-github-docs-2026-11-23-pointers.md` (fast) and `qa-github-docs-2026-11-23-fable-5-2-agent.md` (the agent; its answers are in `evals/runs/fable-5-2-high-github-docs-2026-11-23/`).

The idea that a decision model, not a similarity search, should choose what the writer reads was reached independently by a Cornell group for document retrieval ("Retriever-Free Retrieval: Navigating Documents with Decision Models", arXiv 2610.35868, 26 October 2026, where the method is called DecisionRAG). Their method walks a hierarchy of topics, documents and passages without a first-stage retriever; unified-brain starts from an embedding search and follows names from one body to the next.

---

I invite you to fork the project and have a look for yourself! I firmly believe that memory intermediate structures combined with System One models will take AI capabilities to the next level soon.

The philosophy behind this venture is to address contemporary inference issues in SWE through architectural elegance, rather than relying primarily on brute force scaling.

```mermaid
flowchart TD
    classDef step fill:#2d3748,stroke:#4a5568,stroke-width:2px,color:#fff;
    classDef process fill:#2b6cb0,stroke:#3182ce,stroke-width:2px,color:#fff;

    Code["1. Raw Git Repository"]
    Entities["`2. Syntax-Isolated Entities
Functions, Types, Macros`"]:::step
    VectorDB["3. Structural Vector DB"]:::step
    Candidates["Candidate Subsets"]:::process
    Filtered["Precision Matches"]:::process
    Dynamic["`Judge-Guided Iterative Exploration
Follows Symbol References and Expands Evidence`"]:::process
    Writer["`Single LLM Call
Synthesizes the Answer from Gathered Evidence`"]:::step

    Code -->|Tree-sitter Parsing| Entities
    Entities -->|Embedding Pass| VectorDB
    VectorDB -->|Tier 1: Initial Retrieval| Candidates
    Candidates -->|Tier 2: Judge Re-Scoring| Filtered
    Filtered -->|Tier 3: Smart Grep Discovery| Dynamic
    Dynamic -->|Compiled Evidence| Writer
```

The judge is no longer tied to one vendor. On 2026-11-05 I wrote here that there was no parity between Jev and the open models I had tried; a day later pplx-decider (Perplexity's 27B decision model, Apache-2.0 licence with gated weights, $0.02 / M on OpenRouter) is the default judge. It is still a hosted model: the weights need an authorised token and Perplexity's own serving code, so running the judge on your own machine is not yet an option with either model. Measured on the same nine xz questions: Jev 70 / 74 at about 9 cents of judge cost per question ($0.49 for the nine); pplx-decider 68.75 / 74 at about 1 cent per question ($0.09 for the nine) with the cheap settings (`evals/results/qa-xz-2026-11-06-pplx.md`). With Jev's own settings pplx-decider scored 66.5 (`qa-xz-2026-11-05-b-pplx.md`), and another open 27B, Cloudflare Clef, scored lower at six times Jev's cost — so this is one model that works, not open models in general. Jev stays the coverage profile: 1.25 points ahead, for three times the judge cost.

With the fixed 400-call scoring step gone (35–204 judge calls per question now), a judge running on the user's own machine is the next thing to try.

## How it works

unified-brain reads a repository and stores every symbol — functions, types,
macros, config entries, and the sections of Markdown articles — using
tree-sitter, in one SQLite db inside the repository in question
(`<repo>/.unified-brain.db`). It can read the repository in two ways: the code
as it is now (a snapshot of the current commit, minutes), or the git history,
where every version of every symbol is stored with the commit that introduced
it. On top of that it answers two questions, as of any commit it has stored:

- **Ask** — "why does X do Y?", answered from the bodies that were live at the
  commits you pick, found by embeddings → a decision judge (pplx-decider or
  Jev: a small model that scores bodies and follows names through the code)
  → one write by the LLM of your choice.
- **Timeline / reports** — pick a range of commits and have every changed symbol
  judged: does the change do what the commit message says, or is there a defect
  or a malicious intent behind it? Each verdict comes with the evidence the
  judge was shown (diffs, same-commit changes, callers, the chains it followed).

No LLM is used during ingestion. One embedding pass runs at the end.

## Requirements

- Python 3.11 or newer (SQLite comes with it; nothing else to install or run)
- API keys: [OpenRouter](https://openrouter.ai) (the judge), one embedding provider —
  [Voyage AI](https://www.voyageai.com) or [DeepInfra](https://deepinfra.com)
  (Qwen3-Embedding-8B, cheaper) — and one writer provider (Isoquant or
  [Fireworks](https://fireworks.ai) for DeepSeek, or Anthropic).
  Or one OpenRouter key for all three (`ALL_VIA_OPENROUTER=1`, see step 1).

## Quick start

Everything below runs in a terminal, from the `unified-brain` folder, with the
virtual environment active. The examples use a clone of
[xz](https://github.com/tukaani-project/xz) at `~/code/xz`; use your own path.

### 1. Install

```bash
git clone https://github.com/DevLoops-ai/unified-brain.git
cd unified-brain
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env
```

Open `.env` and fill in Part 1. The minimum (comments only on their own
lines — python-dotenv reads `KEY=value  # text` as the value `# text`):

```
# the database the service answers about (written by step 2)
DB_PATH=/Users/you/code/xz/.unified-brain.db
# writer: isoquant = DeepSeek V4.1 Flash, 1017 build, on Isoquant with zero
#         data retention (Isoquant-ZDR: required); the writer of the evals
#         from 11-12 on. llmbase = the same model on Fireworks (the writer
#         of the first evals). Or anthropic.
LLM_PROVIDER=isoquant
LLM_API_KEY=...
# the judge (pplx-decider by default; typesafe/jev-1.14 for coverage), through OpenRouter
OPENROUTER_API_KEY=...
# code embeddings: qwen (the evals), or voyage (then set VOYAGE_API_KEY instead)
CODE_EMBED_PASS2=qwen
QA_VECTOR_STORE=qwen
DEEPINFRA_API_KEY=...
```

One key for everything: with `ALL_VIA_OPENROUTER=1` the judge, the writer and
the embeddings all go through OpenRouter, and `OPENROUTER_API_KEY` is the only
key you need (`LLM_API_KEY` and `DEEPINFRA_API_KEY` are then not used). The
writer is DeepSeek V4.1 Flash unless `OPENROUTER_LLM_MODEL` names another
model; the vectors are Qwen3-Embedding-8B served by DeepInfra, the same
vectors the ingest stores without the switch. It is the convenient setup, not
the fast one: on the help-centre questions the question's vector took 13 to
38 s per question through OpenRouter, against about 1 s from a direct provider.

### 2. See what will be indexed

Before ingesting, a few seconds show which files the ingester covers symbol
by symbol, which it stores whole, and which it skips (binary files are not
stored). 

```bash
python ingester.py ~/code/xz scan-coverage
```


### 3. Ingest a repository

The ingester reads the repository and writes one file,
`<repo>/.unified-brain.db`. No LLM is used; it is CPU work plus git. When the
code is in, the embedding pass runs once over the stored bodies.

The fast way — only the code as it is now, no history:

```bash
python next_claude.py ~/code/xz --snapshot
```

This ingests the current commit in one step, without walking the history
(open62541, a repository of about 13,000 commits: 143 seconds on an M3, 4
minutes 30 seconds with the embedding pass), then runs the embedding pass. It is enough to ask questions about the code as
it is today. The timeline starts at this commit; earlier commits are not in
the database.

`--snapshot` needs an empty database. Later commits are added one by one:

```bash
git pull
python next_claude.py ~/code/xz --resume
```

With history — a slice, so you see results in minutes:

```bash
# 1,349 commits of xz, from January 2021 (the threaded decoder work) to July 2024
python next_claude.py ~/code/xz \
  --since f7fa309e1f7178d04c7bedc03b73077639371e97 \
  --max 1349
```

`--since <ref>` starts after a commit or tag; `--max N` stops after N commits.
Progress prints one line per commit and a summary at the end
(`✅ 1349 commit(s) ingested … skills created=… updated=… obsoleted=…`),
then the embedding pass (`🧬 embedding pass [qwen] … 1943/1943`).

The whole history of a repository. The walk follows the main line only
(`git log --first-parent`); commits of a side branch arrive with their merge:

```bash
python next_claude.py ~/code/xz
```

On a laptop this takes a while (open62541: 13,474 commits in 96 minutes on an
M3, then 56 minutes of embedding). On macOS keep the machine awake with
`caffeinate`, in the same terminal:

```bash
caffeinate -i python next_claude.py ~/code/open62541
```

Stopped half-way (Ctrl+C, sleep, crash)? Continue from the last ingested commit:

```bash
python next_claude.py ~/code/xz --resume
```

To start over, delete the `.unified-brain.db` file.

A documentation repository (a help centre in Markdown) needs four more lines
in `.env`. The first two act when you ingest, the last two when you ask:

````
# cut each .md file at its headings (without it a .md file is one piece)
INGEST_MARKDOWN=1
# folders to leave out of the ingest, comma separated (here: 1,800 images)
INGEST_SKIP_PATHS=/assets/
# a name may contain hyphens (file names of shared texts usually do)
JEV_NAMES_TEXT=1
# follow the files and sections a text points to by name
JEV_POINTERS=1
````

Ingest with `--snapshot` as above (github/docs: 44,050 pieces in 30 minutes
on an M3, embedding included). Two more things to know:

- `QA_SKIP_PATHS=/src/` leaves folders out when you ask, with no new ingest:
  the bodies stay in the database, the search and the chains do not use
  them. On github/docs this removed the website's own code and data from the
  answers and cut the writer's input on one question from 849 k to 144 k
  characters.
- `JEV_POINTERS=1` was measured on Markdown only. Leave it out for a code
  repository until a results file says otherwise.

### 4. Embeddings (only if you need to redo them)

The ingest already runs the embedding pass for the provider in
`CODE_EMBED_PASS2`. Two cases need the separate commands:

```bash
# the ingest finished but the embedding pass did not (key missing, network):
python next_claude.py ~/code/xz --embed-only

# add or redo one provider's vectors on an existing database:
python reembed_code_vectors.py --provider voyage --db ~/code/xz/.unified-brain.db
python reembed_code_vectors.py --provider qwen   --db ~/code/xz/.unified-brain.db
```

Both providers can live in the same database; `QA_VECTOR_STORE` picks the one
questions use. Cost to expect: open62541's 277,080 body versions cost about
$1.30 with Qwen on DeepInfra. Add `--dry-run` to count without embedding.


### 5. Start the service

`DB_PATH` in `.env` must point at the database you want to ask about — one
service, one repository. Then:

```bash
python codebase_qa_service.py
```

Open http://127.0.0.1:8000 to ask questions and http://127.0.0.1:8000/timeline
for the commit timeline and reports. The server listens on localhost only.
Each answer ends with a line of numbers: time per phase, judge cost (the footer still labels it "Jev"), writer speed.
With a direct TypeSafe key (`JEV_URL`) the judge cost shows as $0.000: that route reports none.

The writer has two modes. `WRITER_REASONING=none`: it answers without thinking
first (the fast profiles). `WRITER_REASONING=high`, the default: it thinks
first; its thinking is billed as output tokens, and the first word comes when
the thinking ends (after 2 to 30 s on the help-centre questions).
Ctrl+C stops it.

To switch repositories, stop the service, change `DB_PATH`, start it again.

### 6. Give it to your coding agent (Cursor, Claude Code, any MCP client)

`unified_brain_mcp.py` is an MCP server with one tool, `retrieve`: the agent
hands over the question, gets back the evidence — every body that answers it,
with file, symbol and line — and writes the answer from it. It talks to the
running service, so step 5 must be running; when the service is stopped the
agent works without it and says so.

Cursor — `.cursor/mcp.json` in the project you are working on (Cursor settings
→ Customize → MCP shows it; use Agent mode):

```json
{"mcpServers": {"unified-brain": {
  "command": "/path/to/unified-brain/.venv/bin/python",
  "args": ["/path/to/unified-brain/unified_brain_mcp.py"],
  "env": {"UNIFIED_BRAIN_URL": "http://127.0.0.1:8000"}}}}
```

Claude Code — the same object in `.mcp.json`. The tool takes 20–60 seconds
(the judge is reading); ask the agent to use unified-brain for the question.

The service also answers plain HTTP for scripts: `POST /api/retrieve`,
`GET /api/grep`, `/api/symbol/{name}`, `/api/body`, `/api/history`,
`/api/commit/{hash}`.

## How it is built

| File | Role |
|---|---|
| `next_claude.py` | the `ingest` command: git history → the database file, then the embedding pass |
| `ingester.py` | reads commits and extracts symbols with tree-sitter (C, C++, Python, TypeScript, JavaScript, shell, CMake, make, YAML; m4, assembly and automake by regex; Markdown cut at its headings with `INGEST_MARKDOWN=1`) |
| `defkey_reconciler.py` | keeps the symbol index right as lines move, symbols change or disappear |
| `store.py` | the database: one SQLite file, with the text index for grep and the vector tables |
| `skills_lib.py` | the record layer: skills, bodies per commit, edges, code vectors, grep |
| `reembed_code_vectors.py` | the embedding pass (one set of vectors per stored body version) |
| `codebase_qa_service.py` | the FastAPI service: questions, timeline, reports, evidence |
| `templates.py` | the two pages |
| `unified_brain_mcp.py` | the MCP server for coding agents: one tool, `retrieve` (a thin client of the service) |

## Licence

AGPL-3.0, with a commercial licence available — see `LICENSING.md`.
Contributions need the CLA in `CLA.md`.

Copyright (c) 2026 DevLoops SINGLE MEMBER P.C.