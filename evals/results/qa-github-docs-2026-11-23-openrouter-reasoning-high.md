# github-docs question set — everything through OpenRouter, writer reasoning high (2026-11-23, evening)

The same nine questions as `qa-github-docs-2026-11-23-pointers.md`, on the
same index, a few hours later, with two settings changed:

- `ALL_VIA_OPENROUTER=1` — the judge, the writer and the question vector
  all go through OpenRouter with one key.
- `WRITER_REASONING=high` — the writer thinks before it answers.

Questions and keys: `evals/questions/github-docs.md` — nine questions, 50
reference points.

Code: commit `4febaa5`.
Index: the same database as the afternoon run (github/docs at `a8dbaf5`,
`INGEST_MARKDOWN=1`, `src/` in the index and left out at question time
with `QA_SKIP_PATHS=/src/`).

**Two things changed at once, so this file cannot say what each one did.**
It is a measurement of this setup as a whole. The section "What can be
said about reasoning alone" lists the little that was measured with one
change only.

## Read this first

| | this run | afternoon run (direct providers, reasoning off) | Fable 5.2 agent, high effort |
|---|---|---|---|
| points | 47.75 / 50 (95.5 %) | 46.0 (92.0 %) | 48.5 (97.0 %) |
| wrong claims | 1 (small) | 1 | 0 found |
| time, nine questions | 397 s | 57 s | 359 s |
| time per answer | 44 s (22 to 71 s) | 6.4 s | 40 s |
| judge cost | $0.070 | not reported | — |
| writer tokens | 103,771 in, 26,497 out | 105,710 in, 11,723 out | — |
| points lost to the writer | 1.5 | 3.25 | — |
| points lost to evidence gathering | 0.75 | 0.75 | — |

- 1.75 points more than the afternoon, all of them writer points. The
  evidence misses are the same two files.
- 7 times slower than the afternoon, and slower than the agent. Almost
  half of the time (190 of 397 s) is one step: getting the question's
  vector through OpenRouter.
- The writer's cost was not computed: the price of the route OpenRouter
  used for the writer was not recorded.

## Setup

- Judge: Jev 1.14 through OpenRouter, for seed scoring, chains and
  triage. Because it goes through OpenRouter, the footer reports its
  cost; the afternoon run used the direct TypeSafe key, which reports
  none.
- Writer: through OpenRouter. The model name set in `.env` for this run
  (`OPENROUTER_LLM_MODEL`, or the default DeepSeek V4.1 Flash) was not
  recorded; check it before publishing.
- Question vector: Qwen3-Embedding-8B through OpenRouter, pinned to
  DeepInfra. With the switch on the code does not use `QUERY_EMBED_URL`
  (Fireworks).
- Everything else as in the afternoon file: `JEV_PREFILTER_TOP_K=40`,
  `JEV_MIN_SCORE=1.9`, two hops, `JEV_POINTERS=1`, `JEV_NAMES_TEXT=1`,
  `QA_SKIP_PATHS=/src/`. The `.env` of this run was not pasted; these
  lines are taken from the afternoon's block and from what the author
  said changed.
- Questions asked in this order: Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q1, Q2,
  between 19:51 and 20:10 (Athens). One run per question, no reruns.

## Results

| Q | topic | score | afternoon | wrong claims | presentable | judge $ | search s | first token s | total s | seeds | bodies | chars | tokens out |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Actions time limits | 5.0 / 5 | 4.5 | 0 | content yes; raw tags, "evidence 2" | 0.007 | 17.6 | 1.8 | 27.0 | 6 | 13 | 38 k | 1,956 |
| 2 | forks on delete and visibility change | 5.0 / 5 | 4.25 | 0 | yes | 0.010 | 14.9 | 12.5 | 45.1 | 18 | 24 | 60 k | 3,605 |
| 3 | 2FA app set up by hand | 4.0 / 4 | 3.75 | 0 | yes | 0.003 | 12.7 | 1.6 | 21.7 | 3 | 4 | 6 k | 599 |
| 4 | retention of logs and artifacts | 5.5 / 6 | 5.5 | 0 | yes, with raw tags | 0.008 | 26.2 | 7.0 | 46.5 | 18 | 24 | 52 k | 2,992 |
| 5 | linear history and signed commits | 7.0 / 8 | 7.0 | 0 | yes | 0.017 | 19.6 | 30.1 | 71.4 | 15 | 47 | 132 k | 7,487 |
| 6 | SMS codes in Nigeria on Enterprise Server | 5.75 / 6 | 5.5 | 1 | short answer yes, body no (raw tags) | 0.009 | 19.7 | 12.0 | 50.0 | 12 | 18 | 46 k | 3,152 |
| 7 | locked out, phone lost | 6.0 / 6 | 6.0 | 0 | yes | 0.006 | 38.4 | 7.0 | 56.5 | 7 | 17 | 35 k | 2,412 |
| 8 | REST API requests per hour | 4.75 / 5 | 4.75 | 0 | yes | 0.006 | 20.9 | 7.1 | 41.8 | 8 | 11 | 25 k | 2,065 |
| 9 | GitHub Pages for a small shop | 4.75 / 5 | 4.75 | 0 | content yes; many raw tags | 0.004 | 20.0 | 6.1 | 37.0 | 6 | 10 | 22 k | 2,229 |
| **total** | | **47.75 / 50 (95.5 %)** | **46.0** | **1** | | **0.070** | **190** | | **397** | **93** | **168** | **416 k** | **26,497** |

