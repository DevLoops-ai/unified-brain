# github-docs question set — a fresh Claude Fable 5.2 agent, high effort (2026-11-23)

The agent comparison for the help-centre set, run the same afternoon as
the unified-brain run in `qa-github-docs-2026-11-23-pointers.md`. One
fresh agent got a clean copy of the documentation repository and the
nine questions, and nothing else.

Questions and keys: `evals/questions/github-docs.md` — nine questions, 50
reference points. Answers:
`evals/runs/fable-5-2-high-github-docs-2026-11-23/`.

## Read this first

| | Fable 5.2 agent, high effort | unified-brain, same day |
|---|---|---|
| points | 48.5 / 50 (97.0 %) | 46.0 / 50 (92.0 %) |
| wrong claims | 0 found | 1 |
| presentable as it is | 9 of 9 | 7 of 9 |
| time, nine questions | 359 s | 57 s |
| time per answer | 40 s | 6.4 s |
| tool calls | 47 | — |
| tokens reported | 188,180 | 117,433 (the writer: 105,710 in, 11,723 out) |
| cost | ≈ $3 to $4 (estimate, see below) | writer $0.007; judge not reported |

- The dollar figure for the agent is an estimate, not a bill. The harness
  reported one token figure for the whole agent and no transcript. The
  estimate uses the two rates of `qa-xz-2026-11-13-fable-5-2-agents.md`:
  $12.2 for 793 k reported tokens at medium effort and $49.6 for 2,287 k
  at max effort. At those rates 188,180 tokens are $2.90 and $4.08. High
  effort was not measured on 11-13.
- unified-brain's judge cost is not known for this day: the direct
  TypeSafe key reports none.
- The gap is 2.5 points. The grader's own drift is about a quarter point
  per question (see "Grading"), so on single questions a gap of 0.25 is
  "level"; over the set the agent is ahead.

## Setup

- Model: Claude Fable 5.2 (`claude-fable-5-2`), the general-purpose agent
  of the Claude Code harness, effort set to `high`.
- **One agent for all nine questions**, answered in order, Q1 to Q9. The
  xz agent runs used nine agents, one per question. Here what the agent
  read for an early question was still in its context for the later
  ones.
- Source: github/docs at `a8dbaf5`, copied into its own folder with the
  sub-folders `content`, `data` and `.github` (7,795 files). No `src/`
  and no `assets/`: unified-brain's run left `src/` out at question time
  and its index has no `assets/`.
- The agent got shell, grep and file reading. It was told to use only
  that folder: no other folder, no web, no memory or past-conversation
  tools, and nothing from what it remembers about GitHub.
- It did not see the keys, the grading or any unified-brain answer.
  Before the run the keys and the unified-brain results file were packed
  into an archive and the open copies removed from the machine; they
  were put back after the run. The author's uploaded files of the day
  (unified-brain answers and logs, no keys) stayed on disk; the agent
  was told not to read them.
- The prompt is printed at the top of each answer file. The questions
  were given without their titles, because two titles give the answer
  away ("where the docs say no").
- One run, no re-run.

Two things the agent was told that unified-brain's writer is not told:

- What the repository's tags mean (`{% data reusables.a.b %}` is the file
  `data/reusables/a/b.md`; `{% ifversion … %}` marks text for some
  products only; `fpt`, `ghec`, `ghes`).
- To write product names out and leave no raw `{% … %}` tags in the
  answer.

Time: the agent ran `date +%s` before and after each question. The nine
spans add up to 359 s. The harness reported 374 s for the whole agent;
the first question started 17 s after the launch.

## Grading

Reference points hit, same keys as the unified-brain run. Graded by
Claude Fable 5.2 in the session that built and graded the unified-brain
run of the same day. The grader is the same model as the contestant and
knew which system each answer came from. About 25 concrete claims of the
agent were checked against the source (numbers, file names, quoted
sentences, version blocks); none was wrong. Grades of this grader have
moved by about a quarter point between gradings on the same day.

## Results per question

