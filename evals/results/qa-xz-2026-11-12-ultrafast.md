# xz question set — ultra-fast profile (2026-11-12, afternoon)

Code: working copy with today's uncommitted speed changes on top of the
morning state (commit hash not recorded here):

1. search: a literal of 3+ characters goes to the trigram index whole
   (`server.h`, not `server` + `h`);
2. search: a name is no longer read in full when it is going to be
   dropped by `JEV_EXPAND_MAX_HITS` anyway (`max_results=max_hits + 1`);
3. `store.py`: the body row is joined only when a search part is shorter
   than 3 characters;
4. `store.py`: index `body_keys_body_key (body_id, key)`;
5. search ahead (`JEV_SEARCH_AHEAD`, off by default, 1 here): the first hop's name
   searches run for all 20 candidates while the judge scores them;
6. `JEV_FINAL_PASS` switch (0 here);
7. timing lines (search detail, slowest names, connection wait).

xz at `7baf6835`.
Writer: DeepSeek V4.1 Flash on Isoquant ($0.035 / M in, $0.30 / M out),
thinking off.
One run per question, in order, no reruns. Every question vector was
read from the store. Graded from the answers; the server log of all nine
runs was kept and read (no `final:` lines in it, so the final pass was
off in every run; `searched ahead` is present in every run).

## Settings

The speed profile with 2 hops, plus:

