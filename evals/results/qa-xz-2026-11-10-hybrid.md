# xz — question answering, run of 2026-11-10 hybrid (two judge models: pplx-decider for seeds and triage, pplx-decider-flash for the chain verdicts)

**This is a configuration run, not a one-change run.** The day started
from a marketing question (how fast and how cheap can the evidence
gathering be) and tried three judge setups on the cheap profile of
`qa-xz-2026-11-06-pplx.md`: Jev with the retry on, pplx-decider-flash
alone, and the hybrid recorded here. Only the hybrid was run on all nine
questions; the other two are listed below as partial arms so the trail is
complete. The next file should return to one change per run, with this
file as the baseline for the hybrid and `qa-xz-2026-11-06-pplx.md` as the
baseline for the full model.

Setting, against the cheap profile of 2026-11-06:

```
JEV_MODEL=perplexity/pplx-decider-flash-v1.2   (11-06: perplexity/pplx-decider-v1.2)  chain verdicts, name choice, final pass
JEV_SELECT_MODEL=perplexity/pplx-decider-v1.2  (new)  seed scoring
JEV_TRIAGE_MODEL=perplexity/pplx-decider-v1.2  (new)  hit triage and definitions triage
JEV_RETRY_BAND=0.10                            (11-06: 0)  second call near a cut, the permissive answer kept
JEV_PREFILTER_TOP_K=20                         (as 11-06)
JEV_PREV_BODY_MAX_CHARS=15000                  (as 11-06)
JEV_TRIAGE_DEFS=1                              (as 11-06)
```

Everything else as 11-06: `JEV_HIT_TRIAGE=1`, `JEV_NAMES_AS_CHOICE=1`,
`JEV_EXPAND_MAX_ADD=200`, `JEV_TRIAGE_FROM=2`, `JEV_QUESTION_GREP=0`,
`JEV_SURE_REJECT=0.75`, `JEV_DERIVED_MIN=0.65`, `JEV_FOLLOW_MIN=0.5`.
`JEV_BATCH_SIBLINGS=0` was also in the `.env`. The thresholds are still
Jev's; none was tuned to either pplx model.

So four things differ from the 11-06 run, not one:

1. the chain-verdict model (flash, 4B, $0.01 / M in; the full model is
   27B at $0.02 / M),
2. `JEV_RETRY_BAND` (0 → 0.10),
3. the writer's provider (Isoquant `deepseek-v4.1-flash-1017-fast`;
   11-06 used DeepSeek V4.1 Flash on Fireworks),
4. the grader (Claude Fable 5.2; the earlier files were graded by Fable
   5.1).

Code: the working copy this file is committed with. It adds the two
settings above to `codebase_qa_service.py` (`_jev_select` uses
`JEV_SELECT_MODEL`, `_jev_triage_hits` uses `JEV_TRIAGE_MODEL`; both
default to `JEV_MODEL`, so nothing changes until they are set).

**What the logs confirm and what they do not.** The seed scoring on the
full model is confirmed: the sample select call is billed at $0.02 / M
(409 tokens, $0.00000818). The chain verdicts on flash are confirmed:
they carry the same probabilities, to two decimals, as the flash-only
run of the same question. The triage model is not printed in the log.
It is consistent with the full model (between the two Q4 runs the flash
verdicts are identical and only two triage scores move, by 0.02), but
that is an inference. Database: not printed in the log either; the
answers quote the tree of the earlier files (line numbers match
`45d08abc` with the usual +1).

Same nine questions and keys (`evals/questions/xz.md`), one run per
question in the order Q4, Q6, Q3, Q9, Q8, Q7, Q5, Q2, Q1, 18:05–19:00
local time, plus a second run of Q4 (below). Every concrete claim graded
was checked against the xz tree at `7baf6835`, which differs from
`45d08abc` only in `AUTHORS` and `THANKS`. Q8 item (3) was graded under
the key correction of the 11-06 file (a non-minimal VLI encoding is
rejected by the VLI decoder, not by the `index_list_size` comparison);
the pushed `evals/questions/xz.md` still carries the old wording for that
item.

## Results

