# xz — question answering, run of 2026-11-05 b-pplx (judge swap: pplx-decider in place of Jev, on run f's code)

**This run uses a different judge.** Everything else is run f
(`qa-xz-2026-11-05-b.md`): same code, same configuration, same writer,
same vectors, same nine questions and keys, same grader and method, one
run per question, no re-runs. The one change:

```
JEV_MODEL=perplexity/pplx-decider-v1.2        (run b: typesafe/jev-1.13)
```

pplx-decider is Perplexity's open-weights decision model (Apache-2.0,
27B), called through OpenRouter. Every number below that says "Jev $" or
"judge $" is the pplx-decider cost for that question; the column keeps
the name the footer prints. The thresholds (`JEV_FOLLOW_MIN` 0.5,
`JEV_SURE_REJECT` 0.75, the seed cut 2.0, `JEV_RETRY_BAND` 0.10,
`JEV_DERIVED_MIN` 0.65) were tuned to Jev and were **not** changed for
this run; that is deliberate, so the comparison to f is the judge alone.

Setup otherwise as f: unified-brain service on the author's laptop,
database = xz commits `f7fa309e`..`45d08abc`, Qwen3 vectors, writer
DeepSeek V4.1 Flash on Fireworks, `JEV_HIT_TRIAGE=1`,
`JEV_NAMES_AS_CHOICE=1`, `JEV_EXPAND_MAX_ADD=200`, `JEV_TRIAGE_FROM=2`.
Run 19:00–19:45 local time, in the order Q7, Q8, Q9, Q6, Q4, Q3, Q2, Q1,
Q5. Every concrete claim graded was checked against the xz tree.

## Before this run — the other judges tried today

Recorded here so the trail is complete; none of these is a clean
comparison and none has its own file.

- **Cloudflare Clef** (`cloudflare/clef`, Apache-2.0, 27B, via
  OpenRouter), writer Qwen3.5-27B, run e's code: Q3 7.5 / 10, Q4 3.5 / 7,
  Q5 5 / 7 — 16 / 24 at judge $1.46 for the three questions (run d's
  three: $0.24). Stopped as too expensive.
- **pplx-decider v1.2, writer Qwen3.5-27B**, run e's code, afternoon:
  Q3 8.5 / 10 (judge $0.035, 22 seeds, 74 bodies), Q4 2 / 7, Q5 5.5 / 7,
  Q6 3.5 / 6; then `JEV_HIT_TRIAGE=0` mid-run: Q6 5 / 6, Q5 5 / 7,
  Q4 3 / 7. Two writers and two configurations across six answers, so
  nothing in it compares to a Jev run. Its one finding — losses traced
  to the hit triage skipping followed names — was on `_file_places`
  candidates bypassing the triage grouping (fixed before e) and on the
  27B writer, and did not reappear below.
- **pplx-decider + Flash writer, Q9**, before run f: the Fireworks
  writer call returned no text after 410 s (Fireworks degraded); the
  $0.12 retrieval was lost. Not graded.

## Results

| Q | topic | f-pplx | run f (Jev) | wrong | judge $ | writer $ | total $ | time s | retrieval s | seeds | bodies | chars in |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | **4 / 4** | 4 | 0 | 0.013 | 0.009 | 0.022 | 53 | 38 | 2 | 6 | 114 k |
| 2 | sandboxing | **5 / 5** | 5 | 0 | 0.023 | 0.018 | 0.041 | 70 | 31 | 20 | 28 | 210 k |
| 3 | full decompression path | 9.5 / 10 | 10 | 0 | 0.036 | 0.030 | 0.066 | 115 | 66 | 22 | 76 | 346 k |
| 4 | test fixture integrity | 5 / 7 | 5.5 | 0 | 0.029 | 0.021 | 0.050 | 89 | 53 | 8 | 70 | 263 k |
| 5 | padding / next stream / garbage | 5.5 / 7 | 6.5 | 1¹ | 0.028 | 0.010 | 0.038 | 64 | 35 | 4 | 8 | 108 k |
| 6 | MT memory limit | 4.5 / 6 | 6 | 0 | 0.030 | 0.016 | 0.046 | 84 | 53 | 7 | 34 | 197 k |
| 7 | when xz deletes the input | 5.5 / 6 | 5.5 | 0 | 0.024 | 0.009 | 0.033 | 32 | 14 | 6 | 12 | 110 k |
| 8 | attacker modifies the Index | 5.5 / 6 | 5.5 | 0 | 0.033 | 0.022 | 0.055 | 89 | 27 | 10 | 38 | 225 k |
| 9 | the long concatenated-streams question | **22 / 23** | 22 | 1² | 0.050 | 0.037 | 0.087 | 150 | 49 | 15 | 70 | 378 k |
| **total** | | **66.5 / 74 (89.9 %)** | **70** | **2** | **0.266** | **0.172** | **0.438** | **746** | **366** | **94** | **342** | **1.95 M** |

