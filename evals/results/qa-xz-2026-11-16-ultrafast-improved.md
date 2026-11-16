# xz question set — ultra-fast improved (2026-11-16)

Code: working copy with uncommitted changes on top of the pushed
repository. The exact commit of this run was not recorded. The changes
are listed under "What is new" below.
xz index: one `--snapshot` ingest of the whole tree at `45d08abc`,
made on 11-14. It was NOT ingested again after the comment change of
11-16 (a comment directly above a function is stored with that
function), so this run does not have that change. The open62541 index
used at the end of this file does.
Judges: Jev 1.14 for chain verdicts and triage, pplx-decider 1.2 for
seed scoring, both through OpenRouter.
Writer: DeepSeek V4.1 Flash on Isoquant ($0.035 / M in, $0.30 / M out),
reasoning off.
Question vector: Qwen3-Embedding-8B hosted on Fireworks, computed fresh
for every question (no cache).
One run per question, no reruns.

Three things to know before reading the numbers:

- The questions were asked in reverse order: Q9, Q8, Q7, Q6, Q5, Q4,
  Q3, Q2, Q1, between 21:16 and 21:26.
- Q7 was asked with its original wording (without the clause
  "including files that xz refuses to process at all").
- The writer's speed moved between 87 and 744 tokens per second inside
  these ten minutes. The total times below are therefore not a fair
  measure of the setting. The evidence-gathering times are.

## Settings

```properties
# judges
JEV_MODEL=typesafe/jev-1.14
JEV_TRIAGE_MODEL=typesafe/jev-1.14
JEV_SELECT_MODEL=perplexity/pplx-decider-v1.2

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
```

This block is the `.env` as pasted at 21:09, a few minutes before the
run. Check it against the `.env` before publishing. Not set in it:
`JEV_SEED_SCORING` and `JEV_FLAT` (defaults: scoring on, rounds),
`JEV_TRIAGE_FROM_HOP` (default: triage from the first hop),
`JEV_STATE_MAX_TOKENS` (so one Jev call carries at most 60,000
characters of state). `JEV_EXPAND_MAX_ADD` appeared twice in the file
(200, then 0); the later line is the one listed.

## What is new against the ultra-fast local runs of 11-13

Index:

- The ingester walks the main line only (`--first-parent`) and can
  ingest the current tree in one step (`--snapshot`). The xz index now
  holds every file of the tree (3,098 pieces; the earlier slice had
  1,943).
- A comment directly above a function or declaration is stored with it
  (11-16). Not in the xz index of this run; see the note at the top.

Evidence gathering:

- Jev also picks which names to follow from each seed
  (`JEV_SEED_NAMES=2`), on top of opening the definitions a seed uses.
- Every name of a body is offered to Jev, in groups of up to 254
  (`JEV_NAMES_ALL=1`). The fixed limits on names are off.
- No limit on the number of definitions opened per body, on calls per
  hop, or on the text the chains may add
  (`JEV_EXPAND_PER_NODE=1000`, `JEV_EXPAND_BUDGET=0`,
  `JEV_EXPAND_MAX_CHARS=0`, `JEV_EXPAND_MAX_ADD=0`).
- A helper (a body Jev marked "follow it", next to accepted evidence)
  reaches the writer only when Jev says the writer needs it
  (`JEV_HELPER_KEEP=1`).
- A body reached through a mention is cut to the lines around that
  mention when Jev says those lines are evidence and the rest is not
  needed (`JEV_LOCAL_VERDICT=2`).
- A failed Jev call no longer stops the chains.

Question vector: hosted on Fireworks (was computed on the laptop).

## Results

