# xz question set — fresh Claude Fable 5.2 agents, medium and max effort (2026-11-13)

A repeat of the agent comparison in `qa-xz-2026-10-29.md` ("Same
questions, answered by Claude Opus 5.5 and Claude Fable 5.1 agents"),
with the current model, run twice: once at the harness default effort
(medium) and once at max effort. Each run is nine fresh agents, one per
question, each given a clean checkout of xz and the question, and nothing
else.

Questions and keys: `evals/questions/xz.md` — nine questions, 74 reference
points. Answers: `evals/runs/fable-5-2-medium-xz-2026-11-13/` and
`evals/runs/fable-5-2-max-xz-2026-11-13/`.

## Read this first: what the two runs cost

| | medium effort | max effort | both |
|---|---|---|---|
| points | 69.25 / 74 | 72.75 / 74 | |
| time, nine questions summed | 990 s (16.5 min) | 5,372 s (89.5 min) | 106 min |
| time per answer | 110 s | 597 s (10 min) | |
| tool calls | 95 | 529 | 624 |
| tokens reported by the harness | 0.79 M | 2.29 M | 3.08 M |
| **cost at API list prices (estimate, a floor)** | **≈ $12** | **≈ $50 ($42 to $57)** | **≈ $62** |
| cost per answer (estimate) | ≈ $1.35 | ≈ $5.50 | |

- **On the author's subscription: after this day's session the account
  showed 86 % of the monthly allowance used.** That figure is for the
  whole session (the two agent runs, plus a long working conversation
  that graded about forty unified-brain answers the same day); the share
  of the two runs alone was not shown. It is consistent with the
  estimate: the two runs are the large items.
- The dollar figures are estimates, not a bill. The harness reported one
  token figure per agent and no transcript, so the October method
  (summing the `usage` field of every API call) could not be repeated.
  Thinking tokens are not counted, and max effort thinks a lot, so the
  max figure is more likely too low than too high. Method below.
- For scale: the unified-brain ultra-fast profile answered the same nine
  questions the same day for $0.16 in total, in 91 s.

## Setup (both runs)

- Model: Claude Fable 5.2 (`claude-fable-5-2`), the general-purpose agent
  of the Claude Code harness.
  - Medium run: effort not set, i.e. the harness default. Anthropic's
    launch note for Fable 5.2 gives Medium as the default in Claude Code;
    the run itself does not report the level.
  - Max run: effort set to `max`.
  - The October run (Fable 5.1, Opus 5.5) used high.
- Source: xz at `7baf6835`, a fresh clone in its own folder for each run
  (the October run used `45d08abc`).
- Each agent got shell, grep and file reading. It was told to use only the
  checkout: no other folder, no web, no memory or past-conversation tools.
  None of them saw the keys, the grading, or any other answer.
- The prompt is the same for all nine agents of a run, word for word; it
  is printed at the top of each answer file. Q7 is the original question
  (no added clause).
- The nine agents of a run ran **at the same time**. Time is each agent's
  own wall-clock, exploring and writing together.
- One run per question per effort level, no re-run.

Differences between the two runs:

- Medium: agents wrote their answer to a file and repeated it in the
  reply (the prompt asked for both), so the answer is paid for twice in
  output tokens. Max: reply only, no files written.
- Max: before the run, the keys, the grading notes and the medium run's
  answers were packed into an archive and the open copies removed from
  the machine, so an agent could not read them even by breaking the rule.
  A separate machine was requested and refused by the harness; both runs
  are on the grader's machine. The author's uploaded files of the day
  (unified-brain answers and logs, no keys) stayed on disk in both runs.
- The max Q4 agent ran the system's `xz` 5.4.5 on the fixtures and rebuilt
  two of them from the README recipe, in memory. That is inside the rules
  as written (nothing was written to disk), but it is more than reading.

Grading: reference points hit, same keys. Graded by Claude Fable 5.2 in
the session that built and graded the unified-brain runs of the same day;
concrete claims were spot-checked in the source. The grader is the same
model as the contestant and knew which system each answer came from. Its
grades moved by about a quarter point between gradings on the same day,
so a gap of 0.5 or less between two systems is "level". Above 70 points
that drift is a large part of what is left.

## Results per question

Time, tool calls and tokens are what the harness reported for each agent.
`est. $` is the estimate described below.

| Q | topic | medium score | medium time s | medium calls | medium tokens | medium est. $ | max score | max time s | max calls | max tokens | max est. $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | 4.0 / 4 | 52 | 8 | 54.2 k | 0.77 | 4.0 / 4 | 308 | 36 | 135.8 k | 2.40 |
| 2 | sandboxing | 5.0 / 5 | 85 | 5 | 68.6 k | 0.99 | 5.0 / 5 | 435 | 55 | 176.7 k | 3.70 |
| 3 | full decompression path | 9.0 / 10 | 164 | 12 | 118.6 k | 1.90 | 9.75 / 10 | 583 | 63 | 399.0 k | 8.45 |
| 4 | test fixture integrity | 7.0 / 7 | 113 | 15 | 99.6 k | 1.56 | 7.0 / 7 | 758 | 87 | 329.3 k | 8.30 |
| 5 | padding, next stream, garbage | 6.25 / 7 | 67 | 6 | 63.9 k | 0.89 | 7.0 / 7 | 457 | 62 | 214.2 k | 4.64 |
| 6 | memory limit, threaded decoder | 4.75 / 6 | 81 | 8 | 70.6 k | 1.05 | 5.75 / 6 | 404 | 43 | 184.2 k | 3.42 |
| 7 | when xz deletes the input | 6.0 / 6 | 75 | 9 | 67.0 k | 1.02 | 6.0 / 6 | 311 | 35 | 162.1 k | 2.81 |
| 8 | attacker modifies the Index | 5.5 / 6 | 109 | 12 | 93.3 k | 1.41 | 5.5 / 6 | 999 | 65 | 328.4 k | 7.06 |
| 9 | long concatenated-streams question | 21.75 / 23 | 245 | 20 | 157.1 k | 2.59 | 22.75 / 23 | 1,115 | 83 | 357.3 k | 8.79 |
| **total** | | **69.25 / 74 (93.6 %)** | **990** | **95** | **793 k** | **≈ 12.2** | **72.75 / 74 (98.3 %)** | **5,372** | **529** | **2,287 k** | **≈ 49.6** |

No wrong claims were found in either run.

Time per answer, max run: 5.1 min (Q1), 7.3 (Q2), 9.7 (Q3), 12.6 (Q4),
7.6 (Q5), 6.7 (Q6), 5.2 (Q7), 16.6 (Q8), 18.6 (Q9).

What max effort bought over medium: +3.5 points (Q3 +0.75, Q5 +0.75,
Q6 +1.0, Q9 +1.0; five questions unchanged) for 5.4× the time, 5.6× the
tool calls, 2.9× the reported tokens and about 4× the estimated cost.

## Against the other arms

| | Fable 5.2 max | Fable 5.2 medium | Opus 5.5 (10-29) | Fable 5.1 (10-29) | ultra-fast local, Jev chains (11-13, run 2) |
|---|---|---|---|---|---|
| points | 72.75 (98.3 %) | 69.25 (93.6 %) | 70 (94.6 %) | 69 (93.2 %) | 62.0 (83.8 %) |
| wrong claims | 0 | 0 | 0 | 0 | 4 (all Q8) |
| time, average | 597 s | 110 s | 131 s | 193 s | 10.1 s |
| tool calls | 529 | 95 | 153 | 204 | — |
| cost, nine questions | ≈ $50 (estimated) | ≈ $12 (estimated) | $6.84 (measured) | $17.55 (measured) | $0.161 |
| cost per answer | ≈ $5.50 | ≈ $1.35 | $0.76 | $1.95 | $0.018 |
| effort | max | default (medium) | high | high | — |
| xz commit | `7baf6835` | `7baf6835` | `45d08abc` | `45d08abc` | `7baf6835` |

Per question:

| Q | Fable 5.2 max | Fable 5.2 medium | Opus 5.5 | Fable 5.1 | ultra-fast (run 2) |
|---|---|---|---|---|---|
| 1 | 4.0 | 4.0 | 4.0 | 4.0 | 4.0 |
| 2 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 |
| 3 | **9.75** | 9.0 | 9.5 | 9.5 | 8.5 |
| 4 | **7.0** | **7.0** | 6.5 | 5.5 | 4.25 |
| 5 | **7.0** | 6.25 | **7.0** | 6.5 | 5.25 |
| 6 | **5.75** | 4.75 | 4.5 | 5.0 | 5.25 |
| 7 | 6.0 | 6.0 | 6.0 | 6.0 | 4.5 |
| 8 | 5.5 | 5.5 | 5.5 | 5.5 | 4.5 |
| 9 | **22.75** | 21.75 | 22.0 | 22.0 | 20.75 |
| **total** | **72.75** | **69.25** | **70** | **69** | **62.0** |

The ultra-fast column is the second full run of 2026-11-13 (top 40, local
question vector, pplx seed scoring, Jev chains, 2 hops; all nine questions
in their original wording). Its eval file is not written yet; the numbers
are from the grading notes of that day.

The fast profile reaches 62.0 of 72.75 points (85 %) of the max run in
1.7 % of the time and about 0.3 % of the estimated cost; against the
medium run, 90 % of the points in 9 % of the time and about 1.3 % of the
cost.

## Where points were lost

Medium run (4.75 lost):

- Q3 (−1.0): `auto_decoder.c` not opened, so no first-byte rules (−0.4);
  the other containers named but not read (−0.2); no `LZMA_TIMED_OUT` →
  `LZMA_OK`, no `rc_is_fast_allowed()`, LZMA rep paths only as state
  names (−0.4). It does read `simple_code()` (BCJ) and `delta_decode()`.
- Q5 (−0.75): no fixture named, and "padding has no CRC" not said.
- Q6 (−1.25): `tests/test_memlimit.c` never opened (−1.0); no `base.h`
  note, no `LZMA_TIMED_OUT` mapping (−0.25).
- Q8 (−0.5): `SEQ_INDEX_WAIT_OUTPUT` not named.
- Q9 (−1.25): allocation failures (`LZMA_MEM_ERROR`) not in the answer
  (−1.0); no `base.h` note, inflated and deflated sizes not separated
  (−0.25).

Max run (1.25 lost):

- Q3 (−0.25): `rc_is_fast_allowed()` and `is_size_valid()` not named.
- Q6 (−0.25): no `base.h` note on the ≤ 5.2.6 bug; the Index-hash append
  after a direct-mode Block not mentioned.
- Q8 (−0.5): `SEQ_INDEX_WAIT_OUTPUT` still not named, after 16.6 minutes
  and 65 tool calls. The same half point was lost by Opus 5.5, Fable 5.1
  and the medium run. (The Q9 agent of the max run does name it.)
- Q9 (−0.25): the survive-then-fail list is spread over two tables and
  does not separate inflated from deflated sizes; allocation failure is
  one line without the thread stop.

Full marks — medium: Q1, Q2, Q4, Q7. Max: Q1, Q2, Q4, Q5, Q7.

## What stands out

- **Q4 is 7 / 7 in both runs, the first full scores on it by any system.**
  Both found the SPDX exemption in `build-aux/license-check.sh`
  (`PAT_UNTAGGED_0BSD`: `^tests/files/[^/]+\.(lz|lzma|xz)$` and
  `xzgrep_expected_output`), which Opus 5.5, Fable 5.1 and every
  unified-brain profile missed, and both read the body of
  `tuktest_file_from_x()` (64 MiB limit, short read).
- **Q7 is 6 / 6 on the original question in both runs.** The agents open
  `io_open_src_real()` on their own; the fast profile needs the added
  clause for that (4.5 without, 5.75 with).
- **Q6:** at medium effort the fast profile wins (5.25 against 4.75; the
  agent did not open the test). At max effort the agent opens it and
  leads (5.75).
- **Q8:** both runs describe `lzma_index_hash_size()` correctly (computed
  from the Blocks). The fast profile gets this wrong in most runs because
  the function is named in the last hop and not read.
- **Diminishing returns.** Five of nine questions scored the same at max
  as at medium. On those five, max effort spent 47 minutes and about $24
  (estimated) for depth the key does not ask for.

Findings beyond the keys, verified in the source by the grader:

- Max Q4: the comment at `tests/test_lzip_decoder.c:27` says
  `0x15A2A343` is the CRC32 of `"Hello\nWorld\n"`. Computed: that string
  gives `0xdb588331`; `0x15A2A343` is the CRC32 of `"Hello\nWorld!\n"`.
  The medium run and the fast profile repeated the comment.
- Max Q5: in `lzma_stream_buffer_decode()`
  (`stream_buffer_decoder.c` 53–70) the positions are restored to their
  start values before the test `*in_pos == in_size`, so that test compares
  the start position. Read, not run.
- Max Q4: `tests/tests.cmake` passes one argument (`".."`) to
  `test_files.sh`, and the script takes the `xzdec` folder from a second
  argument, so the `xzdec` half is probably skipped under CMake. Both
  lines confirmed; no CMake build was run.
- Both Q4: `tests/test_compress.sh` has a `compress_prepared_*` branch but
  no such file exists at this commit; the README and the directory list
  the same 95 fixtures.

Not verified by the grader: max Q8's table of which check catches each
repository `bad-*index*` fixture under full decode, `xz -l` and `xz -lvv`
(from the agent's own in-memory model, stated as such); max Q2's
observation that `ruleset_fd` is never closed; max Q9's observation that
the memory figure `xz` prints after `LZMA_MEMLIMIT_ERROR` is not the need
of the refused Block.

## How the cost was estimated

The harness reported one token figure per agent. The estimate treats that
figure as the size of the agent's final context and prices it at
Anthropic's list prices for Fable 5.2 (read 2026-11-13: $8 input, $10
five-minute cache write, $0.20 cache read, $40 output, per M tokens),
with prompt caching on:

| part | medium | max |
|---|---|---|
| cache write: the whole final context, once | $7.93 | $22.87 |
| cache read: (tool calls + 1) turns, each re-reading part of the final context | $1.24 to $2.06 (60–100 %) | $14.86 to $29.71 (50–100 %) |
| output: the answer and the tool-call text; **no thinking tokens** | ≈ $2.60 (answer written twice) | ≈ $4.43 |
| **total** | **$11.8 to $12.6** | **$42 to $57** |

The tables use the middle of each range. The October Fable 5.1 numbers
have the same shape when run through this method (Q1 measured: 66.3 k
cache write, 430 k cache read, 4.3 k output, $1.15), which is why the
method is trusted to roughly ±25 % for the medium run. For the max run it
is weaker: the cache-read share is large and depends on how the context
grew, and thinking is not counted. Two things could move both: if the
harness shares one cached prompt prefix between the nine agents the cache
writes are lower; if the reported figure is not the final context the
whole estimate is off.

The one independent check is the subscription meter (86 % of the month
after the session), which fits "tens of dollars of API-equivalent use",
not "a few dollars".

## What this comparison is and is not

- Same questions, same keys, same day and same source tree as the
  unified-brain runs of 2026-11-13.
- Not the same conditions as the October agent runs: other xz commit,
  medium and max effort instead of high, nine agents in parallel, a
  different prompt wording, and an estimated cost instead of a measured
  one. The scores are comparable; the time and cost columns are
  indicative.
- A frontier model with shell access against a system whose writer is a
  $0.035 / M model. The question answered is "how much of a frontier
  agent's answer does the fast profile reach, and at what time and
  price".
- xz is a well-known codebase. The agents were told to answer from the
  checkout and they cite it, but what the model already knew about xz
  cannot be separated out.
- Answer files: the medium files are what each agent wrote to disk (for
  Q2 the agent's reply had three small accuracy fixes that its file
  lacks; the grade is from the reply). The max files were saved by the
  grader from each agent's reply, since those agents wrote no files.
