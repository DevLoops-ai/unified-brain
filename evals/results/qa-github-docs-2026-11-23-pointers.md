# github-docs question set — Markdown as the source, pointers followed (2026-11-23)

The first results file for a help centre. The source is not code: it is
the Markdown of GitHub's own documentation (github.com/github/docs). The
question behind the run: can unified-brain be used as RAG on Markdown?

Questions and keys: `evals/questions/github-docs.md` — nine questions,
50 reference points.

Code: the working copy of the run, committed 39 minutes after it as
`4febaa5` (2026-11-23 15:16). The changes are listed under "What is
new" below.
Index: one `--snapshot` ingest of github/docs at `a8dbaf5e`, with
`INGEST_MARKDOWN=1` and `INGEST_SKIP_PATHS=/assets/`. It took 30
minutes. The `src/` folder (website code and large JSON data, 3,906
files) IS in the index; this run leaves it out at question time with
`QA_SKIP_PATHS=/src/`. The embedding pass ended with failed batches, so
some pieces have no vector (the first ingest of the same tree: 43,650
vectors stored, 2 failed batches; the count of this ingest was not
recorded).
Judges: Jev 1.14 for seed scoring, chain verdicts and triage, with the
direct TypeSafe key. That route reports no cost, so every footer shows
"Jev $0.000". The judge cost of this run is not known.
Writer: DeepSeek V4.1 Flash on Isoquant ($0.035 / M in, $0.30 / M out),
reasoning off.
Question vector: Qwen3-Embedding-8B hosted on Fireworks, computed fresh
for every question (no cache).

Four things to know before reading the numbers:

- The questions were asked in this order: Q5, Q4, Q3, Q2, Q1, Q6, Q7,
  Q8, Q9, between 14:29 and 14:37 (Athens).
- Q5 is the question the two new switches were developed on. It was
  asked four times earlier the same day under other settings (4.75,
  4.75, 4.75 without the pointers; 7.0 with the pointers and with
  `src/` still in). The Q5 row below is the first run under the final
  settings. The other eight are one run each, no reruns.
- The keys were written by the grader before the first run. The Q1 key
  was corrected once, after the baseline run found a fact the key had
  wrong (the 45-minute queue limit of GitHub-hosted runners). The
  correction is dated in the questions file.
- The baseline in the comparison column is a run of the same morning
  with `JEV_POINTERS` and `QA_SKIP_PATHS` not set. It has no results
  file; its numbers are from the session record. It ran on the first
  ingest of the same tree, this run on the second.

## Settings

```properties
# judges (direct TypeSafe key)
JEV_URL=https://api.typesafe.ai/v1/systemone
JEV_MODEL=jev-1.14.0
JEV_TRIAGE_MODEL=jev-1.14.0
JEV_SELECT_MODEL=jev-1.14.0

# seeds: top 40, scored, cut at 1.9
JEV_PREFILTER_TOP_K=40
JEV_MIN_SCORE=1.9

# ultra-fast profile
JEV_EXPAND_MAX_HOPS=2
JEV_FINAL_PASS=0
JEV_SEARCH_AHEAD=1
JEV_CONCURRENCY=256
JEV_PREV_BODY_MAX_CHARS=15000
JEV_TRIAGE_DEFS=1
JEV_TRIAGE_NAMES=1
JEV_TRIAGE_REOPEN=1
JEV_TRIAGE_FROM=2
JEV_RETRY_BAND=0
JEV_HIT_TRIAGE=1
JEV_NAMES_AS_CHOICE=1
JEV_QUESTION_GREP=0
WRITER_REASONING=none
QA_PLAIN_MARKERS=1

# question vector
QUERY_EMBED_URL=https://api.fireworks.ai/inference/v1/embeddings
QUERY_EMBED_MODEL=fireworks/qwen3-embedding-8b
QUERY_EMBED_OLLAMA=
QUESTION_VECTOR_CACHE=0

# switches of 11-14 to 11-16
JEV_HELPER_ORDER=1
JEV_HELPER_MIN_ACCEPT=0.15
JEV_HELPER_KEEP=1
JEV_EXPAND_MAX_CHARS=0
JEV_EXPAND_MAX_ADD=0
JEV_EXPAND_PER_NODE=1000
JEV_EXPAND_BUDGET=0
JEV_LEADS_MAX=1000
JEV_NAMES_ALL=1
JEV_SEED_NAMES=2
JEV_LOCAL_VERDICT=2

# switches of 11-23 (Markdown)
ALL_VIA_OPENROUTER=0
INGEST_MARKDOWN=1
JEV_NAMES_TEXT=1
INGEST_SKIP_PATHS=/assets/,/src/
QA_SKIP_PATHS=/src/
EMBED_WINDOW_LONG=1
JEV_POINTERS=1
```

