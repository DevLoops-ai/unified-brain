# xz question set — speed profile, 2 hops (2026-11-12)

Code: working copy on commit `147545e`, with three uncommitted changes:
the question-vector cache (`QUESTION_VECTOR_CACHE`), the writer's
thinking switch (`WRITER_REASONING`) and the per-hop timing lines.
xz at `7baf6835`.
Writer: DeepSeek V4.1 Flash on Isoquant ($0.035 / M in, $0.30 / M out),
thinking off.
One run per question, in order, no reruns. All nine questions had been
asked before on the same day, so every question vector was read from
the store (search 0.10–0.16 s).
Graded from the answers and their status lines; the server logs of
these nine runs were not kept, so there are no per-hop timings here.

## Settings

The speed profile of `qa-xz-2026-11-12-speed.md` with one change:

```properties
JEV_EXPAND_MAX_HOPS=2
```

In full:

```properties
JEV_MODEL=typesafe/jev-1.14
JEV_SELECT_MODEL=typesafe/jev-1.14
JEV_TRIAGE_MODEL=typesafe/jev-1.14
JEV_FINAL_MODEL=typesafe/jev-1.14
JEV_PREFILTER_TOP_K=20
JEV_MIN_SCORE=1.9
JEV_EXPAND_MAX_HOPS=2
JEV_CONCURRENCY=256
QUESTION_VECTOR_CACHE=1
WRITER_REASONING=none
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
JEV_FLAT=0
```

## Results

| Q | topic | score | 3 hops | reliable hybrid | wrong claims | judge $ | writer $ | total $ | evidence s | total s | seeds | bodies | chars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | 4.0 / 4 | 3.75 | 4.0 | 0 | 0.012 | 0.0020 | 0.0140 | 2.1 | 7.6 | 2 | 9 | 133 k |
| 2 | sandboxing | 5.0 / 5 | 5.0 | 5.0 | 0 | 0.009 | 0.0031 | 0.0121 | 2.8 | 7.6 | 19 | 37 | 226 k |
| 3 | full decompression path | 7.25 / 10 | 8.0 | 9.25 | 1 | 0.029 | 0.0036 | 0.0326 | 3.9 | 14.8 | 16 | 87 | 229 k |
| 4 | test fixture integrity | 4.25 / 7 | 5.0 | 5.25 | 0 | 0.013 | 0.0020 | 0.0150 | 2.6 | 5.7 | 4 | 25 | 137 k |
| 5 | padding, next stream, garbage | 5.5 / 7 | 5.5 | 5.75 | 1 | 0.011 | 0.0022 | 0.0132 | 3.4 | 9.3 | 11 | 24 | 155 k |
| 6 | memory limit, threaded decoder | 5.0 / 6 | 5.75 | 5.75 | 0 | 0.014 | 0.0023 | 0.0163 | 2.9 | 6.1 | 7 | 22 | 171 k |
| 7 | when xz deletes the input | 5.0 / 6 | 4.5 | 5.25 | 0 | 0.017 | 0.0019 | 0.0189 | 2.9 | 5.3 | 7 | 15 | 138 k |
| 8 | attacker modifies the Index | 4.25 / 6 | 4.75 | 5.25 | 1 | 0.009 | 0.0022 | 0.0112 | 2.6 | 6.2 | 7 | 22 | 138 k |
| 9 | long concatenated-streams question | 21.25 / 23 | 20.75 | 21.0 | 1 | 0.028 | 0.0047 | 0.0327 | 3.6 | 17.0 | 13 | 66 | 323 k |
| **total** | | **61.5 / 74 (83.1 %)** | **63.0** | **66.5** | **4** | **0.142** | **0.024** | **0.166** | **26.9** | **79.6** | **86** | **307** | **1.65 M** |

Per answer: $0.018 on average ($0.011 to $0.033); 8.8 s on average
(5.3 to 17.0 s); evidence gathering 3.0 s on average (2.1 to 3.9 s),
with the question's vector stored. A new question adds the embedding
call, 0.9–2.3 s on this day.

