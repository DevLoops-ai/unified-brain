# xz question set — reliable hybrid profile (2026-11-12)

Code: working copy after commit `53f8dc9`, with the final-pass model
(`JEV_FINAL_MODEL`) and the local-verdict code (off) applied. The exact
commit of this run was not recorded. xz at `7baf6835`.
Writer: DeepSeek V4.1 Flash on Isoquant ($0.035 / M in, $0.30 / M out).
One run per question, in order, no reruns.

## Settings

```properties
JEV_MODEL=perplexity/pplx-decider-flash-v1.2
JEV_SELECT_MODEL=perplexity/pplx-decider-v1.2
JEV_TRIAGE_MODEL=perplexity/pplx-decider-v1.2
JEV_FINAL_MODEL=perplexity/pplx-decider-v1.2
JEV_PREFILTER_TOP_K=100
JEV_MIN_SCORE=1.9
JEV_RETRY_BAND=0
JEV_PREV_BODY_MAX_CHARS=15000
JEV_TRIAGE_DEFS=1
JEV_HIT_TRIAGE=1
JEV_NAMES_AS_CHOICE=1
JEV_TRIAGE_FROM=2
JEV_EXPAND_MAX_ADD=200
JEV_BATCH_SIBLINGS=0
JEV_QUESTION_GREP=0
JEV_SIGNPOST=0
JEV_LOCAL_VERDICT=0
```

Changed against the 11-11 hybrid: `JEV_FINAL_MODEL` set to the full
model. The fast model follows the chains; the full model takes the three
final decisions (which seeds to keep, which places to open, whether a
held lead reaches the writer).

## Results

| Q | topic | score | 11-11 hybrid | wrong claims | judge $ | writer $ | total $ | evidence s | total s | seeds | bodies | chars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | 4.0 / 4 | 3.25 | 0 | 0.0042 | 0.0023 | 0.0065 | 8.2 | 21.1 | 2 | 6 | 114 k |
| 2 | sandboxing | 5.0 / 5 | 5.0 | 0 | 0.0088 | 0.0035 | 0.0123 | 10.7 | 26.1 | 23 | 26 | 185 k |
| 3 | full decompression path | 9.25 / 10 | 9.5 | 1 | 0.0133 | 0.0058 | 0.0191 | 14.7 | 39.7 | 28 | 86 | 302 k |
| 4 | test fixture integrity | 5.25 / 7 | 5.0 | 0 | 0.0072 | 0.0033 | 0.0105 | 12.4 | 28.6 | 11 | 41 | 194 k |
| 5 | padding, next stream, garbage | 5.75 / 7 | 6.25 | 1 | 0.0105 | 0.0039 | 0.0144 | 10.9 | 33.5 | 8 | 18 | 145 k |
| 6 | memory limit, threaded decoder | 5.75 / 6 | 5.75 | 0 | 0.0114 | 0.0045 | 0.0159 | 11.8 | 32.3 | 7 | 41 | 217 k |
| 7 | when xz deletes the input | 5.25 / 6 | 5.0 | 0 | 0.0152 | 0.0035 | 0.0187 | 18.2 | 39.7 | 7 | 12 | 127 k |
| 8 | attacker modifies the Index | 5.25 / 6 | 5.0 | 1 | 0.0119 | 0.0058 | 0.0177 | 10.9 | 66.5 | 12 | 36 | 195 k |
| 9 | long concatenated-streams question | 21.0 / 23 | 21.25 | 1 | 0.0129 | 0.0069 | 0.0198 | 10.3 | 108.7 | 16 | 60 | 239 k |
| **total** | | **66.5 / 74 (89.9 %)** | **66.0** | **4** | **0.095** | **0.040** | **0.135** | **108** | **396** | **114** | **326** | **1.72 M** |

Per answer: $0.015 on average ($0.0065 to $0.0198); 44 s on average
(21 to 109 s); evidence gathering 12 s on average (8 to 18 s).

Against the other arms:

| | this run | hybrid 11-11 | cheap 11-06 | coverage (run f) | Fable 5.1 agent |
|---|---|---|---|---|---|
| points | 66.5 / 74 (89.9 %) | 66.0 (89.2 %) | 68.75 (92.9 %) | 70 (94.6 %) | 69 (93.2 %) |
| judge $ | 0.095 | 0.084 | 0.092 | about 0.80 | — |
| total $ | 0.135 | 0.122 | — | — | 17.55 |
| time s | 396 | 382 | — | — | 1,736 |

Against the agent: 2.5 points behind, 130 times cheaper, 4.4 times
faster. The half point over the 11-11 hybrid is inside the run-to-run
movement of the writer; the one repeatable effect of the final-pass
model is Q1 (below).

## Where the time goes

| step | seconds over nine questions | share |
|---|---|---|
| search (question embedding + vector search) | 25.9 | 7 % |
| seed scoring (100 calls, one round) | 16.5 | 4 % |
| chains (2–5 hops, triage and verdict rounds, final pass) | 65.7 | 17 % |
| writer | 287.7 | 73 % |

- The vector search itself takes 0.08–0.13 s. The rest of "search" is
  the embedding call: 1.2–2.9 s normally, 11.4 s once (Q7).
- The writer's wait before its first token was 6.9–18.6 s on Q1–Q7,
  35.5 s on Q8 and 54.5 s on Q9.
- Chain depth: Q1 3 hops, Q2 3, Q3 3 (a fourth found nothing), Q4 4,
  Q5 4, Q6 5, Q7 2, Q8 4, Q9 3.