This block is the `.env` as pasted at 14:40, right after the run. Check
it against the `.env` before publishing. Notes on it:

- `INGEST_SKIP_PATHS` reads `/assets/,/src/` in the block, but the
  index of this run was made with `/assets/` only. The `/src/` part was
  added after the ingest and had no effect on this run.
- `JEV_EXPAND_MAX_ADD` appeared twice in the file (200, then 0); the
  later line is the one listed.
- Not set: `JEV_SEED_SCORING` and `JEV_FLAT` (defaults: scoring on,
  rounds), `JEV_TRIAGE_FROM_HOP` (default: triage from the first hop),
  `JEV_STATE_MAX_TOKENS` (so one Jev call carries at most 60,000
  characters of state).

## What is new against the xz runs

Index:

- `INGEST_MARKDOWN=1`: a `.md` file is cut at its headings with the
  tree-sitter Markdown grammar. One piece per heading, named by its
  heading path; the text above the first heading stays as the file's
  top piece. Without the switch a `.md` file is one piece. On this
  tree: 3,805 articles gave 25,688 pieces; the whole index has 44,050.
- `INGEST_SKIP_PATHS`: folders the ingest leaves out. Here the 1,803
  images under `assets/`, which made the first ingest very slow.
- `EMBED_WINDOW_LONG=1`: a body with no stored parts is embedded in
  windows of lines.

Evidence gathering:

- `JEV_NAMES_TEXT=1`: a name may contain hyphens
  (`checks-and-statuses-retention-scope` is one name, not four words).
- `JEV_POINTERS=1`: every body the chain reads, seed or not, also
  offers (a) each file whose name appears in it and is not a symbol,
  and (b) for the top piece of an article, the sections cut out of it.
  All of them go through the "(definitions)" triage, where Jev sees the
  first lines of each place. Reason: an article includes a shared file
  with a tag such as `{% data reusables.pull_requests.rebase_and_merge_verification %}`.
  As one name among all the words of a body, that name lost the name
  choice (0.06 against a best of 0.36 on Q5).
- `QA_SKIP_PATHS=/src/`: files the search and the chains do not use,
  with no new ingest. The bodies stay in the index.

Providers: `ALL_VIA_OPENROUTER` (off in this run) sends the judges, the
writer and the vectors through OpenRouter with one key.

## Results

