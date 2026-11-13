# xz question set — ultra-fast local, top 40, pplx / flash judges (2026-11-13)

Code: working copy with uncommitted changes applied: the local question
vector (`QUERY_EMBED_OLLAMA`), names shown to the triage
(`JEV_TRIAGE_NAMES`), the reopen fix (`JEV_TRIAGE_REOPEN`), the reworded
skeleton markers (`QA_PLAIN_MARKERS`) and the writer-input dump
(`QA_DUMP_CONTEXT`). The exact commit of this run was not recorded.
xz at `7baf6835`.
Writer: DeepSeek V4.1 Flash on Isoquant ($0.035 / M in, $0.30 / M out),
reasoning off.
Question vector: Qwen3-Embedding-8B, 4-bit, computed on the laptop by
Ollama (Mac M3, 16 GB). Stored vectors are the hosted ones; ingestion
was not touched.
One run per question in this setting, no reruns.

Three things to know before reading the numbers:

- The questions were not asked in order: Q3, Q7, Q8, Q9, Q6, Q5, Q4,
  Q2, Q1.
- Q7 was asked with an added clause: "…, including files that xz
  refuses to process at all?". With the original question key point 5
  is not asked for and the score is about 4.75. The fair total is about
  61.25.
- On Q3 the search took 4.2 s instead of 1.1 s: Ollama had unloaded the
  model after five idle minutes.

## Settings

```properties
# judges
JEV_MODEL=perplexity/pplx-decider-flash-v1.2
JEV_SELECT_MODEL=perplexity/pplx-decider-v1.2
JEV_TRIAGE_MODEL=perplexity/pplx-decider-v1.2

# seeds
JEV_PREFILTER_TOP_K=40
JEV_MIN_SCORE=1.9

# ultra-fast profile
JEV_EXPAND_MAX_HOPS=2
JEV_FINAL_PASS=0
JEV_SEARCH_AHEAD=1
JEV_TRIAGE_DEFS=1
JEV_TRIAGE_FROM=2
JEV_TRIAGE_AROUND=3
JEV_NAMES_AS_CHOICE=1
WRITER_REASONING=none

# new switches of 11-12 / 11-13
JEV_TRIAGE_NAMES=1
JEV_TRIAGE_REOPEN=1
QA_PLAIN_MARKERS=1

# question vector on this machine
QUERY_EMBED_OLLAMA=qwen3-embedding:8b
QUESTION_VECTOR_CACHE=0
```

This block is rebuilt from the session, not copied from the `.env` of
the run. Check it against the `.env` before publishing.

Changed against the ultra-fast local run of 11-12 (58.25 / 74):
top 40 instead of top 20; the three judge models (were all Jev); names
shown to the triage; the reopen fix; the reworded markers.

## Results

| Q | topic | score | reliable hybrid 11-12 | wrong claims | judge $ | writer $ | total $ | evidence s | total s | seeds | bodies | chars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | 3.75 / 4 | 4.0 | 0 | 0.0020 | 0.0010 | 0.0030 | 5.0 | 6.9 | 2 | 5 | 54 k |
| 2 | sandboxing | 5.0 / 5 | 5.0 | 0 | 0.0030 | 0.0024 | 0.0054 | 6.7 | 9.7 | 21 | 28 | 189 k |
| 3 | full decompression path | 9.0 / 10 | 9.25 | 0 | 0.0066 | 0.0038 | 0.0104 | 11.4 | 16.7 | 18 | 69 | 269 k |
| 4 | test fixture integrity | 5.0 / 7 | 5.25 | 0 | 0.0045 | 0.0022 | 0.0067 | 8.6 | 12.1 | 8 | 32 | 142 k |
| 5 | padding, next stream, garbage | 5.25 / 7 | 5.75 | 0 | 0.0035 | 0.0018 | 0.0053 | 7.8 | 11.2 | 7 | 14 | 126 k |
| 6 | memory limit, threaded decoder | 4.25 / 6 | 5.75 | 0 | 0.0030 | 0.0015 | 0.0045 | 6.5 | 9.3 | 5 | 14 | 78 k |
| 7 | when xz deletes the input (with clause) | 5.75 / 6 | 5.25 | 0 | 0.0093 | 0.0021 | 0.0114 | 8.9 | 13.7 | 7 | 16 | 142 k |
| 8 | attacker modifies the Index | 4.5 / 6 | 5.25 | 3 | 0.0045 | 0.0027 | 0.0072 | 6.7 | 11.2 | 9 | 37 | 205 k |
| 9 | long concatenated-streams question | 19.75 / 23 | 21.0 | 1 | 0.0069 | 0.0045 | 0.0114 | 8.1 | 18.0 | 15 | 58 | 261 k |
| **total** | | **62.25 / 74 (84.1 %)** | **66.5** | **4** | **0.043** | **0.022** | **0.065** | **70** | **109** | **92** | **273** | **1.47 M** |

Per answer: $0.007 on average ($0.003 to $0.011); 12.1 s on average
(6.9 to 18.0 s); evidence gathering 7.7 s on average (5.0 to 11.4 s).

Against the other arms:

| | this run | ultra-fast local 11-12 | ultra-fast, hosted vector 11-12 | reliable hybrid 11-12 | Fable 5.1 agent |
|---|---|---|---|---|---|
| points | 62.25 / 74 (84.1 %) | 58.25 (78.7 %) | 61.25 (82.8 %) | 66.5 (89.9 %) | 69 (93.2 %) |
| judge $ | 0.043 | — | — | 0.095 | — |
| total $ | 0.065 | about 0.135 | about 0.135 | 0.135 | 17.55 |
| time s | 109 | about 60 | 60 | 396 | 1,736 |

The two ultra-fast columns have no results file of their own; their
cost and time are the session averages (about $0.015 and 6.7 s per
answer).

Against the agent: 6.75 points behind, about 270 times cheaper, 16 times
faster. Against the reliable hybrid: 4.25 points behind, half the cost,
3.6 times faster. Against the ultra-fast local run of the day before:
4 points more (3 with the original Q7), half the cost, but 12 s per
answer instead of about 7.

## Where the time goes

| step | seconds over nine questions | share |
|---|---|---|
| search (question vector on the laptop + vector search) | 14.4 | 13 % |
| seed scoring (40 calls, one round) | 15.9 | 15 % |
| chains (2 hops, a triage and a verdict round each) | 39.4 | 36 % |
| writer | 39.2 | 36 % |

- The question vector takes 1.0–1.2 s for a normal question, 1.9 s for
  Q9, and 4.2 s when Ollama has to load the model first (Q3).
- Scoring 40 candidates takes 1.3–2.5 s. With 20 and Jev it took
  0.7–1.1 s. The calls already run all at once (limit 128).
- A pplx or flash round takes 0.4–1.9 s however small it is. Q7 hop 2:
  a triage round of 2 calls took 1.36 s. With Jev the same rounds took
  0.3–0.6 s that morning. A short question still has four rounds, so it
  pays about 4–5 s of chains (Q5 4.6 s for 35 verdicts, Q7 5.3 s for
  38). A wide question pays the same (Q3 5.7 s for 152 verdicts).
- Rounds per question from the logs (triage / verdicts, seconds):
  Q3 1.48 / 1.95 then 0.79 / 1.16; Q4 1.54 / 1.46 then 0.70 / 1.36;
  Q5 1.42 / 1.56 then 0.89 / 0.59; Q6 0.63 / 1.21 then 0.38 / 1.30;
  Q7 1.40 / 1.86 then 1.36 / 0.59; Q8 1.35 / 1.00 then 0.41 / 1.10;
  Q9 1.56 / 1.21 then 0.63 / 1.25.

## Per question

- Q1 3.75 / 4. Both `.S` files, the guard and its comment, the full
  Autotools path. Adds two correct conditions that are not in the key
  (non-small build, CRC64 enabled for the second file). −0.25 the CMake
  side: `XZ_ASM_I386` is named but `CMakeLists.txt` was not read.
- Q2 5.0 / 5. All five pledge strings, the Landlock rights formula, the
  `ENOSYS` exception, the call order in `main()` and the "last file
  only" rule of `xzdec` verified in source. One loose sentence in the
  closing section ("only for the single-file-to-stdout case"); the body
  of the answer has it right. No point lost.
- Q3 9.0 / 10. Format detection is there for the first time in an
  ultra-fast run: `coder.c` came in at knn rank 21, `auto_decode` at 33,
  `stream_decode_mt` at 35. −0.5 BCJ filter bodies not reached. −0.25
  the `LZMA_TIMED_OUT` mapping in `lzma_code()`. −0.25 `is_size_valid`,
  `memcmp` and the `decoders[]` table not named.
- Q4 5.0 / 7. −1.0 `license-check.sh` (rejected 0.85 at hop 2). −0.9
  `test_compress.sh` never a candidate. −0.1 the value of
  `TUKTEST_FILE_SIZE_MAX`: the judge chose that name (0.75) in the last
  hop and nothing read it; the answer says so.
- Q5 5.25 / 7. −0.6 header outcomes other than bad magic
  (`lzma_stream_header_decode()` lost in the triage: 27 definitions
  offered, 27 skipped). −0.75 fixtures and "padding has no CRC"
  (`tests/files/README` never a candidate). −0.4 the partial-header case
  and the fresh Index hash, both in bodies the writer had.
- Q6 4.25 / 6. The test is described in full and the trap is avoided
  outright. −1.0 allocation failure → `LZMA_MEM_ERROR`, inside
  `stream_decode_mt`, which the writer had. −0.4 where `xz` sets the two
  limits (`coder_init` not read). −0.35 the sizes appended after the
  Block ends in direct mode; the timeout mapping.
- Q7 5.75 / 6 (with the clause). `args.c` came in at knn rank 34 and
  gives the `--stdout` / `--test` rule from the code. Files refused at
  open are complete. −0.25 `coder_normal` skipped by the triage.