| Q | topic | score | 11-13 Jev chains (two runs) | wrong claims | presentable | judge $ | writer $ | total $ | evidence s | total s | seeds | bodies | chars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | 3.75 / 4 | 3.75, 4.0 | 0 | yes | 0.011 | 0.0010 | 0.012 | 4.0 | 13.4 | 2 | 6 | 61 k |
| 2 | sandboxing | 5.0 / 5 | 5.0, 5.0 | 0 | yes | 0.023 | 0.0032 | 0.026 | 7.0 | 11.8 | 22 | 31 | 248 k |
| 3 | full decompression path | 8.75 / 10 | 9.0, 8.5 | 0 | yes | 0.072 | 0.0057 | 0.078 | 14.2 | 45.5 | 24 | 151 | 422 k |
| 4 | test fixture integrity | 5.0 / 7 | 4.5, 4.25 | 0 | yes | 0.028 | 0.0022 | 0.030 | 7.3 | 11.7 | 8 | 41 | 119 k |
| 5 | padding, next stream, garbage | 6.25 / 7 | 5.25, 5.25 | 0 | yes | 0.044 | 0.0034 | 0.047 | 7.8 | 19.7 | 6 | 35 | 281 k |
| 6 | memory limit, threaded decoder | 5.25 / 6 | 5.25, 5.25 | 0 | yes | 0.016 | 0.0014 | 0.017 | 6.1 | 9.1 | 5 | 9 | 73 k |
| 7 | when xz deletes the input (original) | 5.0 / 6 | 4.5 (one run) | 0 | yes | 0.026 | 0.0022 | 0.028 | 7.2 | 25.7 | 8 | 20 | 162 k |
| 8 | attacker modifies the Index | 5.0 / 6 | 4.75, 4.5 | 0 | yes, minus its last two sentences | 0.023 | 0.0031 | 0.026 | 5.3 | 39.2 | 6 | 33 | 194 k |
| 9 | long concatenated-streams question | 20.0 / 23 | 20.25, 20.75 | 0 | yes | 0.050 | 0.0052 | 0.055 | 13.1 | 39.8 | 15 | 103 | 321 k |
| **total** | | **64.0 / 74 (86.5 %)** | **62.5 and 62.0** | **0** | **9 of 9** | **0.293** | **0.027** | **0.320** | **72** | **216** | **96** | **429** | **1.88 M** |