| Q | topic | score | baseline, same morning | wrong claims | presentable | writer $ | evidence s | total s | seeds | bodies | chars |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Actions time limits | 4.5 / 5 | 5.0 | 1 | no (one wrong cell in the summary table) | 0.0008 | 3.1 | 6.0 | 6 | 14 | 40 k |
| 2 | forks on delete and visibility change | 4.25 / 5 | 4.0 | 0 | yes | 0.0007 | 3.8 | 6.1 | 16 | 22 | 52 k |
| 3 | 2FA app set up by hand | 3.75 / 4 | 3.75 | 0 | yes | 0.0002 | 3.0 | 3.6 | 3 | 4 | 6 k |
| 4 | retention of logs and artifacts | 5.5 / 6 | 5.5 | 0 | yes | 0.0009 | 3.2 | 5.7 | 19 | 25 | 57 k |
| 5 | linear history and signed commits | 7.0 / 8 | 5.0 | 0 | yes, with blemishes | 0.0020 | 5.2 | 11.1 | 16 | 50 | 144 k |
| 6 | SMS codes in Nigeria on Enterprise Server | 5.5 / 6 | 5.25 | 0 | short answer yes, body no (raw tags) | 0.0009 | 3.4 | 7.1 | 12 | 18 | 46 k |
| 7 | locked out, phone lost | 6.0 / 6 | 5.0 | 0 | yes | 0.0007 | 2.6 | 6.0 | 7 | 16 | 36 k |
| 8 | REST API requests per hour | 4.75 / 5 | 4.75 | 0 | yes | 0.0006 | 4.1 | 6.6 | 7 | 11 | 24 k |
| 9 | GitHub Pages for a small shop | 4.75 / 5 | 4.5 | 0 | yes | 0.0005 | 2.8 | 5.0 | 6 | 9 | 18 k |
| **total** | | **46.0 / 50 (92.0 %)** | **42.75 (85.5 %)** | **1** | **7 of 9** | **0.0072** | **31** | **57** | **92** | **169** | **423 k** |

Per answer: evidence gathering 3.5 s on average (2.6 to 5.2 s); total
6.4 s on average (3.6 to 11.1 s). The writer read 105,710 tokens and
wrote 11,723 over the nine answers.

How the columns were filled:

- seconds, seeds, bodies and characters are the footer of each answer.
  Evidence seconds = search + seed scoring + chains.
- writer $ is computed from the footer's token counts at the prices
  above. It was not billed separately.
- There is no judge $ column: the direct key reports no cost.
- "wrong claims" counts statements that contradict the source. Claims
  were checked against a clone of github/docs at the same commit.
- "presentable" is the grader's judgement: could this answer be shown
  to an end user as it is.

Against the baseline of the same morning:

| | this run | baseline (no pointers, `src/` in) |
|---|---|---|
| points | 46.0 / 50 (92.0 %) | 42.75 (85.5 %) |
| points lost to evidence gathering | 0.75 | 4.75 |
| points lost to the writer | 3.25 | 2.5 |
| wrong claims | 1 | 0 |
| presentable as it is | 7 of 9 | 7 of 9 |
| time, nine answers | 57 s | 62 s |
| writer $ | 0.007 | about 0.006 |

## What the two switches did, measured on Q5

| | no switch (three runs) | pointers | pointers + `QA_SKIP_PATHS=/src/` |
|---|---|---|---|
| score | 4.75, 4.75, 4.75 | 7.0 | 7.0 |
| chains | 4.3 to 5.1 s | 9.9 s | 3.4 s |
| judged / triage calls | 117–119 / 23–24 | 171 / 48 | 124 / 39 |
| characters to the writer | 814 k to 1,103 k | 849 k | 144 k |
| first token | 5.2 to 7.3 s | 5.4 s | 2.0 s |
| total | 14.8 to 17.5 s | 20.8 s | 11.1 s |

- The pointers brought the two files that hold the key fact
  (`rebase_and_merge_verification.md` and `_2.md`): with required signed
  commits, "Rebase and merge" on GitHub adds commits without signature
  verification.
- Without `QA_SKIP_PATHS`, 14 copies of `src/rest/data/*/branches.json`
  and other JSON files of `src/` were most of the writer's input.
  Leaving `src/` out at question time gave back more speed than the
  pointers cost.

## Where the time goes

| step | seconds over nine questions | share |
|---|---|---|
| search (question vector on Fireworks + vector search) | 10.4 | 18 % |
| seed scoring (40 calls, one round) | 2.7 | 5 % |
| chains (2 hops, a triage and a verdict round each) | 18.0 | 32 % |
| writer | 25.9 | 45 % |