- Q8 4.5 / 6. The running-total check is there. Adds the
  backward-reading path and `xz --list`, both correct, not in the key.
  −0.75 threaded decoder: sizes said to be appended in
  `SEQ_BLOCK_THR_RUN` (it is `SEQ_BLOCK_INIT`), the wait for workers not
  mentioned (wrong claim). −0.25 `lzma_index_hash_size()` said to use
  the decoded Index; it uses `blocks` (wrong claim; its body was not
  read). −0.25 a longer VLI with the same value said to survive until
  Backward Size; `lzma_vli_decode()` rejects it (wrong claim). −0.25
  rest.
- Q9 19.75 / 23. Own 3.3 / 4. Q5 part 6.05. Q6 part 5.15. Q8 part 5.25.
  The implementation path is nearly complete. The confirmations are
  thin: API contracts and one test only. `tests/files/README` rejected
  at 0.84; the Stream Header and Footer decoder bodies skipped by the
  triage; `test_memlimit.c` held as "not sure" and not attached. −0.25
  `lzma_index_hash_size()` said to use the `records` side (wrong claim).

## Where the 11.75 points were lost

| cause | points | items |
|---|---|---|
| writer | 4.05 | Q1 0.05; Q3 0.5; Q5 0.4; Q6 1.35; Q8 1.0; Q9 0.75 |
| judge | 3.85 | Q4 `license-check.sh` 1.0; Q5 stream-header body (triage) 0.6; Q7 `coder_normal` (triage) 0.25; Q9 `tests/files/README` (rejected 0.84), stream header / footer bodies (triage), `test_memlimit.c` 2.0 |
| reach | 3.85 | Q1 `CMakeLists.txt` 0.2; Q3 BCJ bodies 0.5; Q4 `test_compress.sh` and the size constant 1.0; Q5 fixtures 0.75; Q6 `coder_init` 0.4; Q8 `lzma_index_hash_size` and the VLI decoder 0.5; Q9 0.5 |

Core content: no question missed its main conclusion. Q5 gives one of
the four ways a following Stream Header can fail. Q9 answers the request
for "tests, format documentation, or API contracts" by half. The four
wrong claims are on Q8 and Q9; three of them describe a body that was
not in the evidence.

## Findings

- Top 40 repairs the local question vector. The 4-bit local vector
  ranks some needed seeds between 21 and 40 (`args.c` 34 on Q7;
  `coder.c` 21, `auto_decode` 33, `stream_decode_mt` 35 on Q3;
  `file_info_decode` 40 on Q8). With top 20 they were invisible.
- pplx scores 40 candidates for $0.001–0.007; Jev took $0.015 on Q7.
  ⚠️ pplx scores lower: on Q7 three needed seeds sat just above the 1.9
  cut (2.05, 2.07, 2.08).
- Flash in the chains costs a third of Jev and accepts less. Q3: Jev
  196 verdicts, 107 bodies, chain $0.028; flash 152 verdicts, 69 bodies,
  chain $0.005, same score. The writer gets less to read and is faster.
- pplx as the triage model throws away almost every definition, even
  with the names shown: Q5 27 of 27 skipped, Q6 26 of 27, Q7 33 of 35.
  Jev on Q7 that morning kept `io_open_src`, `coder_normal` and
  `io_open_dest` out of a group of 8. Bodies lost this way:
  `lzma_stream_header_decode`, `lzma_stream_footer_decode`,
  `coder_normal`.
- Reopen is a bug fix and stays on. Without it a place skipped by the
  triage stayed marked as seen: on Q7 the judge asked for
  `io_open_src_real` (0.80) and `io_open_dest_real` (0.99), the search
  found them, and they were dropped (3.75 against 4.5, same 6.5 s).
- Names the judge chooses in the last hop are never read. Each log ends
  with 5 to 20 open leads. Seen on Q4 (`TUKTEST_FILE_SIZE_MAX`) and
  behind the repeated wrong claim about `lzma_index_hash_size()` (seven
  runs across two days).
- Text files that list things are rejected: `tests/files/README` 0.84,
  `license-check.sh` 0.85. Same as in the reliable hybrid run.
- Measured on single questions the same morning, not part of this run:
  Q3 with Jev in the chains 8.75 (15.4 s, judge $0.030); Q3 with the
  full pplx everywhere 9.0 (judge $0.011); Q7 with Jev everywhere and
  top 40 5.25 (9.8 s, judge $0.029); Q7 with pplx scoring and Jev chains
  5.75 (9.8 s, judge $0.020).

## Open

- Same run with `JEV_TRIAGE_MODEL=typesafe/jev-1.13`: expected to bring
  back the lost definitions and 1–2 s per answer. Not measured.
- Read the definitions of names the judge chose in the last hop and give
  them to the writer without judging. Not built.
- Narrow reopen (only names the judge chose) if full reopen shows extra
  calls on wide questions. One night-time measurement on Q3 (155 → 190
  calls) is not trusted.
- Ollama keep-alive, so the model is not unloaded between questions.
- The Q7 key: point 5 needs the clause in the question, or should be
  marked good-to-have.
- The writer guessing about bodies it was not given, and skipping
  things it was given (Q6 point 5).
- The manual page seed on Q7 (`xz.1`): 12–16 chain calls, 63–85 % of the
  chain cost, nothing accepted.