```properties
JEV_FINAL_PASS=0
JEV_SEARCH_AHEAD=1
JEV_GREP_CONCURRENCY=16   # default, written out here
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
JEV_FINAL_PASS=0
JEV_SEARCH_AHEAD=1
JEV_GREP_CONCURRENCY=16
JEV_CONCURRENCY=256
QUESTION_VECTOR_CACHE=1
WRITER_REASONING=none
JEV_RETRY_BAND=0
JEV_PREV_BODY_MAX_CHARS=15000
JEV_TRIAGE_DEFS=1
JEV_TRIAGE_AROUND=3
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

| Q | topic | score | speed 2 hops | speed 3 hops | reliable hybrid | wrong claims | judge $ | writer $ | total $ | evidence s | total s | seeds | bodies | chars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `.note.GNU-stack` | 4.0 / 4 | 4.0 | 3.75 | 4.0 | 0 | 0.0094 | 0.0017 | 0.0111 | 1.7 | 5.0 | 2 | 8 | 123 k |
| 2 | sandboxing | 5.0 / 5 | 5.0 | 5.0 | 5.0 | 0 | 0.0064 | 0.0032 | 0.0096 | 2.35 | 8.6 | 19 | 36 | 225 k |
| 3 | full decompression path | 7.25 / 10 | 7.25 | 8.0 | 9.25 | 1 | 0.0248 | 0.0036 | 0.0284 | 3.25 | 8.7 | 16 | 86 | 225 k |
| 4 | test fixture integrity | 4.5 / 7 | 4.25 | 5.0 | 5.25 | 1 | 0.0111 | 0.0019 | 0.0130 | 2.0 | 4.9 | 4 | 22 | 130 k |
| 5 | padding, next stream, garbage | 6.0 / 7 | 5.5 | 5.5 | 5.75 | 0 | 0.0113 | 0.0023 | 0.0136 | 2.4 | 5.7 | 11 | 26 | 167 k |
| 6 | memory limit, threaded decoder | 5.75 / 6 | 5.0 | 5.75 | 5.75 | 0 | 0.0091 | 0.0024 | 0.0115 | 2.2 | 5.7 | 7 | 21 | 164 k |
| 7 | when xz deletes the input | 5.25 / 6 | 5.0 | 4.5 | 5.25 | 0 | 0.0161 | 0.0019 | 0.0180 | 2.2 | 6.0 | 7 | 15 | 139 k |
| 8 | attacker modifies the Index | 4.5 / 6 | 4.25 | 4.75 | 5.25 | 1 | 0.0078 | 0.0021 | 0.0099 | 4.6 | 7.9 | 7 | 22 | 138 k |
| 9 | long concatenated-streams question | 19.0 / 23 | 21.25 | 20.75 | 21.0 | 0 | 0.0186 | 0.0042 | 0.0228 | 2.45 | 7.7 | 13 | 62 | 313 k |
| **total** | | **61.25 / 74 (82.8 %)** | **61.5** | **63.0** | **66.5** | **3** | **0.115** | **0.023** | **0.138** | **23.3** | **60.2** | **86** | **298** | **1.62 M** |

Per answer: $0.015 on average ($0.010 to $0.028); 6.7 s on average
(4.9 to 8.7 s); evidence gathering 2.6 s on average (1.7 to 4.6 s), 2.3 s
without the Q8 outlier (one verdict round of 16 calls took 2.95 s; the
same round takes 0.4–0.6 s everywhere else in the log).

Against the other arms:

| | this run | speed, 2 hops | speed, 3 hops | reliable hybrid 11-12 | Fable 5.1 agent |
|---|---|---|---|---|---|
| points | 61.25 / 74 (82.8 %) | 61.5 (83.1 %) | 63.0 (85.1 %) | 66.5 (89.9 %) | 69 (93.2 %) |
| judge $ | 0.115 | 0.142 | 0.180 | 0.095 | — |
| total $ | 0.138 | 0.166 | 0.205 | 0.135 | 17.55 |
| time s | 60 | 80 | 105 | 396 | 1,736 |
| evidence s per answer | 2.6 | 3.0 | 3.9 (vector stored) | 12 | — |

Against the 2-hop speed run of the morning: 0.25 points behind (inside
the run-to-run movement), judge 19 % cheaper, 1.3 times faster overall.
Most of the 19.4 s saved over the nine questions is the writer (52.5 s
then, 37.1 s now, same model, same kind of evidence); the evidence part
went from 26.9 s to 23.3 s.

xz is the small case for today's search changes: its database has
little history, so its searches were never slow. The same changes took
open62541 Q6 from 8.5 s of evidence gathering to 3.7 s with the final
pass on and 2.8 s with it off.

## Where the time goes

| step | seconds over nine questions | share |
|---|---|---|
| search (stored vector + vector search) | 1.3 | 2 % |
| seed scoring (20 calls, one round; first-hop searches run meanwhile) | 4.3 | 7 % |
| chains (2 hops: triage round and verdict round each; no final pass) | 17.7 | 29 % |
| writer | 37.1 | 62 % |

- Chains: 0.9–2.7 s per question (4.1 s on Q8, the outlier), 558 judge
  calls over the nine (648 in the 2-hop run with the final pass).
- Inside a hop, from the log: search 0.00–0.06 s in hop 1 (done ahead,
  0.06–0.24 s, hidden behind seed scoring) and 0.03–0.22 s in hop 2;
  triage 0.24–0.39 s; verdicts 0.37–0.64 s (1.04 s once, 57 calls).
  The floor is four judge rounds of 0.3–0.5 s each.
- The writer's wait before its first token: 0.8–2.2 s. Twice it ran at
  half speed (Q1 314 tok/s, Q7 335 tok/s; 670–745 tok/s otherwise).

## Per question

- Q1 4.0 / 4. Guard quoted exactly, both build systems, says no C source
  and no build rule emits the note. Nothing lost.
- Q2 5.0 / 5. Same 19 seeds and 36 bodies as in the morning. One gap
  that is not a wrong claim: for `xz` it calls Landlock failures fatal
  and leaves out that an absent Landlock means no sandbox (it says so
  for `xzdec`).
- Q3 7.25 / 10. −1.0 format detection (`auto_decode()`, `coder_init()`),
  not among the 20 candidates. −0.75 inside of the filter chain
  (`decoders[]`, chaining), seen only as a prototype. −0.5 BCJ. −0.25
  `LZMA_TIMED_OUT`. Wrong claim: `lzma_check_finish` placed in
  `SEQ_CHECK`; it is at the end of `SEQ_PADDING`.
- Q4 4.5 / 7. −1.0 `test_compress.sh`, −1.0 `license-check.sh` (read in
  hop 2 and rejected at 0.73). Loader limits from the doc comment only.
  Wrong claim: all `unsupported-*.xz` must pass with `-qQ`; the script
  tests only `unsupported-check.xz`.
- Q5 6.0 / 7. All five padding cases right, the trap named in plain
  words. −0.5 header error cases (short header, CRC32, reserved flags),
  −0.5 the `good-*` fixtures and the no-CRC note.
- Q6 5.75 / 6. Both limits, both direct-mode triggers, the wait, the
  allocation failure, the resume test. −0.25 Index-hash append in
  direct mode.
- Q7 5.25 / 6. −0.75 the open-time checks (`io_open_src_real`): named in
  one line from the man page, body not read. Cites its sources as
  "(body 3)", which is an internal label.
- Q8 4.5 / 6. −1.0 threaded decoder path. −0.25 reordered records.
  Wrong claim: a size in a longer encoding than needed is said to pass
  until the Backward Size check; the number decoder rejects it, as the
  answer's own point 1.2 says.
- Q9 19.0 / 23. Own 3.25 / 4. Q5 part 6.25. Q6 part 4.25 (no allocation
  failure, no mapping of the `xz` options, cites the single-threaded
  memory test). Q8 part 5.25. No wrong claim (the two risky ones,
  `lzma_index_hash_size()` from decoded Blocks and `LZMA_FAIL_FAST` at a
  truncated Block Header, were checked in the source).

## Where the 12.75 points were lost

| cause | points | items |
|---|---|---|
| judge | 5.0 | Q4 `test_compress.sh` 1.0, `license-check.sh` 1.0; Q5 stream-header body 0.5; Q7 `io_open_src_real` 0.75; Q8 threaded decoder 1.0; Q9 stream-header body and fixtures 0.75 |
| writer | 4.25 | Q3 0.5; Q4 0.5; Q5 0.5; Q6 0.25; Q8 0.5; Q9 2.0 |
| reach | 2.75 | Q3 `auto_decoder.c` 1.0 and BCJ 0.5 (K=20); Q9 `hardware.c`, format document, `container.h`, threaded memory test 1.25 |
| hop count | 0.75 | Q3 inside of the filter chain |

The final pass cannot be separated out on xz from this run: there is no
run of the same day with today's code and the final pass on. It was
separated on open62541.

Note on the final pass, from the open62541 runs of the same afternoon:
with `JEV_FINAL_PASS=0`, Q7 and Q8 scored as before (6.0; 7.75 and
8.25), Q6 scored 5.0 against 6.0–7.25. In the Q6 log one body was lost
to the switch: `UA_Subscription_addRetransmissionMessage` (accept 0.19,
continue 0.40, reject 0.41), which the final pass had accepted at
0.62–0.78 in six earlier runs. The rest of that Q6 loss was triage
(`Subscription_setPublishTimer`: 3 places, 3 skipped) and the writer.

## Critical or good-to-have

| Q | critical misses | good-to-have misses |
|---|---|---|
| 1 | none | 0 |
| 2 | none | 0 |
| 3 | format detection, the first stage of the path (reach, K=20) | 3 |
| 4 | none | 3 |
| 5 | none | 2 |
| 6 | none | 1 |
| 7 | the files `xz` refuses to process in place (triage) | 0 |
| 8 | none | 2 |
| 9 | none | 7 |
| **total** | **2** | **18** |

The two critical misses are the same two as in both morning speed runs.
Neither comes from today's changes: Q3 is the 20-candidate limit, Q7 is
the triage of definition groups (also missed by the reliable hybrid).

Wrong claims: 3, all small (Q3, Q4, Q8), each one already made in a
morning run on the same evidence.

## What this run shows

- Today's search changes, search ahead and the missing final pass
  together cost no measurable accuracy on xz: 61.25 against 61.5.
- The one large move is Q9 (21.25 → 19.0): 2.0 of the 4.0 lost points
  are the writer leaving out things it had, 1.25 are bodies that did not
  arrive (13 seeds, 15 in the morning 3-hop run).
- Evidence gathering on xz is now four judge rounds and almost no
  search. Going lower means fewer rounds, a faster judge endpoint, or a
  local embedding model (which only helps for a new question).
- The writer is 62 % of the time. For a robot that takes the evidence
  and needs no prose, the time per question is the 2.6 s.

## Open

- A run of the nine with `JEV_FINAL_PASS=1` and today's code, to price
  the final pass on xz.
- Triage of definition groups (`JEV_TRIAGE_DEFS`): the cause of the Q7
  critical miss here and of the open62541 misses (`addNode_*`,
  `setOverflowInfoBits`).
- Seeds just above the 1.9 cut change from run to run (open62541 Q7).
- Internal labels in answers ("body 3").