Writer speed per question, tokens per second: Q1 458, Q2 479, Q3 459,
Q4 578, Q5 407, Q6 408, Q7 427, Q8 461, Q9 513.

## Where the points went

Four points lost over the nine questions:

| cause | points | where |
|---|---|---|
| writer (the fact was in a body it read) | 3.25 | Q1 0.5, Q2 0.75, Q3 0.25, Q5 1.0, Q6 0.5, Q8 0.25 |
| evidence gathering (a file named in a seed was not opened) | 0.75 | Q4 0.5, Q9 0.25 |

The two evidence misses are small shared files:
`checks-and-statuses-retention-scope.md` (Q4) and
`no_sensitive_data_pages.md` (Q9). Each is named in a seed, so the
pointer step offered it to the triage. The logs of these two questions
were not read, so whether the triage said no is not confirmed.

## Per question

- Q1 4.5 / 5. All limits right in the text, the 30-day approval time
  kept apart from the 35-day workflow limit. The summary table and one
  later paragraph give 24 hours as the queue limit for GitHub-hosted
  runners too; the limits table marks that row "Self-hosted", and the
  answer itself gives the right 45 minutes further down. Writer.
- Q2 4.25 / 5. Three cases right, both Enterprise Server passages
  marked as such. It quotes two rows of the four-row table and skips
  the other two. It found a real disagreement between two sections of
  the visibility article and says so. Writer.
- Q3 3.75 / 4. All seven values. The reusable file came in through the
  chain (score under the seed cut). Half of one tip is missing. The
  cleanest answer of the run.
- Q4 5.5 / 6. Default, both ranges, Enterprise Server, not retroactive,
  the October 1 change. The cache is mentioned apart, not mixed in. The
  scope sentence on third-party integrations is missing (file not
  opened). It calls the October 1 change "today" still pending; the
  docs word it that way and the writer has no date.
- Q5 7.0 / 8. The key fact and its workaround are there, and the
  squash trap. It found that two articles disagree on whether rebasing
  a stack gives signed commits. Lost: the `{% else %}` branch of
  `required-signed-commits.md` (on Enterprise Server a pull request
  cannot be merged on GitHub when signed commits are required) and the
  write permission. Blemishes: "evidence 2" numbers, raw tags inside
  quotes, mentions of the docs repository's own ruleset files.
- Q6 5.5 / 6. "No" twice, in the first lines; no steps for adding a
  phone number. Reasons against SMS are thin and the recovery codes are
  not mentioned, though both were in its input. The body is full of raw
  `{% ifversion %}` tags and one sentence is garbled.
- Q7 6.0 / 6. Full marks. The four step files came in through the
  chain; the article itself holds only the tags. No raw tags in the
  answer.
- Q8 4.75 / 5. All four numbers, `GITHUB_TOKEN` at 1,000 per
  repository, shared budgets with the docs' example. Missing: requests
  with no token are for public data only.
- Q9 4.75 / 5. "No" in the first line, limits called soft and marked
  as GitHub.com plans only, Free plan needs a public repository.
  Missing: no passwords or credit card numbers (file not opened).

## What this run shows, and what it does not

- Search on heading-sized pieces works for prose, and with the pointers
  followed the evidence is nearly complete: 0.75 of 50 points lost to
  it.
- The writer is now the larger loss. Three patterns repeat: it leaves
  raw `{% … %}` tags in its quotes; it has ignored an `{% else %}`
  branch on Q5 in every run; it shortens a table or a tip it has in
  front of it.
- Not measured: the judge cost; the effect of `JEV_POINTERS=1` on a
  code project (xz and open62541 were not run with it; a C file's
  `#include "common.h"` would offer `common.h` at every body, so those
  results would change); an index made without `src/`.
- On Q5, before `QA_SKIP_PATHS` was set, one Jev triage call failed in
  each of the two hops (`max_tokens_exceeded`); when a triage call
  fails, every place of that group is opened. The cause was not traced,
  and no log of the final run was read to see if it still happens.