- Places found at hop 1 before triage, per seed: Q3 320 for 28 seeds,
  Q4 143 for 11, Q5 68 for 8, Q6 73 for 7, Q7 78 for 7, Q8 108 for 12,
  Q9 133 for 16. About 8 to 13 per seed.

## Per question

- Q1 4.0 / 4. Both build systems complete. `CMakeLists.txt` held at hop 1
  (reject 0.65), passed the final pass as continue (reject 0.40) and was
  attached as a helper. Same six bodies and 113,735 chars in five runs
  in a row with a stronger final-pass model; lost in every run with
  flash in the final pass (reject 0.54–0.65).
- Q2 5.0 / 5. All claims verified, including four `NEWS` version claims.
  The chains added 3 bodies in 64 calls. `CMakeLists.txt` rejected at
  hop 1 with 0.79, so the CMake sandbox detection is not read; the answer
  says so. No point lost.
- Q3 9.25 / 10. −0.5 BCJ filter bodies not reached. −0.25
  `lzma_check_finish()` placed in `SEQ_CHECK`; it runs at the end of
  `SEQ_PADDING` (wrong claim). The final pass made 54 calls and rejected
  none: 86 bodies against 71 on 11-11.
- Q4 5.25 / 7. −1.0 `license-check.sh` (rejected 0.85 at hop 2). −0.75
  `test_compress.sh` `cmp` round trip and the fixed seed (`test_compress`
  shown as a name, not followed).
- Q5 5.75 / 7. −0.5 header outcomes other than bad magic
  (`lzma_stream_header_decode()` skipped by the triage, `lzma_code()` not
  reached). −0.5 fixtures and "padding has no CRC". −0.25 the Stream
  Header called six bytes; it is twelve (wrong claim).
- Q6 5.75 / 6. −0.25 the `base.h` note on the ≤ 5.2.6 bug not used;
  `base.h` was attached by the final pass this time.
- Q7 5.25 / 6. −0.5 files that are never processed: taken from `xz.1`
  only, without the `--force` / `--keep` exceptions and the symlink rule;
  `io_open_src_real()` skipped by the triage. −0.25 destination removal
  described for a failed close only.
- Q8 5.25 / 6. Best answer on this question so far: gives the order in
  which the checks fire and a worked example of swapped records caught
  only by the hash. −0.25 `SEQ_INDEX_WAIT_OUTPUT` not mentioned. −0.25
  the VLI-width case. −0.25 case F4 says a size re-encoded in more bytes
  survives until the Footer; `lzma_vli_decode()` rejects a non-minimal
  encoding (wrong claim).
- Q9 21.0 / 23. Own 3.5 / 4 (no fixtures, format document or
  `container.h`). Q5 part 6.25. Q6 part 5.75. Q8 part 5.75. −0.25
  `lzma_index_hash_size()` said to use the `records` side; it uses
  `blocks` (wrong claim; Q8 of the same run has it right).

## Where the 7.5 points were lost

| cause | points | items |
|---|---|---|
| judge | 4.0 | Q4 `license-check.sh` 1.0, `test_compress.sh` 0.75; Q5 stream-header body (triage) and `lzma_code()` 0.75; Q7 `io_open_src_real` (triage) 0.5; Q9 `tests/files/README` (rejected 0.84) 0.75, stream-header body (triage) 0.25 |
| writer | 2.5 | Q3 `lzma_check_finish` 0.25; Q5 six bytes 0.25; Q6 `base.h` note 0.25; Q7 destination removal 0.25; Q8 0.75; Q9 0.75 |
| reach | 1.0 | Q3 BCJ bodies 0.5; Q5 fixtures 0.25; Q9 format document and `container.h` 0.25 |

Against 11-11: the judge's Q1 loss (0.5) is gone. The remaining judge
losses are all in the chains and the triage, before the final pass.

Core content: no question missed its main conclusion. The four wrong
claims are small slips (a misplaced call, a byte count, a guessed case,
a misread function); none is a wrong mechanism.

## Findings

- A stronger model in the final pass fixes the Q1 miss and nothing else.
  With Jev there (11-11, one run of nine): 66.25 / 74, judge $0.125. With
  the full pplx model (this run): 66.5 / 74, judge $0.095.
- The full pplx final pass is generous, not selective: Q3 54 calls and 0
  rejects, Q6 30 calls and 0 rejects, Q9 35 calls and 1 reject. It adds
  context (1.72 M chars against 1.47 M on 11-11) at no loss of score.
- The local verdict (a second look at a rejected body on the lines
  around the link) was measured on 11-11 with Jev: Q1 3.5, Q3 9.5,
  Q4 5.0, judge +40 to +69 %, no point gained, and on Q1 it lost
  `CMakeLists.txt`. Off.
- The triage skips whole groups of definitions from their first lines
  ("12 places, 11 skipped"). Three of the judge losses are bodies lost
  there (`lzma_stream_header_decode`, `io_open_src_real`).
- `tests/files/README` is reached and rejected (0.84–0.86) on Q8 and Q9.
  It holds the fixture names three questions ask for.
- The writer is 73 % of the time and its first-token wait grows with the
  size of the question.

## Open

- Speed mode: links computed at ingest, hops 1–2 judged in one round,
  hops 3–5 for what survives; writer without thinking; evidence-only
  output.
- The embedding call for the question (11.4 s once).
- The writer dropping or misreading in-context evidence.
- `_jev_verdict_names` error paths return 4 values, callers unpack 5.
- Remove the dead local-verdict v1 code in `_jev_verdict_names`.