| Q | topic | agent | time s | unified-brain | time s | difference |
|---|---|---|---|---|---|---|
| 1 | Actions time limits | 5.0 / 5 | 36 | 4.5 | 6.0 | +0.5 |
| 2 | forks on delete and visibility change | 4.5 / 5 | 46 | 4.25 | 6.1 | +0.25 |
| 3 | 2FA app set up by hand | 4.0 / 4 | 20 | 3.75 | 3.6 | +0.25 |
| 4 | retention of logs and artifacts | 6.0 / 6 | 33 | 5.5 | 5.7 | +0.5 |
| 5 | linear history and signed commits | 7.75 / 8 | 70 | 7.0 | 11.1 | +0.75 |
| 6 | SMS codes in Nigeria on Enterprise Server | 5.25 / 6 | 52 | 5.5 | 7.1 | −0.25 |
| 7 | locked out, phone lost | 6.0 / 6 | 45 | 6.0 | 6.0 | 0 |
| 8 | REST API requests per hour | 5.0 / 5 | 24 | 4.75 | 6.6 | +0.25 |
| 9 | GitHub Pages for a small shop | 5.0 / 5 | 33 | 4.75 | 5.0 | +0.25 |
| **total** | | **48.5 / 50 (97.0 %)** | **359** | **46.0 (92.0 %)** | **57** | **+2.5** |

Tool calls (47) and tokens (188,180) were reported for the whole agent,
not per question.

unified-brain reaches 46.0 of 48.5 points (95 %) of the agent in 16 % of
the time.

## Where points were lost

Agent (1.5 lost):

- Q2 (−0.5): of the two other rows of the forks table it has one (a
  public repository is deleted: an active fork becomes the new
  upstream). It does not say what happens to private forks when a
  private repository is made public.
- Q5 (−0.25): does not say that a merge method needs write permission.
- Q6 (−0.75): gives no reason against SMS (interception, phishing,
  unreliable delivery) (−0.5); does not say that an organization or
  enterprise can block content access for members who use SMS 2FA
  (−0.25).

Full marks: Q1, Q3, Q4, Q7, Q8, Q9.

unified-brain (4.0 lost; details in its own file): writer 3.25,
evidence gathering 0.75.

## What stands out

- **Q5, the `{% else %}` branch.** The agent says in its short answer
  that on GitHub Enterprise Server a pull request cannot be merged on
  GitHub when signed commits are required. unified-brain's writer had
  the same file in front of it in every run of the day and left that
  branch out every time (−0.75).
- **Q4 and Q9, the small shared files.** The agent opened
  `checks-and-statuses-retention-scope.md` and
  `no_sensitive_data_pages.md`. These are unified-brain's only two
  evidence misses (−0.5 and −0.25).
- **Q1.** The agent's table has 45 minutes for GitHub-hosted runners and
  24 hours for self-hosted ones, and it notes that the limits table has
  no queue row for GitHub-hosted runners. unified-brain's text has both
  numbers right but its summary table says 24 hours for both (its one
  wrong claim).
- **Q6 is the one question unified-brain wins.** Its answer has a reason
  against SMS and the enterprise block. The agent has neither, though it
  adds something the key does not ask for: on Enterprise Server with
  SAML or CAS sign-in, two-factor authentication is not handled by the
  server at all.
- **Presentability.** All nine agent answers can be shown to an end user
  as they are: a short answer first, product names written out, no raw
  tags, a file named after each statement. unified-brain's Q6 body is
  full of raw `{% ifversion %}` tags and several answers carry "evidence
  8" or "body 3". Part of this gap is the paragraph of instructions
  listed under "Setup", not the model.
- **Cost of the points.** The 2.5 points cost about 6 times the time
  and, on the estimate, several hundred times the writer's cost. The
  judge's share of unified-brain's cost is missing from that
  comparison.

## What this run does not show

- One agent with a growing context is an easier setting than nine fresh
  agents. A run with one agent per question would be the like-for-like
  repeat of the xz agent runs.
- One run. No second run to measure how much the agent's score moves.
- High effort only; medium and max were not run on this set.
- The keys were written by the grader from the same repository, before
  either system ran, and one key (Q1) was corrected after the
  unified-brain baseline. Both systems were graded on the corrected key.