| Q | topic | this run | pplx cheap 11-06 | run f (Jev) | wrong | judge $ | writer $ | total $ | time s | retrieval s | calls | seeds | bodies | chars in |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | 3.25 / 4 | 4 | 4 | 1 | 0.002 | 0.001 | 0.004 | 35 | 8 | 36 | 2 | 4 | 50 k |
| 2 | sandboxing | 4.75 / 5 | 4.75 | 5 | 0 | 0.004 | 0.004 | 0.008 | 28 | 12 | 90 | 12 | 26 | 232 k |
| 3 | full decompression path | 8.75 / 10 | 9.5 | 10 | 1 | 0.009 | 0.005 | 0.014 | 72 | 24 | 231 | 10 | 52 | 203 k |
| 4 | test fixture integrity | 4.0 / 7 | 6.5 | 5.5 | 0 | 0.006 | 0.003 | 0.008 | 37 | 25 | 133 | 4 | 23 | 114 k |
| 5 | padding / next stream / garbage | 5.25 / 7 | 5.25 | 6.5 | 0 | 0.002 | 0.003 | 0.005 | 41 | 9 | 46 | 3 | 5 | 74 k |
| 6 | MT memory limit | **5.75 / 6** | 5.75 | 6 | 0 | 0.008 | 0.003 | 0.011 | 45 | 28 | 180 | 5 | 36 | 152 k |
| 7 | when xz deletes the input | 5.0 / 6 | 5.5 | 5.5 | 0 | 0.004 | 0.002 | 0.007 | 20 | 10 | 65 | 6 | 11 | 114 k |
| 8 | attacker modifies the Index | 5.5 / 6 | 5.5 | 5.5 | 0 | 0.006 | 0.006 | 0.012 | 66 | 13 | 123 | 4 | 21 | 170 k |
| 9 | the long concatenated-streams question | 20.25 / 23 | 22 | 22 | 0 | 0.009 | 0.008 | 0.016 | 94 | 18 | 181 | 11 | 47 | 182 k |
| **total** | | **62.5 / 74 (84.5 %)** | **68.75** | **70** | **2** | **0.051** | **0.035** | **0.086** | **437** | **149** | **1,085** | **57** | **225** | **1.29 M** |

Columns as in the 11-06 file: judge $ from the footer (the footer prints
"Jev $"; here it is the two pplx models together, as billed), time =
footer total, retrieval = search + seed scoring + chains, calls = select
judgements (20) + chain judgements + triage calls. Writer $ is computed
from the footer's token counts (388 k in, 72 k out over the nine) at the
Isoquant price of $0.035 / M in and $0.30 / M out; the 11-06 file used
the Fireworks list price ($0.22 / $0.66), so the writer and total
columns of the two files are not comparable. Totals are sums of the
unrounded values.

Against the cheap profile on the full model: **−6.25 points at 55 % of
the judge cost** ($0.051 vs $0.092), 14 % more calls, retrieval 149 s vs
206 s. Equal on four questions (Q2, Q5, Q6, Q8), behind on five. Two
thirds of the gap is three questions: Q4 (−2.5), Q9 (−1.75), Q3 (−0.75).

Time. The `search` step took 6.7 / 13.9 / 7.5 / 6.1 s on Q3 / Q4 / Q6 /
Q9 against the normal 1–1.5 s — the embedding of the question, not the
judge; about 29 s of the 149. Without it the retrieval is near 120 s.
The two files were run on different days, so the difference to 206 s is
an indication, not a measurement of flash against the full model.

Wrong claims, two:

- Q1: DragonFly listed as a BSD host that matches `*bsd*` in
  `configure.ac`; its host name is `dragonfly*`. From the writer's own
  knowledge, not from the evidence. −0.25.
- Q3: `lzma_check_finish()` placed in `SEQ_CHECK`, twice; it runs at the
  end of `SEQ_PADDING`. −0.25.

Not deducted: on Q3 `dict_put` "line 44" and `dict_write` "line 43" of
`lz_decoder.h` (they are at 195 and 219); on Q8 the heading "SHA-256"
for a check the text below correctly calls `LZMA_CHECK_BEST`.

## Per question

- Q1 3.25 / 4. Both files, the guard and its comment, the Autotools gate
  with the small-build and CRC64 conditions, and one thing no earlier
  run had: `--enable-assembler=x86` given explicitly skips the host
  check (`configure.ac:360-374`). −0.5 the CMake side (`XZ_ASM_I386`):
  `CMakeLists.txt` was read and left as a lead. −0.25 DragonFly.