How the columns were filled: seconds, cost, seeds, bodies, characters and
tokens are the footer of each answer. "tokens out" includes the writer's
thinking. Claims were checked against a clone of github/docs at the same
commit.

The evidence is the same as in the afternoon: 93 seeds and 168 bodies
against 92 and 169.

## Where the time goes

| step | seconds over nine questions | share | afternoon |
|---|---|---|---|
| search (question vector through OpenRouter + vector search) | 190 | 48 % | 10.4 |
| seed scoring | 15 | 4 % | 2.7 |
| chains | 37 | 9 % | 18.0 |
| writer | 156 | 39 % | 25.9 |

- The search step took 12.7 to 38.4 s per question. In the afternoon,
  with the vector from Fireworks, it took about 1 s.
- The writer wrote 135 to 204 tokens per second on eight questions and
  427 on one (Q1), so its speed on this route is not stable. In the
  afternoon, on Isoquant: 407 to 578.
- Thinking, estimated from the length of each answer at 4.2 characters
  per visible token: about 540 to 1,460 tokens per answer, and about
  4,900 on Q5 (30 s before the first word).

## Where the points went

2.25 points lost:

| cause | points | where |
|---|---|---|
| writer | 1.5 | Q5 1.0, Q6 0.25, Q8 0.25 |
| judge (a file named in a seed was offered and not opened) | 0.75 | Q4 0.5, Q9 0.25 |

- Q5: the `{% else %}` branch of `required-signed-commits.md` (on
  Enterprise Server a pull request cannot be merged on GitHub when
  signed commits are required) is left out again, with thinking on.
  Write permission is not mentioned.
- Q4: this answer states that `checks-and-statuses-retention-scope.md`
  "was not read". So the file was reached and the judge did not open it.
  Q9: `no_sensitive_data_pages.md`, same pattern.
- The one wrong claim (Q6): Nigeria "would fall between Netherlands
  Antilles and New Zealand" in the country list. By the alphabet it
  would fall after New Zealand. Nigeria is absent either way.

Points gained against the afternoon, all from the writer: Q1 +0.5 (no
wrong table cell on the queue time), Q2 +0.75 (all four rows of the forks
table), Q3 +0.25 (the second half of the tip), Q6 +0.25 (the reasons
against SMS).

New facts no earlier answer had: "Rebase and merge" is limited to 100
commits (Q5); the search endpoints have their own per-minute limits (Q8);
the automated account recovery is documented for GitHub.com and
Enterprise Cloud only (Q7).

## What can be said about reasoning alone

At 15:20 the same day, three questions were asked with
`WRITER_REASONING=high` and nothing else changed (direct providers,
writer on Isoquant):

| Q | reasoning off | reasoning high, Isoquant | time off | time high |
|---|---|---|---|---|
| 1 | 4.5 | 5.0 | 6.0 s | 9.3 s |
| 2 | 4.25 | 4.25 | 6.1 s | 9.3 s |
| 3 | 3.75 | 3.75 | 3.6 s | 5.6 s |

On those three, thinking fixed the one wrong claim (Q1) and added about
3 s per answer. Three questions are too few to say more. The two
providers share one question with reasoning high (Q3: 3.75 on Isoquant,
4.0 through OpenRouter), which is inside the grader's noise.

## What this run does not show

- Whether the 1.75 points come from thinking, from the writer route on
  OpenRouter, or from run-to-run variation. One run per question.
- The writer's cost on this route.
- Why the question vector takes 13 to 38 s through OpenRouter.
- Graded by Claude Fable 5.2, the grader of the other two github-docs
  files of the day, with the afternoon's grades in view.