Against the other arms:

| | this run | speed, 3 hops | reliable hybrid 11-12 | cheap 11-06 | coverage (run f) | Fable 5.1 agent |
|---|---|---|---|---|---|---|
| points | 61.5 / 74 (83.1 %) | 63.0 (85.1 %) | 66.5 (89.9 %) | 68.75 (92.9 %) | 70 (94.6 %) | 69 (93.2 %) |
| judge $ | 0.142 | 0.180 | 0.095 | 0.092 | about 0.80 | — |
| total $ | 0.166 | 0.205 | 0.135 | — | — | 17.55 |
| time s | 80 | 105 | 396 | — | — | 1,736 |

Against 3 hops: 1.5 points behind, 1.3 times faster overall, judge 21 %
cheaper. Against the reliable hybrid: 5.0 points behind, 5 times
faster. Against the agent: 7.5 points behind, 106 times cheaper, 22
times faster.

The comparison of evidence time with the 3-hop run is not like for
like: eight of the nine 3-hop runs embedded their question. With that
call taken out, the 3-hop run gathered evidence in about 3.9 s per
question, against 3.0 s here. The third hop costs about 0.9 s.

## Where the time goes

| step | seconds over nine questions | share |
|---|---|---|
| search (stored vector + vector search) | 1.2 | 2 % |
| seed scoring (20 calls, one round) | 5.4 | 7 % |
| chains (2 hops, triage and verdict rounds, final pass) | 20.3 | 26 % |
| writer | 52.5 | 66 % |

- Chains: 1.4–3.4 s per question, 648 calls over the nine.
- The writer's wait before its first token: 0.8–2.2 s. Its total time
  follows the size of the evidence: 2.4 s for 15 bodies (Q7), 10.8 s
  for 87 (Q3), 13.4 s for 66 bodies and 92,548 tokens (Q9).
- On Q3 and Q9 the writer takes three to four times as long as the
  evidence gathering.

## Per question

- Q1 4.0 / 4. Both build systems, the `Makefile.inc` nesting and the DOS
  makefile; says outright that C sources do not emit the note.
  `configure.ac` arrives at hop 2, which is all this question needs.
- Q2 5.0 / 5. Eleven claims verified, none wrong. `INSTALL` and the CI
  file (hop 3 before) are not there; the platform versions are taken
  from the comments in `sandbox.c` and `xzdec.c` instead.
- Q3 7.25 / 10. −1.0 format detection (`auto_decoder.c` not among the 20
  candidates). −0.5 the inside of the filter chain:
  `lzma_raw_coder_init` used to arrive at hop 3; the answer names
  `lzma_raw_decoder_init` and says it did not see inside. −0.5 BCJ.
  −0.5 `lzma_code()` reduced to "forwards to `next.code`". −0.25
  `lzma_check_finish()` placed in `SEQ_CHECK`; it runs at the end of
  `SEQ_PADDING` (wrong claim, the same slip as the reliable hybrid).
- Q4 4.25 / 7. −1.0 `test_compress.sh`. −1.0 `license-check.sh`. −0.25
  the loader's body (`tuktest_file_from_x`, hop 3 before): the rules
  are taken from its comment in the header, so read errors and short
  files are missing. −0.5 the CRC32 compare of decoded output. The
  negative conclusion is stated twice. No wrong claims.
- Q5 5.5 / 7. Same points as with 3 hops. −0.5 header outcomes other
  than bad magic. −1.0 fixtures and "padding has no CRC". One loose
  line in the summary treats trailing zero bytes as "garbage" (counted
  as a wrong claim; the table before it is right).
- Q6 5.0 / 6. −0.5 `is_direct_mode_needed()` not named. −0.5 allocation
  failure only in the scope note. Both are in `stream_decode_mt`, the
  top seed.