- Q2 4.75 / 5. Same 12 seeds as 11-06 and nearly the same bodies (26 vs
  25). −0.25: strict also needs output to stdout, and why `--files`
  rules it out; `main()` was in context (accept 0.63). The same quarter
  as 11-06.
- Q3 8.75 / 10. All stages in order with the hand-offs, `auto_decode()`
  included, the threaded variant, the four containers. −1.0 point 9:
  delta not mentioned although `delta_decode` was in context (0.58), and
  BCJ `simple_code()` not reached. −0.25 the `lzma_check_finish` slip.
- Q4 4.0 / 7, both runs. Loader complete, `basic_lzip_decode` with the
  CRC of the output, the three behaviours of `test_crc`, `test_files.sh`
  complete (the `-qQ` test correctly tied to `unsupported-check.xz`),
  the negative conclusion. Lost: `decode_expect_error` (1.0),
  `test_compress.sh` and the fixed seed (1.0), the `license-check.sh`
  exemption (1.0).
- Q5 5.25 / 7. The same run as 11-06: 3 seeds, 5 bodies, the same three
  lost items (header outcome codes 1.0, the mt decoder 0.5, fixtures
  0.25).
- Q6 **5.75 / 6**. The fullest Q6 of any pplx arm: both limits with the
  `xz` wiring through `coder_init()` and `hardware.c` (including
  `total_ram / 4`, the default the 11-06 run did not write), hard check
  first, direct mode, the wait, all three allocation failures and the
  different handling of a failed Block decoder init, the counters, the
  test. −0.25: the Index hash append after a direct-mode Block, and
  "unknown size" as a reason for direct mode.
- Q7 5.0 / 6. −0.5 the `success` rule inside `coder_normal()`
  (`coder_normal` offered at 0.33 from `coder_run`, not followed). −0.5
  the files that are never processed (`io_open_src_real` among the
  skipped definitions; what the answer has comes from `xz.1`).
- Q8 5.5 / 6. The survive-then-fail section is complete, including the
  swapped-records case worked through check by check and the
  non-minimal VLI case under the corrected key. −0.5
  `SEQ_INDEX_WAIT_OUTPUT` not named, the same half as every run
  (`stream_decode_mt` in context, accept 0.66).
- Q9 20.25 / 23. Own 3.25 / 4 (the Footer's CRC32 and reserved-flag
  outcomes; no fixtures, format document or `container.h` among the
  confirmations). Q5 part 6.25 (header codes, fixtures). Q6 part 5
  (allocation failures missing; `stream_decode_mt` was a seed at 2.88).
  Q8 part 5.75 (the VLI case not drawn). 11 seeds as on 11-06, 47 bodies
  against 75.

## Where the points were lost

Eleven and a half points.

**Writer, 3.25** — the fact was in the evidence:

| Q | lost | where it was |
|---|---|---|
| 1 | 0.25 DragonFly | not in the evidence at all; the writer added it |
| 2 | 0.25 strict needs stdout | `main()` body |
| 3 | 0.5 delta; 0.25 `lzma_check_finish` placement | `delta_decode` body; `block_decode` body |
| 6 | 0.25 Index hash append, unknown size | `stream_decode_mt` body |
| 8 | 0.5 `SEQ_INDEX_WAIT_OUTPUT` | `stream_decode_mt` body |
| 9 | 1.0 allocation failures; 0.25 the VLI case | `stream_decode_mt` body; the format document |

**Judge, flash, 3.75** — the body or the name was offered and flash said no:

| Q | lost | what the judge did |
|---|---|---|
| 1 | 0.5 CMake side | `CMakeLists.txt <module>` read, reject 0.65, final 0.59: a lead only. Kept by the full model on 11-06 |
| 4 | 1.0 `license-check.sh` | read, reject 0.85. The 11-06 run kept that point |
| 4 | 1.0 `decode_expect_error` | `test_lzip_decoder.c <module>` accepted at 0.69 with "(none of these)" 0.65, so no name was followed; `basic_lzip_decode`: 2 places, 2 skipped at hop 3 |
| 7 | 0.5 `coder_normal()` | offered at 0.33 from `coder_run`, "(none of these)" 0.67 |
| 9 | 0.75 fixtures | `tests/files/README <module>` read, reject 0.84 |