Columns as before: judge $ from the footer, writer $ at Fireworks list
price ($0.22 / M in, $0.66 / M out) on the footer's token counts, time =
footer total, retrieval = search + Jev scoring + chains.

Against f on the same seven questions whose f footers are on file (all
but Q4, Q5): judge $0.205 against $0.606 — **34 %**. Writer characters
1.95 M against f's ≈ 2.4 M. Retrieval time 366 s against ≈ 185 s: the
chains took 20–41 s per question on OpenRouter against 5–11 s with Jev
(Q3's 18 s search was cold vectors, not the judge).

¹ Q5: "errors are routed through the `SEQ_ERROR` state" given as the
multithreaded decoder's difference in `SEQ_STREAM_PADDING`. They are
not: `stream_decode_mt()` returns `LZMA_DATA_ERROR` directly there, as
the single-threaded decoder does. The MT body was in the evidence at
2.80. Writer.

² Q9: the Stream Header is "16 bytes" three times; it is 12
(`LZMA_STREAM_HEADER_SIZE`). The same writer made this slip in runs c
and d and not in e and f. Writer; counted −0.5 in the Q5 part as before.

## Per question

- Q1 **4 / 4**. Both conditions, both build systems, the "assembled but
  no note" consequence. Six bodies, no duplicate reads (the judge never
  chose `crc32_x86` as a name, so `_file_places` did not fire).