- Q7 5.0 / 6. −1.0 files never processed in place (`io_open_src_real()`
  not read). Destination removal on any failure is there this time.
  Same 15 bodies as with 3 hops.
- Q8 4.25 / 6. −1.0 the threaded decoder. −0.25 no fuzzing-build switch.
  −0.5 the survive-then-fail cases not split (inflated, deflated,
  reordered). Wrong claim: a size growing from one VLI byte to two said
  to pass until the Footer; the running-total check stops it at that
  record.
- Q9 21.25 / 23, the best Q9 of the three profiles. Own 3.75 / 4. Q5
  part 6.5. Q6 part 5.5 (allocation failure and both direct-mode
  triggers present; cites the single-threaded memory test, not the
  threaded one). Q8 part 5.5. One loose line: section 3.4 says the
  worker pool is not carried across the Stream boundary, section 1.7
  says correctly that it persists (wrong claim).

## Where the 12.5 points were lost

| cause | points | items |
|---|---|---|
| judge | 5.75 | Q3 BCJ 0.5; Q4 `test_compress.sh` 1.0, `license-check.sh` 1.0; Q5 stream-header body 0.5, `tests/files/README` 0.5; Q7 `io_open_src_real` 1.0; Q8 threaded decoder 1.0; Q9 stream-header body 0.25 |
| writer | 3.5 | Q3 0.75; Q6 1.0; Q8 0.75; Q9 1.0 |
| reach | 2.75 | Q3 `auto_decoder.c` 1.0 (K=20), filter chain inside 0.5 (2 hops); Q4 loader body 0.25 (2 hops); Q5 fixtures 0.5; Q9 format document, `container.h`, threaded memory test 0.5 |
| not assigned | 0.5 | Q4 CRC32 compare: writer or hops, not decidable without the log |

Traced to the missing hop: 0.75 (Q3 filter chain, Q4 loader body). The
rest of the 1.5 points against 3 hops moves both ways between the two
runs (Q7 +0.5, Q9 +0.5, Q1 +0.25; Q6 −0.75, Q8 −0.5) on the same or
nearly the same evidence, which is the writer's run-to-run movement.

## Critical or good-to-have

| Q | critical misses | good-to-have misses |
|---|---|---|
| 1 | none | 0 |
| 2 | none | 0 |
| 3 | format detection, the first stage of the path (reach, K=20) | 3 |
| 4 | none | 4 |
| 5 | none | 2 |
| 6 | none | 2 |
| 7 | the files `xz` refuses to process in place (triage) | 0 |
| 8 | none | 3 |
| 9 | none | 6 |
| **total** | **2** | **20** |

The two critical misses are the same two as with 3 hops, with the same
causes. Dropping the third hop added no critical miss. The four wrong
claims are small (a misplaced call, two loose sentences, one wrong
order of checks); none is a wrong mechanism.

## Findings

- The third hop is worth about 0.75 traced points and about 0.9 s per
  question. It costs 21 % of the judge's bill.
- What the third hop brought was often available one hop earlier in
  another form: the loader's rules in the header comment (Q4), the
  platform versions in code comments (Q2).
- Depth is not where the critical content is lost. Both critical misses
  come from breadth (20 candidates) and from triage (definition groups
  skipped whole).
- With evidence at 3 s, the writer is two thirds of the time, and it
  grows with the number of bodies, not with the difficulty of the
  question.
- The writer without thinking varies by half a point per question on
  the same evidence. One run per question cannot separate that from a
  setting.

## Open

- Shorter output for the robot's slow layer: a fixed format instead of
  a written answer would remove most of the 66 %.
- Fewer bodies to the writer on wide questions (Q3 87, Q9 66).
- Triage of definition groups (`JEV_TRIAGE_DEFS`) and K between 20 and
  100: the two causes of the critical misses.
- Hop 1 started together with seed scoring; the judge on a closer
  endpoint.
- Repeat runs, to put a number on the writer's movement.
- The same test on robot-style questions (ROS 2 Nav2 / MoveIt 2
  failure and recovery).