**Judge, the full model's triage, 2.25** — the same hole as on 11-06:

| Q | lost | what the triage did |
|---|---|---|
| 5 | 1.0 header outcome codes | the definitions of `stream_decode`: 15 places, 15 skipped. Fifth run in a row |
| 7 | 0.5 files never processed | the definitions under `io_close_src` / `io_unlink`: 4 of 4, 4 of 4, 11 of 12 skipped; `io_open_src_real` not read |
| 9 | 0.75 header and Footer codes | the definitions of `stream_decode_mt`: 13 places, 10 skipped |

**Chain, 1.75** — no road, or the names step did not offer it:

| Q | lost | where the road ended |
|---|---|---|
| 3 | 0.5 BCJ `simple_code()` | `filter_decoder`: 5 places, 4 skipped; as on 11-06 |
| 4 | 1.0 `test_compress.sh`, the fixed seed | `test_compress` offered at 0.02; `create_compress_files` at 0.29, but from `.gitignore`, a body flash rejected, so the name was not followed |
| 5 | 0.25 fixtures README | no name road from the three seeds |

**knn, 0.5** — Q5: no `stream_decode_mt` body in the top 20, as on 11-06.

The 11-06 run lost 5.25: writer 1.75, judge 1.5, chain 1.0, knn 0.5,
index 0.25, cap 0.25. The difference of 6.25 is the writer (+1.5), flash's
verdicts (+3.75) and the rest (+1.0).

## What the logs show

- **Flash turns down files that are not code.** `license-check.sh` (Q4,
  0.85), `tests/files/README` (Q9 0.84; Q8 0.58 and 0.60, harmless
  there), `CMakeLists.txt` (Q1, 0.65). On code that calls other code it
  follows well: Q6, Q8 and Q2 are level with the full model. Three
  cases; a pattern to watch, not yet a rule.
- **Narrower chains from the same seeds.** Bodies against 11-06, with the
  same seed count on each: Q4 23 vs 65, Q9 47 vs 75, Q3 52 vs 62; and
  level where the answer sits in a few C functions: Q2 26 vs 25, Q5 5 vs
  5, Q7 11 vs 11, Q6 36 vs 30, Q8 21 vs 25.
- **The retrieval repeats.** Q4 was run twice: 4 seeds, 23 bodies,
  113,739 and 113,737 characters of context, $0.0057 both times, every
  flash verdict identical to two decimals, 4.0 / 7 both times. Two triage
  scores moved by 0.02 and changed nothing that was read. The Q4 losses
  are properties of this setting, not noise.
- **The retry earned points here.** Two rescued triage picks carried a
  graded point each: `auto_decode` on Q3 (through `alone_decode`, 0.46 →
  0.61, then accepted at 0.78) and `basic_lzip_decode` on Q4
  (`tuktest_file_from_srcdir`, 0.47 → 0.56). The 11-06 baseline had the
  retry off, so part of this run's score is the retry's, not the
  models'. On the chain verdicts the retry changed nothing: flash's
  rejects sit at 0.76–0.99 and came back the same.
- **The full model fixes the seed scoring.** Flash alone kept 1 seed of
  40 on Q4 and, on Q6, 4 single-threaded decoders among its 6 seeds; the
  full model kept 4 and 5, all on the subject.
- **Cost.** $0.0056 of judge per question on average. With the Isoquant
  writer the whole answer averages under one cent.

## Before this run — the day's other arms

None of these has its own file. Graded in the session by the same grader
and method.

**Jev with the retry on, the cheap profile otherwise** (`JEV_MODEL` Jev
for everything — `typesafe/jev-1.14` by the `.env`; the log's sample call
is billed at $0.042 / M — `JEV_RETRY_BAND=0.10`, K=20,
`JEV_TRIAGE_DEFS=1`). Q1–Q8 only; Q9 was not run, so this arm is partial.

