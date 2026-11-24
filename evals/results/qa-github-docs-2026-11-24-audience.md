# github-docs question set — answers written for a customer (2026-11-24)

The third unified-brain results file on the Markdown of GitHub's
documentation (github.com/github/docs). The question behind this run:
can the answers be shown to a customer of a help centre as they are,
and what does that cost in points?

Questions and keys: `evals/questions/github-docs.md` — nine questions,
50 reference points. The keys were not changed for this run.

Code: commit `0ce04e8` (2026-11-24 12:36) plus two changes that were
not committed at the time of the run: `QA_INLINE_TAG` and
`WRITER_AUDIENCE`. Both are described under "What is new".
Index: the index of the 2026-11-23 runs (github/docs at `a8dbaf5e`,
`INGEST_MARKDOWN=1`, `src/` in the index and left out at question time).
No new ingest was made for this run.
Judges: Jev 1.14 for seed scoring, chain verdicts and triage, with the
direct TypeSafe key. That route reports no cost, so every footer shows
"Jev $0.000". The judge cost of this run is not known.
Writer: `WRITER_REASONING=high`, `ALL_VIA_OPENROUTER=0`. The writer's
model and provider line was not in the `.env` block pasted for this
run. TO CONFIRM before publishing: the 2026-11-23 direct run used
DeepSeek V4.1 Flash on Isoquant. No writer cost is given below for
that reason; the token counts are.
Question vector: Qwen3-Embedding-8B hosted on Fireworks, computed fresh
for every question (no cache).

Four things to know before reading the numbers:

- The questions were asked in this order: Q5, Q9, Q8, Q7, Q6, Q4, Q3,
  Q2, Q1, between 13:49 and 13:55 (Athens). One run each, no reruns.
- The same nine questions were asked about 20 minutes earlier with the
  same `.env` and `ALL_VIA_OPENROUTER=1`. That run has no file of its
  own; its numbers are in the comparison below, from the session
  record. The run of this file is the second of the two, not a pick of
  the better one per question.
- Q5 and Q9 were also asked earlier the same day while the two new
  switches were being tried (Q5 7.5 with inline tags and no audience
  line; Q9 5.0 with inline tags and no audience line).
- Against the published runs of 2026-11-23, more than one thing
  changed: the path step and the judge's view of blank lines (both in
  `0ce04e8`), the inline tags, and the audience line. This file does
  not separate their effects.

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
WRITER_REASONING=high
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