Per answer: $0.036 on average ($0.012 to $0.078); evidence gathering
8.0 s on average (4.0 to 14.2 s); total 24.0 s on average (9.1 to
45.5 s, see the note on the writer's speed).

How the columns were filled:

- judge $, seconds, seeds, bodies and characters are the footer of each
  answer. Evidence seconds = search + seed scoring + chains.
- writer $ is computed from the footer's token counts at the prices
  above. It was not billed separately.
- "wrong claims" counts statements that contradict the source. Three
  answers have one loose or misleading sentence each that is not
  counted (Q1, Q3, Q8); they are described under "Per question".
- "presentable" is the grader's judgement: could this answer be shown
  to an end user as it is.
- The 11-13 column is the two runs of the same profile with Jev in the
  chains (63.5 with Q7 asked with the clause, about 62.5 with the
  original Q7; and 62.0). Those two runs have no results file; the
  numbers are from the session record.

Against the other arms:

| | this run | ultra-fast local, Jev chains 11-13 (two runs) | ultra-fast local, flash chains 11-13 | reliable hybrid 11-12 | Fable 5.1 agent |
|---|---|---|---|---|---|
| points | 64.0 / 74 (86.5 %) | about 62.5 and 62.0 | 62.25 (84.1 %) | 66.5 (89.9 %) | 69 (93.2 %) |
| judge $ | 0.293 | 0.137 and 0.134 | 0.043 | 0.095 | — |
| total $ | 0.320 | about 0.164 and 0.161 | 0.065 | 0.135 | 17.55 |
| time s | 216 | 85 and 91 | 109 | 396 | 1,736 |

Against the agent: 5 points behind, about 55 times cheaper, 8 times
faster. Against the same profile on 11-13: 1.5 to 2 points more, about
twice the cost, and (on this evening's writer speed) 2.4 times the
time.

## Where the time goes

| step | seconds over nine questions | share |
|---|---|---|
| search (question vector on Fireworks + vector search) | 6.4 | 3 % |
| seed scoring (40 calls, one round) | 15.5 | 7 % |
| chains (2 hops, a triage and a verdict round each) | 50.1 | 23 % |
| writer | 143.9 | 67 % |

- Search is 0.6 to 0.9 s per question with the hosted question vector.
- Chains: 1.9 s (Q1, 40 calls) to 12.3 s (Q3, 514 calls). Per-hop
  timing lines were switched off in this run (`JEV_CALL_TIMES`), so
  there is no split into rounds.
- Writer speed per question, tokens per second: Q1 87, Q2 531, Q3 118,
  Q4 683, Q5 165, Q6 744, Q7 89, Q8 112, Q9 222. On the three fast ones
  the whole answer took 9.1 to 11.8 s.

## Where the points went

Ten points lost over the nine questions:

| cause | points |
|---|---|
| writer (the fact was in a body it read) | 5.25 |
| judge (a name it was offered and did not follow, or a body it rejected) | 2.5 |
| not delivered, cause not traced without the logs | 2.25 |

The judge's 2.5 are three cases that repeat in every run of this
profile: `tests/test_compress.sh` and `build-aux/license-check.sh` on
Q4, and the BCJ filters on Q3.

## Per question

- Q1 3.75 / 4. Both `.S` files, the guard and its comment, the whole
  Autotools path, and the case where the file is assembled but the note
  is skipped (mingw, cygwin, djgpp). −0.25: C sources never emit the
  note themselves; `CMakeLists.txt` was not read. One loose sentence:
  "a linux*/*bsd* i?86 host satisfies both gates" (the guard asks for
  FreeBSD, not any BSD); its first paragraph has it right.
- Q2 5.0 / 5. Three mechanisms with their version floors, the three
  levels in `xz`, the strict-mode condition, the pre-loading of locale
  data, `xzdec`'s own copy. Version floors, `xzdec`'s "last file only"
  rule and the `ENOSYS` exception verified in source.
- Q3 8.75 / 10. All stages in order with the hand-offs. −0.5 BCJ
  filters not reached. −0.5 the `xz` tool's own format detection and
  its first `lzma_code()` call with no output space. −0.25
  `LZMA_TIMED_OUT` turned into `LZMA_OK`. One loose phrase about
  `LZMA_RANGE_DECODER_CONFIG`. 151 bodies and $0.072 for the same score
  as 11-13.
- Q4 5.0 / 7. Loader constraints, CRC32 of decoded output, each bad
  file pinned to its error, `test_files.sh`, and the negative
  conclusion (nothing verifies fixture bytes) stated first. −1.0
  `test_compress.sh` / `create_compress_files.c`. −1.0
  `license-check.sh`. Mentions "blob descriptions", which is the
  index's wording and means nothing to a user.
- Q5 6.25 / 7. The three-way split, the modulo-4 counter, each error
  case, and the backward parser in `file_info.c`. Gets the trap right:
  garbage is never detected as garbage. −0.25 the header shorter than
  12 bytes. −0.5 the test files in `tests/files/README`.
- Q6 5.25 / 6. Both limits, the hard-limit path, direct mode, the
  waiting condition, and for the first time on this profile the
  `LZMA_MEM_ERROR` on allocation failure. −0.5 the `xz` functions that
  set the limits. −0.25 direct mode for an unknown block size.
- Q7 5.0 / 6. The one deletion site and its three conditions, the
  forced keep, the identity check, the destination removed on failure,
  plus a failed destination close and the `--force` weakness. −0.75
  when `success` becomes true. −0.25 non-regular files.
- Q8 5.0 / 6. Twelve checks in order, the survive-then-fail cases, the
  difference between the standalone Index decoder and real
  decompression. −0.75 the threaded side. −0.25 errors returned
  directly. Its last two sentences speak of an attacker "recomputing"
  the size-pair hash; that hash is not stored in the file.
- Q9 20.0 / 23. Every stage and every failure case with state, whether
  more input helps, and the returned status. −1.0 `LZMA_MEM_ERROR` on
  allocation failure. −0.5 two Index sub-cases not spelled out. −1.0
  the fixture files and the format document not cited. −0.5 no CRC on
  padding; which `xz` functions set the limits.

## Reading

- Quality: the highest ultra-fast total so far, and no answer with a
  statement that contradicts the source.
- Cost: about twice the 11-13 runs. Q3, Q5 and Q9 take $0.166 of the
  $0.293. On Q3 and Q9 the extra calls bought no point; on Q5 they
  bought one.
- Size: 1.88 M characters to the writer over nine questions (559,007
  tokens). Large documents weigh the most: `configure.ac`,
  `CMakeLists.txt`, `INSTALL`, `NEWS`, `xz.1`,
  `doc/xz-file-format.txt`.
- Time: needs a second run. The evidence gathering is 4 to 14 s; the
  rest is the writer's provider.

## The same setting on three open62541 questions (same evening)

One run each, 21:07 to 21:13, index: `--snapshot` of open62541 with the
comment change.

| Q | topic | score | wrong claims | presentable | judge $ | total s | seeds | bodies |
|---|---|---|---|---|---|---|---|---|
| 6 | PublishRequests, lifetime, Republish | 5.75 / 8 | 0 | yes | 0.021 | 19.4 | 9 | 36 |
| 7 | MonitoredItem sampling and overflow | 6.0 / 8 | 2 | only the overflow part | 0.017 | 13.5 | 11 | 18 |
| 8 | AddNodes from a type | 8.5 / 10 | 1 | yes, with care on one line | 0.030 | 27.5 | 17 | 56 |
| **total** | | **20.25 / 26 (77.9 %)** | **3** | | **0.068** | **60** | | |

The Q8 key gives 0.5 for two entry functions that run before the point
the question starts from; the key is to be corrected. The 20-seed
setting without seed scoring scored 23.25 / 26 on these three on 11-14,
at about $0.11 for the three.

## Open

- A second full run, to separate the setting from the writer's speed.
- The same run on an xz index ingested with the comment change. That is
  a different index, so it goes in a new dated file.
- The same nine questions with the switches of 11-14 to 11-16 off, to
  price them: they look worth about 2 points and about $0.018 per
  answer.
- Logs of this run were not kept with the answers; the split of the
  2.25 "not delivered" points needs them.
- Results files for the two 11-13 Jev-chains runs do not exist.