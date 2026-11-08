# xz — question answering, run of 2026-11-08 pplx + Qwen3.5-27B writer (writer-only swap on the cheap configuration)

**One change against `qa-xz-2026-11-06-pplx.md`: the writer.** DeepSeek V4.1
Flash on Fireworks → Qwen3.5-27B on DeepInfra. Everything else is the
cheap configuration of that file: pplx-decider judge, `JEV_PREFILTER_TOP_K=20`,
`JEV_PREV_BODY_MAX_CHARS=15000`, `JEV_TRIAGE_DEFS=1`, `JEV_RETRY_BAND=0`,
`JEV_HIT_TRIAGE=1`, `JEV_NAMES_AS_CHOICE=1`, `JEV_EXPAND_MAX_ADD=200`,
`JEV_TRIAGE_FROM=2`, `JEV_QUESTION_GREP=0`, Qwen3 vectors, the pre-change
xz index (`.unified-brain.db.before-branchfix`, commits `f7fa309e`..`45d08abc`).

Writer setting (`.env`):

```
LLM_PROVIDER=llmbase
LLM_MODEL=openai/Qwen/Qwen3.5-27B
LLM_API_BASE=https://api.deepinfra.com/v1/openai
```

Why this run: a dense 27B is the size that fits a workstation (a Mac
Studio M5 Ultra runs one at ~50 tokens/s), so the question was whether
the cheap configuration's evidence can be written up by a model of that
size — not whether it is cheaper (on DeepInfra it is not: $0.26 / M in,
$2.60 / M out against Flash's $0.22 / $0.66).

Same nine questions and keys (`evals/questions/xz.md`, with the Q8 key
correction of the 11-06 file), same grader (Claude Fable 5.1) and method,
one run per question, no re-runs, run 17:30–17:55 local time in the
order Q9 → Q1. Every concrete claim graded was checked against the xz
tree at `45d08abc`. Grades are against the 11-06 Flash arm on the same
question; where the retrieved evidence differs it is said.

## Before this run — the same weekend

- **Flash re-runs, cheap configuration, 2026-11-08 afternoon**, three
  questions, to see run-to-run variation: Q2 5 / 5 (11-06: 4.75), Q5
  5.5 / 7 (5.25), Q6 6 / 6 (5.75) — +0.75 over three, from the reach
  side (a `list.c` seed in Q5; four `hardware.c` bodies instead of two
  in Q6, giving `hardware_init`'s `total_ram / 4`) and one writer
  sentence in Q2 (the strict-sandbox condition stated with its
  `to_stdout_only` nesting). Writer at 245–270 tok/s that afternoon.
  Zero wrong claims in the three. This is the first same-configuration
  repeat on xz; the README's "replicability not measured" line can cite
  it as three questions, +0.75, no sign change.
- **Gemma 4 31B (OpenRouter, `google/gemma-4-31b-it`, $0.10 / $0.34 per
  M), Q9 only, aborted.** 11.5 / 23 on the same evidence that scored 22
  (11 seeds, 80 bodies, 324 k chars). Most `stream_decoder_mt.c` line
  numbers in the answer were invented — `SEQ_INDEX_DECODE` "at 1084"
  (that line is `case SEQ_BLOCK_HEADER:`; the state is at 1658), the
  footer/padding states cited 500 lines above where they are, pointing
  into comments — plus one substantive error (Index sizes said to be
  appended after decoding; the threaded path appends them from the Block
  Header before decoding, mt.c:1295). Writer 231 s, first token 136 s,
  4,681 tokens out at 20 tok/s, ≈ $0.012. Stopped after one question: a
  writer that fabricates `file:line` citations fails the one property
  the evidence-only design is for, whatever it costs.
- **Qwen3.5-27B, 2026-11-05**, Q1–Q3 on Jev-era evidence (run e code,
  K=400): Q1 3.5 / 4, Q2 3 / 5, Q3 6.5 / 10 at 47 k / 71 k / 110 k tokens
  in. Score fell with context size. Today's run is the same model on the
  cheap configuration's smaller, organised contexts.

## Results

| Q | topic | Qwen3.5-27B | Flash 11-06 | Δ | wrong | judge $ | writer $ | total $ | time s | first token s | out tokens | tok/s | calls | seeds | bodies | chars in |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | 3.25 / 4 | 4 | −0.75 | 2¹ | 0.005 | 0.022 | 0.027 | 74 | 55 | 4,916 | 80 | 46 | 2 | 6 | 115 k |
| 2 | sandboxing | 3.75 / 5 | 4.75 | −1.0 | 1² | 0.006 | 0.028 | 0.034 | 72 | 38 | 4,224 | 75 | 71 | 12 | 25 | 222 k |
| 3 | full decompression path | 5.5 / 10 | 9.5 | −4.0 | 1³ | 0.013 | 0.032 | 0.045 | 76 | 38 | 3,925 | 67 | 157 | 10 | 58 | 274 k |
| 4 | test fixture integrity | 3.75 / 7 | 6.5 | −2.75 | 0 | 0.021 | 0.038 | 0.059 | 83 | 45 | 3,891 | 65 | 178 | 4 | 59 | 359 k |
| 5 | padding / next stream / garbage | 4.75 / 7 | 5.25 | −0.5 | 0 | 0.003 | 0.015 | 0.018 | 52 | 34 | 3,720 | 79 | 35 | 3 | 5 | 73 k |
| 6 | MT memory limit | 4 / 6 | 5.75 | −1.75 | 0 | 0.009 | 0.022 | 0.031 | 62 | 30 | 3,422 | 75 | 103 | 5 | 29 | 176 k |
| 7 | when xz deletes the input | 4.25 / 6 | 5.5 | −1.25 | 1⁴ | 0.006 | 0.017 | 0.023 | 48 | 22 | 2,891 | 74 | 53 | 6 | 11 | 114 k |
| 8 | attacker modifies the Index | 3 / 6 | 5.5 | −2.5 | 2⁵ | 0.007 | 0.033 | 0.040 | 125 | 86 | 8,685 | 79 | 82 | 4 | 16 | 138 k |
| 9 | the long concatenated-streams question | 13.5 / 23 | 22 | −8.5 | 3⁶ | 0.018 | 0.035 | 0.053 | 84 | 29 | 4,490 | 66 | 189 | 11 | 71 | 309 k |
| **total** | | **45.75 / 74 (61.8 %)** | **68.75 (92.9 %)** | **−23** | **10** | **0.088** | **0.240** | **0.328** | **673** | | **40,164** | | **914** | **57** | **280** | **1.78 M** |

Columns as in the 11-06 file. Writer $ at DeepInfra list price ($0.26 / M
in, $2.60 / M out) on the footer's token counts; the Flash arm's writer
was $0.161 for the nine at Fireworks list. Judge $0.088 vs $0.092 on
11-06: the retrieval is the same within noise (914 vs 949 calls, 280
vs 304 bodies). Totals are sums of the unrounded footer values.

Wrong claims (Flash 11-06: one, a line number):

¹ Q1: `configure.ac` "line 535" and "525–530" for the host case (it is
at 353–355); `Makefile.inc` "32 and 46" (27–28, 40–41). Given as exact,
not approximate.
² Q2: "`sandbox_restrict_self` applies these rules" — no such function;
it is `syscall(SYS_landlock_restrict_self, …)`.
³ Q3: "a common chain for .xz files involves LZMA2 followed by LZMA1" —
LZMA2 is the filter, LZMA1 the decoder inside it, not two filters.
⁴ Q7: `opt_stdout` is set by "`--stdout`, `-c`, or piping" — piping xz's
output sets nothing; only `-c` (and `--test` through the same block) do.
⁵ Q8: the records hash is called "a hash (CRC32)" — it is SHA-256
(`LZMA_CHECK_BEST`, 32-byte `memcmp`, index_hash.c:290-295); and the
"extra Index Padding bytes" case is said to survive checks 1–6 and fail
at Backward Size — the padding length is computed from the records, so
the extra zeros are read as the CRC32 field and check 7 fails first.
⁶ Q9: `lzma_index_hash_append` "called via `read_output_and_wait` after
the Block finishes" — in the threaded path the sizes are appended from
the Block Header before decoding (mt.c:1295; only direct mode appends
after, 1635); the hard limit "returns `LZMA_MEMLIMIT_ERROR` immediately"
— pending output is flushed first and the check sits first in
`SEQ_BLOCK_INIT` so `lzma_memlimit_set()` can restart; trailing data
after `LZMA_STREAM_END` "triggers `LZMA_BUF_ERROR`" — `lzma_code` in
`ISEQ_END` returns `LZMA_STREAM_END` again (common.c:277). About half
the mt.c line numbers are exact, the rest 15–40 lines off, given as
exact.

None of the ten invents a state, a file or a function the tree does not
have (Q2's `sandbox_restrict_self` is a mangled real syscall name); they
are a model summarising what it skimmed. That is the difference from
the Gemma arm, where the citations themselves were fabricated.

## Per question

- Q1 3.25 / 4. Both gates right (the `#if defined(__ELF__) && (defined(__FreeBSD__)
  || defined(__linux__))` directive; `COND_ASM_X86` / `XZ_ASM_I386` with
  the `i?86` + OS list). Missing from the same `Makefile.inc` /
  `CMakeLists.txt` bodies: the small-build exclusion (`COND_SMALL` /
  `XZ_SMALL`) and `crc64_x86.S`'s extra `COND_CHECK_CRC64` / `"crc64"
  IN_LIST XZ_CHECKS`; the mingw/cygwin/djgpp mismatch stated only
  generically. First token 55 s on 35 k tokens in — the longest think of
  the arm relative to input.
- Q2 3.75 / 5. Platforms table right, strict condition right ("a single
  file processed to stdout" — the 11-06 Flash answer missed the
  `to_stdout_only` nesting), the macOS observation right (ci.yml:25 has
  `macos-latest`; no macOS sandbox). Thin where the seeds are rich: no
  Landlock mask arithmetic, no `required_rights` set or the `READ_DIR`
  reason, no "no `landlock_add_rule`" point, no `prepare_for_strict_sandbox()`
  locale preload, Capsicum rights reduced to "CAP_READ or CAP_WRITE",
  NEWS (0.927) uncited.
- Q3 5.5 / 10. Starts at `stream_decode`: `lzma_code` and `auto_decode`
  were not in this run's evidence (below). Of the three container seeds
  (`lzip_decode` 2.27, `alone_decode` 2.23, `microlzma_decode` 2.11) not
  one is mentioned — "for the standard .xz Stream format" and stop.
  `delta_decode` in context (0.619), absent. LZMA2 control bytes
  "determine chunk types" with no values; `dict_size` arithmetic absent.
  Second Qwen run on this question: 11-05's 7.25 had the two entry
  stages because that run's retrieval reached them.
- Q4 3.75 / 7. The four mechanisms it names are right (loader
  constraints, `test_files.sh` expectations, library checks, the test
  modules) and the negative conclusion (no hashing of fixture bytes) is
  right. Three sections absent with their bodies in context: the README
  contract (0.732), the fixed-seed generation + `test_compress.sh`
  (0.586, 0.660), the build side (`tests.cmake` 0.591, `INSTALL`'s
  EBCDIC note 0.203). `test_files.sh`'s own gating (`have_feature`,
  `NO_WARN`, exit 77) skipped; the `unsupported-*` sentence folds two
  rules into one.
- Q5 4.75 / 7. Padding machine, `first_stream` rewrite, four-row error
  table all correct. The non-concatenated case never stated; the EOF
  misaligned-padding row labelled "trailing garbage" (it is misaligned
  padding; garbage is the header-fails row). `file_info.c` — a seed at
  2.68, the backwards parser Flash wrote a section on — not mentioned.
  The two misses that are not the writer's are the same as every pplx
  run on Q5 (below).
- Q6 4 / 6. Gets the hard limit right (flush first, then
  `LZMA_MEMLIMIT_ERROR`), the two-tier eviction, the outqueue counters,
  `memconfig`'s rule. Missing: the clamp `memlimit_threading ≤
  memlimit_stop`; the waiting half of the soft limit (`block_can_start`
  in `read_output_and_wait`) — describes reclaiming memory, never that
  the main thread blocks until memory returns; the restart via
  `lzma_memlimit_set`; allocation failures; `coder.c` / `hardware.c`
  wiring; `test_memlimit_stream_decoder_mt`, a **seed** at 2.03, uncited.
- Q7 4.25 / 6. Skeleton right, DOS-like skip right. `coder_run` not even
  named this time (`coder.c` in context at 0.653); the `--force` comment
  (xz *cannot* detect a renamed file replaced by a symlink), the race
  comment, the `unlink()` failure message, the sparse-file gate,
  `--list` never reaching `io_close` — all absent. Closes with "no
  evidence for additional mechanisms", wrong about its own evidence.
  Same 4.5-band as the 11-06 Qwen run on this question.
- Q8 3 / 6. The eleven checks in order with the right survives/fails
  logic for the two main cases and the right closing sentence. The mt
  decoder not mentioned (two bodies present); the VLI-width case (key
  item 3) absent; `files/README`'s `bad-2-index-*` mapping absent;
  `test_index_hash.c` absent; the `lzma_index_append` / `xz -l` gap
  absent (`index.c` present). First token 86 s on 38 k tokens in.
- Q9 13.5 / 23. Own 3 / 4, Q5 part 4.5 / 7, Q6 part 3 / 6, Q8 part
  3 / 6. The state sequence right and in order; the three Index checks
  named with the right distinction; the Backward-Size case correctly
  "fails regardless of the CRC"; direct-mode fallback and the
  `block_can_start` wait separated as asked. Not one test, doc or API
  contract cited although `files/README` (0.780), `test_memlimit.c`
  (0.435), `test_index.c`, `xz-file-format.txt` (0.871) are in the
  sources and the question asks for them; no CRC-recompute reasoning
  (which checks survive an attacker who fixes CRCs); no partial-header →
  `BUF_ERROR`, no EOF-with/without-FINISH, no `--single-stream`, no
  `lzma_memlimit_set` recovery.

## Where the points were lost

Twenty-eight and a quarter.

**Writer, 23.0** — the fact was in the evidence:

| Q | lost | what was unread |
|---|---|---|
| 1 | 0.75 | small-build and crc64 conditions in the cited build files; the mismatch targets |
| 2 | 1.25 | Landlock mask, `required_rights`, `prepare_for_strict_sandbox`, Capsicum rights, failure messages, NEWS |
| 3 | 2.0 | three container seeds, `delta_decode`, LZMA2 values, the LZMA2/LZMA1 muddle |
| 4 | 3.0 | README contract, fixed seed + `test_compress.sh`, `tests.cmake` / `INSTALL`, `test_files.sh` gating |
| 5 | 0.75 | non-concatenated case, `file_info.c` seed, row label |
| 6 | 2.0 | clamp, `block_can_start` wait, restart, allocation failures, `coder.c` / `hardware.c`, the `test_memlimit` seed |
| 7 | 1.25 | `coder_run`, `--force` meaning, race, `unlink()` failure, sparse gate, `--list` |
| 8 | 2.5 | mt decoder, VLI case, README, tests, `index_append` path; two wrong claims |
| 9 | 9.5 | tests/docs/contracts, CRC-recompute reasoning, partial header, EOF cases, restart; three wrong claims |

**Judge, 4.0** — the body was offered and the judge said no (from the
logs, which this run has for all nine):

| Q | lost | what the log shows |
|---|---|---|
| 3 | 2.0 | `lzma_code` offered from `lzma_index_hash_decode` at 0.27 (not followed), then **followed** from `common.h` at hop 2 (0.51) — and at hop 3 the triage read 5 of 26 candidates without it (`common.h … led_to=0`). `auto_decode` offered once, from `CMakeLists.txt`, at 0.06. Both reached by the 11-06 Flash run from the same seeds: run-to-run judge variation on near-threshold bodies |
| 5 | 1.0 | `(definitions)` under `stream_decode`: 15 places, 15 skipped — `lzma_stream_header_decode` among them. Third run in a row (11-06 Q5 twice, open62541's `setOverflowInfoBits`) |
| 7 | 0.5 | `coder_run` accepted (0.65); names `coder_normal=0.30`, under the 0.5 follow cut — as f-pplx |
| 8 | 0.5 | the standing `SEQ_INDEX_WAIT_OUTPUT` half, kept on the judge for consistency with the earlier grades (`stream_decode_mt` was in context) |

**Chain, 0.75** — Q3 BCJ names (0.5, as every run: `filter_decoder.c`'s
decoders table offers no per-filter init names); Q4 `test_xz` at 0.10
next to `create_compress_files` 0.59 (0.25).

**knn, 0.5** — Q5, no `stream_decoder_mt.c` body in the top 20.

Retrieval lost 5.25 points on exactly the four spots where the 11-06
Flash arm lost its 5.25 (Q3 BCJ, Q4 `test_xz`, Q5 header codes + mt,
Q7 `coder_normal`) plus Q3's two entry stages this time. The remaining
23 are the writer's. The 11-06 arm's writer lost 1.75.

## What the swap did — from the footers

- **Shorter answers, longer thinking.** 40,164 tokens out over nine
  (Flash: 63,800); first token 22–86 s (Flash: 9–17 s that afternoon);
  65–80 tok/s (Flash 150–270). The 27B spends its output on reasoning
  and writes the skeleton; Flash writes the trace.
- **Seeds unused.** On Q3 three of ten seeds, on Q5 the second-ranked
  seed, on Q6 a seed at 2.03 are not mentioned. The judge put them in
  the top five of the evidence index and the writer skipped them. Nothing
  in the context organisation (run f's evidence index, bodies grouped by
  file, probabilities shown) changed that.
- **Cost.** Writer $0.240 vs $0.161 — the 27B is 50 % more expensive
  per nine on DeepInfra, because a dense 27B is served at $2.60 / M out
  against the MoE Flash's $0.66. Total $0.328 vs $0.253; time 673 s vs
  519 s. The "small model" premium runs the wrong way for a hosted
  writer; the only case for this size is a machine of one's own.
- **Honesty held.** Where the answers claim the evidence lacks something
  they are right (Q6 scope note, Q4 "no cryptographic signatures");
  where they claim completeness they are wrong (Q7 "no additional
  mechanisms"). No fabricated files or states.

## Evidence gathering alone, and the cost with the writer on Local Mac Studio Ultra

unified-brain's own cost in this run is the evidence gathering: the
judge calls plus one embedding query per question.

| | nine questions | per question |
|---|---|---|
| judge (pplx-decider, 914 calls) | $0.088 | $0.010 (range $0.003–0.021) |
| embedding query (Qwen3-Embedding-8B, one call) | < $0.001 | ≈ $0.0001 |
| **evidence gathering** | **≈ $0.09** | **≈ 1 cent** |
| writer, Qwen3.5-27B on DeepInfra | $0.240 | $0.027 |
| writer, Flash on Fireworks (11-06) | $0.161 | $0.018 |

Retrieval time (search + scoring + chains) was 5–22 s per question,
126 s for the nine; the other 547 s of the 673 were the writer.

If the same 27B ran on the user's own machine, the writer's $0.240 goes
to zero per question and the total is the evidence gathering: **about
1 cent a question, $0.09 for the nine**, paid to OpenRouter for the
judge. What that machine costs is a separate line: a Mac Studio with
M5 Ultra starts at $5,499 (96 GB unified memory, 1.2 TB/s), and the
first independent review measured a dense 27B at about 48–54 tokens/s
generation (52 at 16 k context, 39 at 64 k) and ~2,700 tokens/s prompt
processing, flat to 64 k (MacStories, via presenc.ai's round-up,
October 2026). On this run's token counts (520 k in, 40 k out over
nine) that is roughly 3 minutes of prompt processing and 15 minutes of
generation — **about 20 minutes of writer time for the nine, against
9 on DeepInfra** — with the large questions (Q4, Q9, ~100 k in) at
3–5 minutes each. Memory is not a constraint: a 27B at 8-bit is ~28 GB
and a 100 k-token cache fits the 96 GB base model with room.

So the all-local cost picture for this configuration is: ≈ 1 cent of
judge per question, the writer's electricity, and the machine. What it
does not change is the points: at this model size the writer scores
61.8 % on this evidence. The judge is still hosted — pplx-decider's
weights are Apache-2.0 but gated and need Perplexity's serving code —
so "nothing leaves the building" is not yet available; "a cent a
question leaves the building" is.

## Reading

The question this run asked — can a 27B dense model write this
pipeline's evidence up — gets a clear no at this model: 61.8 % against
92.9 % on identical evidence, ten wrong claims against one, and at a
higher price. The retrieval side's loss (5.25) did not move; the
synthesis side's did (1.75 → 23). For the local-writer idea the
hardware is no longer the question (an M5 Ultra runs a dense 27B at the
speeds above); the model is. Qwen3.8-27B is the one unmeasured
candidate in this size.

The three retrieval misses that repeat on every pplx run — Q5's
definitions group, Q7's `coder_normal` at 0.30, the Q3/Q8 near-threshold
bodies — are now the whole of what retrieval loses on xz, and all three
are judge decisions on short functions seen in a triage view. Per-place
probability logging for the `(definitions)` groups is the next thing to
add before any threshold moves.

## Notes for the next runs

- Writer stays DeepSeek V4.1 Flash in both profiles; the README's "the
  writer is your choice and costs what your writer costs" paragraph
  carries this arm's numbers.
- Qwen3.8-27B, writer-only swap on the cheap configuration, Q3 and Q9
  first, if the local-writer question is still open.
- Replicability: the three Flash re-runs above (+0.75 over three) are
  the first measurement; a full second Flash pass on the cheap
  configuration would give the number the README still owes.
- Per-place probability in the `(definitions)` triage log, then look at
  Q5's `lzma_stream_header_decode` and Q3's `lzma_code` skips before
  touching `JEV_FOLLOW_MIN` or the triage view size.
- Ingester list unchanged (branch-hole DBs, `@line` +1, `.S` symbol
  names, grammar-based keyword exclusion, rarest-first names).