| Q | Jev + retry | pplx cheap 11-06 | judge $ | retrieval s | seeds / bodies |
|---|---|---|---|---|---|
| 1 | 4 / 4 | 4 | 0.022 | 9.8 | 2 / 8 |
| 2 | 5 / 5 | 4.75 | 0.033 | 17.2 | 15 / 35 |
| 3 | 8.5 / 10 | 9.5 | 0.050 | 17.4 | 16 / 115 |
| 4 | 4.75 / 7 | 6.5 | 0.023 | 11.4 | 4 / 36 |
| 5 | 5.75 / 7 | 5.25 | 0.020 | 10.9 | 8 / 24 |
| 6 | 4.0 / 6 | 5.75 | 0.010 | 6.4 | 4 / 8 |
| 7 | 5.5 / 6 | 5.5 | 0.023 | 7.2 | 7 / 15 |
| 8 | 4.5 / 6 | 5.5 | 0.028 | 11.5 | 7 / 40 |
| **Q1–Q8** | **42 / 51** | **46.75** | **0.209** | **92** | |

Three wrong claims (Q4 the `-qQ` test said of every `unsupported-*`
file; Q6 the order of the two limit checks; Q7 `success` under
`--test`). Of the 9 points lost, the writer's share is 3.0 (Q6 alone
1.5). Jev is the fastest judge of the day (retrieval 6–17 s, 1.4–3 s per
hop) and the most expensive (2.9 times the full model's judge cost on
the same eight, $0.209 against $0.072). On Q6, its fastest run, the triage read 7 of 73
candidates and every definitions group was skipped whole. On Q3 about 45
of the 115 bodies were `range_decoder.h` macros while `auto_decode` was
missing. The retry rescued about 20 triage picks over the eight
questions and earned at most half a graded point (Q5, `coder_normal`
through `allow_trailing_input`).

**pplx-decider-flash alone** (`JEV_MODEL` flash for everything,
`JEV_PREFILTER_TOP_K=40`, `JEV_TRIAGE_DEFS=0`, `JEV_RETRY_BAND=0.10`).
Two questions: Q6 5.25 / 6 (judge $0.009, 218 calls, 6 seeds of 40, four
of them single-threaded decoders that took 115 of the 157 chain calls),
Q4 3.25 / 7 (judge $0.007, 1 seed of 40; `tuktest_file_from_srcdir`: 10
places, 10 skipped). With the definitions read whole, about 15 keyword
definitions (`help`, `version`, `struct`, `option`, `restrict`, `read`)
were read at hop 1 of Q6; at flash's price that cost almost nothing.

Q4 and Q6 across the arms:

| | Q4 + Q6 | judge $ |
|---|---|---|
| pplx cheap, full model, 11-06 | 12.25 / 13 | 0.030 |
| hybrid (this file) | 9.75 / 13 | 0.014 |
| Jev + retry | 8.75 / 13 | 0.032 |
| flash alone | 8.5 / 13 | 0.016 |

## Against a frontier agent

The Fable 5.1 agent figures are those of the 11-06 file (same questions
and keys; graded there by Fable 5.1).

| | Fable 5.1 agent | pplx cheap 11-06 | this run |
|---|---|---|---|
| points | 69 / 74 (93.2 %) | 68.75 / 74 (92.9 %) | 62.5 / 74 (84.5 %) |
| wrong claims | 0 | 0 (one line slip) | 2 |
| time, total | 1,736 s | 519 s | 437 s |
| cost | $17.55 | $0.253 | $0.086 |

The cost column mixes writer prices (Fireworks list on 11-06, Isoquant
here); the judge alone is $0.092 against $0.051.

## Open after this run

- `JEV_TRIAGE_DEFS=0` on the hybrid, Q5, Q7 and Q9 first: 2.25 points sit
  behind the definitions triage, and with flash reading the definitions
  whole is nearly free. One change, measurable because the retrieval
  repeats.
- A same-day speed test: Q4 once with all three settings on the full
  model, to compare the chain seconds directly (10.0 and 10.7 s here).
- The retry as its own run on the full model (`JEV_RETRY_BAND=0.10`
  against the 11-06 file): it earned two points here that the baseline
  did not have the chance to earn.
- Flash and non-code files: no change proposed until there are more
  cases than three.
- The writer lost 3.25 with the body in context, against 1.75 on 11-06
  with a different provider of the same model family. Not separated in
  this run.