# switches of 11-24
JEV_PLAIN_BLANKS=1
QA_INLINE_TAG='{% data PATH %}'
WRITER_AUDIENCE='a customer reading a help centre. Answer the customer directly. Do not mention the evidence, files, or source tags; say which plan or version a rule applies to in plain words.'
```

This block is the `.env` as pasted at 13:57, right after the run. Notes:

- `INGEST_SKIP_PATHS` reads `/assets/,/src/`, but the index was made
  with `/assets/` only. The `/src/` part had no effect on this run.
- `JEV_EXPAND_MAX_ADD` appeared twice in the file (200, then 0); the
  later line is the one listed.

## What is new against the runs of 2026-11-23

Evidence gathering (both in commit `0ce04e8`):

- The path step of `JEV_POINTERS`: a path written in a body, such as
  `reusables.gated-features.pages`, offers the file at exactly that
  folder and name. Before, a name was offered only when few files had
  it, and `pages` is the name of 17 files.
- `JEV_PLAIN_BLANKS=1`: the judge reads a body without the marker lines
  the ingest stores for blank lines.

What the writer reads and how it answers (not committed at run time):

- `QA_INLINE_TAG='{% data PATH %}'`: in the text given to the writer, a
  tag of this shape is replaced by the value its path points to in the
  index. `{% data variables.product.prodname_pages %}` becomes
  `GitHub Pages`. Only tags that end at one key with a plain value are
  replaced; a tag that includes a whole file stays. Nothing is kept
  after the answer and there is no glossary file. The judge and the
  chains still read the raw tags.
- `WRITER_AUDIENCE`: one line that says who reads the answer. When
  set, it takes the place of the style line of the writer's prompt
  ("Technical precision; cite exact symbols, files, and lines."). The
  rest of the prompt is unchanged.

## Results

| Q | topic | score | published 11-23, reasoning high | wrong claims | presentable | evidence s | total s | seeds | bodies | chars | tokens in | tokens out |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Actions time limits | 4.5 / 5 | 5.0 | 2 | yes | 3.2 | 5.3 | 6 | 12 | 32 k | 8,618 | 1,249 |
| 2 | forks on delete and visibility change | 4.25 / 5 | 5.0 | 0 | yes | 3.6 | 9.4 | 16 | 22 | 52 k | 12,294 | 1,428 |
| 3 | 2FA app set up by hand | 4.0 / 4 | 4.0 | 0 | yes | 2.9 | 3.9 | 3 | 4 | 6 k | 1,824 | 522 |
| 4 | retention of logs and artifacts | 5.25 / 6 | 5.5 | 0 | yes | 3.6 | 6.6 | 19 | 23 | 53 k | 13,417 | 1,160 |
| 5 | linear history and signed commits | 7.75 / 8 | 7.0 | 0 | yes | 5.4 | 16.2 | 17 | 46 | 133 k | 33,092 | 2,094 |
| 6 | SMS codes in Nigeria on Enterprise Server | 6.0 / 6 | 5.75 | 0 | yes | 3.4 | 6.7 | 12 | 18 | 46 k | 11,724 | 1,279 |
| 7 | locked out, phone lost | 5.75 / 6 | 6.0 | 0 | yes | 2.8 | 7.6 | 7 | 17 | 38 k | 9,355 | 1,721 |
| 8 | REST API requests per hour | 5.0 / 5 | 4.75 | 0 | yes | 4.3 | 6.9 | 8 | 11 | 22 k | 5,786 | 1,030 |
| 9 | GitHub Pages for a small shop | 4.75 / 5 | 4.75 | 0 | yes | 2.9 | 6.2 | 5 | 9 | 23 k | 5,926 | 1,261 |
| **total** | | **47.25 / 50 (94.5 %)** | **47.75 (95.5 %)** | **2** | **9 of 9** | **32.2** | **68.8** | **93** | **162** | **406 k** | **102,036** | **11,744** |

Per answer: evidence gathering 3.6 s on average (2.8 to 5.4 s); total
7.6 s on average (3.9 to 16.2 s).

How the columns were filled:

- seconds, seeds, bodies, characters and tokens are the footer of each
  answer. Evidence seconds = search + seed scoring + chains.
- There is no judge $ column: the direct key reports no cost. There is
  no writer $ column: see "Writer" at the top.
- "wrong claims" counts statements that contradict the source. Claims
  were checked against a clone of github/docs at the same commit.
- "presentable" is the grader's judgement: could this answer be shown
  to a customer as it is. In the two files of 2026-11-23 the same
  column asked the question for an end user in general; an answer with
  file paths and "the evidence shows" could pass there. Read with the
  stricter question of this file, none of the nine answers of the
  published reasoning-high run passes.

## The runs side by side

| | this run | same `.env`, via OpenRouter, 20 minutes earlier | published 11-23, OpenRouter, reasoning high | published 11-23, direct, reasoning off | Fable 5.2 agent, high |
|---|---|---|---|---|---|
| points | 47.25 | 46.75 | 47.75 | 46.0 | 48.5 |
| lost to the writer | 2.0 | 2.75 | 1.5 | 3.25 | — |
| lost to evidence gathering | 0.75 | 0.5 | 0.75 | 0.75 | — |
| time, nine answers | 68.8 s | 301.9 s | 397 s | 57 s | 359 s |
| writer tokens out | 11,744 | 44,735 | 26,497 | 11,723 | — |
| audience line | on | on | off | off | — |

Per question, the two runs of today:

| Q | this run (direct) | via OpenRouter |
|---|---|---|
| 1 | 4.5 | 5.0 |
| 2 | 4.25 | 4.0 |
| 3 | 4.0 | 3.5 |
| 4 | 5.25 | 5.75 |
| 5 | 7.75 | 7.75 |
| 6 | 6.0 | 5.75 |
| 7 | 5.75 | 5.5 |
| 8 | 5.0 | 5.0 |
| 9 | 4.75 | 4.5 |

Two things happened on the OpenRouter route and not on the direct one,
with the same `WRITER_REASONING=high`:

- Three answers came after a long wait: first token at 33.5 s (Q1),
  71.2 s (Q2) and 62.5 s (Q7), with 7,631, 15,511 and 13,234 tokens out
  for answers of normal length. On the direct route the first token
  came after 0.6 to 7.3 s on every question.
- The Q2 answer was broken: its first section was the writer's own
  thinking printed as text. It is the one answer of that run that is
  not presentable.

Which provider served those calls was not recorded.

## Where the time goes

| step | seconds over nine questions | share |
|---|---|---|
| search (question vector on Fireworks + vector search) | 10.2 | 15 % |
| seed scoring (40 calls, one round) | 2.7 | 4 % |
| chains (2 hops, a triage and a verdict round each) | 19.3 | 28 % |
| writer | 36.4 | 53 % |

## Where the points went

2.75 points lost over the nine questions:

| cause | points | where |
|---|---|---|
| writer (the fact was in a body it read) | 2.0 | Q1 0.5, Q2 0.75, Q4 0.25, Q5 0.25, Q7 0.25 |
| evidence gathering (a file named in a seed was not opened) | 0.75 | Q4 0.5, Q9 0.25 |

The two evidence misses are the same two small shared files as on
2026-11-23: `checks-and-statuses-retention-scope.md` (Q4) and
`no_sensitive_data_pages.md` (Q9). In the OpenRouter run of the same
day both were opened on one question each (Q4, and Q9 in an earlier
try), so they come in on some runs and not on others. The logs of this
run were not read.

## Per question

- Q1 4.5 / 5. All limits, the 30-day approval time kept apart from the
  35-day limit. Two wrong statements: it gives the 24-hour queue limit
  as general (the table has that row under "Self-hosted" only), and it
  says the 45-minute window is "listed as not increasable" (it is not
  in the table). Writer.
- Q2 4.25 / 5. Three cases right, both Enterprise Server passages
  marked as such. One of the two other table rows is missing, and the
  line that Git data stays reachable in the network after a fork is
  deleted. Writer.
- Q3 4.0 / 4. All seven values, and the context: the setup key is the
  TOTP secret, how to set up several devices. 3.9 s.
- Q4 5.25 / 6. Default, both ranges with internal repositories on
  Enterprise Cloud, Enterprise Server, not retroactive, the October 1
  change. Caches named apart, with their own numbers. Lost: the scope
  sentence on third-party integrations (file not opened) and where to
  click (writer).
- Q5 7.75 / 8. Every point but the write permission. No wrong claim.
  Three true extras: the 100-commit limit of "Rebase and merge",
  stacked pull requests, vigilant mode. On 2026-11-23 the Enterprise
  Server branch of `required-signed-commits.md` was missed in both
  published runs; it is here.
- Q6 6.0 / 6. First full score on this question in any run. "No"
  twice in the opening, then what to use instead, and the note that an
  organization can block members who use SMS.
- Q7 5.75 / 6. All six steps and all time and policy points. It lists
  "a fallback number" among the ways back in without saying that it is
  no longer supported. Writer.
- Q8 5.0 / 5. A table with the four numbers and the Enterprise Cloud
  ones, shared budgets with the docs' example, per-installation limits.
- Q9 4.75 / 5. "No" to the shop and to the private repository on the
  Free plan; the soft limits marked as hosted plans only, in plain
  words; private repository kept apart from a privately published
  site. Missing: no passwords or credit card numbers (file not opened).

## What this run shows, and what it does not

- With one line on who the reader is, and tag values put in place of
  the tags, all nine answers can be shown to a customer: no file
  paths, no "the evidence shows", no raw `{% data … %}` tags. The
  version tags are said in words ("on GitHub Enterprise Server", "on
  GitHub's hosted plans").
- The score is 0.5 under the published reasoning-high run and 1.25
  under the Fable 5.2 agent, in 68.8 s for the nine answers.
- The answers are shorter, and the points lost to the writer are
  mostly things left out: a table row (Q2), a click path (Q4), a
  permission (Q5). The key gives points for some of these as
  "for completeness".
- Not measured: the judge cost and the writer cost of this run; each
  of the four changes alone; the same settings on xz and open62541
  (`QA_INLINE_TAG` and `WRITER_AUDIENCE` are off unless set, so the
  code runs are not affected by them).
- Each question was asked once. On the same code Q5 has scored between
  7.0 and 7.75 on other runs of these two days, so a difference of
  half a point between two runs is inside what one question can move.