- Q2 **5 / 5**. All five with the pledge strings, the Landlock
  arithmetic, the Capsicum rights, xzdec's last-file rule; six NEWS
  entries verified; new: the `configure.ac` sanitizer comment (Capsicum
  tested on FreeBSD 13.2; OpenBSD's minimal runtime). Honest about the
  two Capsicum no-op bodies it did not have.
- Q3 9.5 / 10. All ten stages in order with the hand-offs; the BCJ
  `simple_code()` mechanism missing — `simple_coder.c` not reached (a
  Jev seed in f). 22 seeds, all decoder files; the long scope list at
  the end names the hand-off bodies it did not read, accurately.
- Q4 5 / 7. Loader, both CRC constants and `test_crc()`, `test_files.sh`
  complete, round trip and fixed seed (the half f lost to reach — pplx
  reached `create_compress_files.c`), the negative conclusion stated
  carefully (it saw the index's own sha256 of one fixture and said no
  test uses it — true). Lost `decode_expect_error()` (writer;
  `test_lzip_decoder.c` eight times in the sources) and
  `license-check.sh` (not reached at all; Jev reaches and rejects it).
- Q5 5.5 / 7, wrong claim ¹. The padding state complete and the trap
  met; the header outcomes reduced to the magic-bytes case alone — no
  partial-header `LZMA_BUF_ERROR`, no CRC32 / reserved-flags codes
  (`stream_flags_decoder.c` not reached); no fixtures cited (README
  not reached). Four seeds, eight bodies. New and verified:
  `file_info.c`'s backwards padding handling and `file_size & 3`.
- Q6 4.5 / 6. Both limits with the API text, hard limit first and
  restartable, `block_can_start`, eviction, `memconfig`, the test
  sequence, full `coder.c` wiring. Missing: allocation failures →
  `LZMA_MEM_ERROR` + `threads_stop()` (−1) and `is_direct_mode_needed()`
  for Blocks without sizes (−0.5). Both sit in `stream_decode_mt()`,
  which the answer quotes on either side of them. Writer; the same
  writer wrote both in Q9 half an hour earlier.
- Q7 5.5 / 6. Same half as every run (the `success` rule), here as a
  reach loss: `coder_normal()` never read. The log shows why: on the
  `coder_run` line pplx gave `names: (none of these)=0.70
  coder_normal=0.30`, under the 0.5 follow cut. Six seeds, twelve
  bodies; the answer named what it did not have.
- Q8 5.5 / 6. Same half as every run (`SEQ_INDEX_WAIT_OUTPUT`). The
  survive-then-fail section is the clearest of any run; new and
  verified: `list.c`'s `parse_block_header()` checking Block Headers
  against Index Records, `index_decode()`'s `SEQ_MEMUSAGE` guard.
  Imprecision not counted: `LZMA_CHECK_BEST` stated as SHA-256
  unconditionally.
- Q9 **22 / 23**, wrong claim ². Own 4 / 4, Q5 part 6.5 (the slip),
  Q6 part **6 / 6** — the `hardware.c` wiring that Jev's d, e and f all
  lost, reached here as a chain body at 0.39 — Q8 part 5.5. 70 bodies
  against f's 61; the one question where pplx drew more than Jev.

## Where the points were lost

Seven and a half points.

**Writer, 4.0** — the fact was in the evidence:

| Q | lost | where it was |
|---|---|---|
| 4 | 1.0 `decode_expect_error()` | `test_lzip_decoder.c` (eight bodies) |
| 6 | 1.0 allocation failures | `stream_decode_mt()` body, quoted on both sides |
| 6 | 0.5 `is_direct_mode_needed()` | same |
| 8 | 0.5 `SEQ_INDEX_WAIT_OUTPUT` half | `stream_decode_mt` seed (2.10) |
| 9 | 0.5 "16 bytes" slip | `LZMA_STREAM_HEADER_SIZE` in the bodies it quotes |
| 9 | 0.5 reorder case | the hash code it quotes |

**Judge, 3.5** — the body was never in front of the writer:

| Q | lost | what the judge did |
|---|---|---|
| 3 | 0.5 `simple_code()` | `simple_coder.c` not a seed, not reached |
| 4 | 1.0 `license-check.sh` | not reached; the only road is `tests/Makefile.am` → name `xzgrep_expected_output` → mention in the script's exemption list; which step failed is in the log (`grep xzgrep_expected_output`) |
| 5 | 1.0 header outcomes | `stream_flags_decoder.c` / `stream_flags.h` not reached; 4 seeds |
| 5 | 0.5 fixtures | `tests/files/README` not reached |
| 7 | 0.5 `coder_normal()` | offered at 0.30, under `JEV_FOLLOW_MIN` 0.5 |

**Reach, 0.**

Run f on the same questions lost 4.0: writer 2.5, judge 1.0, reach 0.5.
The judge swap costs 2.5 judge points, three of them on the two
questions where pplx drew 4 and 6 seeds (Q5, Q7) against Jev's ≈ 45 and
8. The writer's 4.0 against 2.5 is the same writer on thinner evidence
plus the Q6 omissions; the two wrong claims are both the writer's.

## What the judge did — from the logs (Q7, Q8 and one earlier run)

- **Seeds.** Fewer skills over the 2.0 cut on the narrow questions (Q5
  4, Q7 6, Q6 7, Q4 8 against Jev's 8–45), the same on the broad ones
  (Q9 15 vs 15, Q1 2 vs 2). This is where the 3.5 judge points come
  from. The log prints "kept N of 400 (score >= 2.0)" and nothing about
  what sits at 1.5–2.0, so whether the missing bodies are just under
  the cut is not yet known.
- **Names.** `(none of these)` wins often; `coder_normal` at 0.30 is the
  measured case. On Q9 the chains went further than Jev's (`hardware.c`).
- **Rejects** are softer than Jev's: many bodies at reject 0.44–0.69
  become "not sure: continue" under `JEV_SURE_REJECT=0.75` and turn into
  leads or helpers. Costs characters, not points, so far.
- **Derived copies**: the `.po` files at derived 0.98–0.99, all
  rejected. Clean.
- **Triage**: the skips in the Q7 and Q8 logs are the right ones
  (`file_io` ×29 include sites, `lzma_crc32` ×38, `in_pos` ×27,
  `lzma_index_append` ×18); the one group next to a key fact
  (`lzma_index_hash_append`, 3 of 4 skipped) skipped call sites that
  were already inside seed bodies. The earlier "pplx loses on the
  triage" impression came from the afternoon runs with the untriaged
  `_file_places` candidates and the 27B writer; it does not hold on f's
  code.
- **Honesty.** With less in front of it, the writer named what it did
  not have in every answer (`coder_normal()`, `io_open_src_real()`,
  `lzma_index_append()`, the two Capsicum no-ops, `uncompress()` …).
  All of those lists were checked against the sources and were accurate.
  The evidence index from f's change is doing that.

## Notes for the next runs

- **pplx-decider is a usable judge for this stack**: −3.5 points
  against Jev (−4.7 %) at 34 % of the judge cost, with the thresholds
  still Jev's. Clef was −8 on three questions at 6× the cost.
- **First measurement, not a change:** one print line in the seed stage
  listing the skills between 1.5 and 2.0 with their scores, on Q5 and
  Q7. If `stream_flags_decoder.c`, `tests/files/README` and
  `coder_normal` sit there, the seed cut is the lever and the number
  reads off the print. If not, the next lever is `JEV_FOLLOW_MIN`
  (count the names at 0.3–0.5 that lost to `(none of these)` over the
  nine logs). Either is one variable against this file as baseline.
- `JEV_SURE_REJECT` for pplx stays reserved as a later one-variable
  run; it has cost characters, not points.
- Not a prompt change. "Follow more" in the names question would move
  `coder_normal` and `struct`, `This`, `size_t` alike — the run-c
  "dead end" lesson.
- The writer's share (4.0 here, 2.5 in f) is the same three facts plus
  one bad night on Q6; the writer-prompt candidate from f's notes
  stands, measured on the Jev arm first.
- Retrieval time doubled on OpenRouter (chains 20–41 s). Worth a line
  in the README if pplx becomes a documented option; not a code item.
- The afternoon partial runs above and the Clef arm are recorded here
  and nowhere else; the Qwen3.5-27B / Qwen3.8-27B writer arm is still
  the next one-variable run after this one, on pplx's evidence.