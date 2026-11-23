# github/docs — question set

Nine questions on GitHub's help centre, the public repository
[github/docs](https://github.com/github/docs). This set tests unified-brain
on prose (Markdown articles) instead of program code.

The reference points were read from the files at commit `a8dbaf5e`
(snapshot, 2026-11-23), before any run. The index used for the runs is a
`--snapshot` ingest of that commit with `INGEST_MARKDOWN=1` (one piece per
heading) and `INGEST_SKIP_PATHS=/assets/` (images left out): 11,775 files,
44,050 pieces.

How this repository differs from a code repository, and what the questions
are built to test:

- Articles are under `content/`. Many paragraphs are not in the article:
  the article holds a reference such as
  `{% data reusables.two_fa.manual-totp-app-setup %}` and the text is in
  `data/reusables/two_fa/manual-totp-app-setup.md`. Q3, Q4 and Q8 can only
  be answered from such files; Q7 and Q9 need them for part of the answer.
- Product names are variables (`{% data variables.product.prodname_dotcom %}`
  = "GitHub", from `data/variables/product.yml`).
- Text can apply to some products only: `{% ifversion fpt or ghec %}` …
  `{% endif %}`. `fpt` = Free, Pro and Team on GitHub.com, `ghec` = GitHub
  Enterprise Cloud, `ghes` = GitHub Enterprise Server. Q6 depends on this.

Grading: one point per reference point unless a number is given. Grade by
facts and values, not by wording. A "trap" line says where a keyword search
goes wrong. Raw `{% … %}` tags left in an answer are a presentation flaw,
not a wrong claim.

Total: 50 points (Q1 5, Q2 5, Q3 4, Q4 6, Q5 8, Q6 6, Q7 6, Q8 5, Q9 5).

---

## Q1 — Actions: how long things may run

> How long can a single job run in GitHub Actions, how long can a whole workflow run last, and how long can a job wait for a runner before it is cancelled? Is it different on our own self-hosted runners, and can GitHub Support raise any of these limits?

Kind: one article, a table. File: `content/actions/reference/limits.md`.

Reference points:

1. GitHub-hosted runners: a job may run for 6 hours of execution time; at
   the limit the job is terminated and fails.
2. Self-hosted runners: a job may run for 5 days of execution time.
3. A workflow run may last 35 days; the period includes execution, waiting
   and approval time; at the limit the run is cancelled.
4. Self-hosted: a job can be in the queue for 24 hours before it is
   automatically cancelled.
5. Support cannot raise any of these four (the table says "No" for each).
   Limits Support can raise include job concurrency, the 50 re-runs per
   workflow run and the workflow trigger event rate.

Trap: the table also has "Gate approval time, 30 days" (waiting on an
environment approval). That is not the workflow run limit. The table gives
no queue-time limit for GitHub-hosted runners; an answer that states one
invented it.

---

## Q2 — forks when a repository is deleted or changes visibility

> We are about to delete a private repository that several people have forked, and to make one of our public repositories private. What happens to the forks in each case? And what happens to a person's fork when we remove that person's access to a private repository?

Kind: one article plus one reusable. Files:
`content/pull-requests/reference/forks.md` (section "What happens to forks
when a repository is deleted or changes visibility"),
`data/reusables/repositories/deleted_forks_from_private_repositories_warning.md`.

Reference points:

1. A private repository is deleted: its private forks are also deleted.
2. A public repository is made private: its public forks stay public, in a
   separate network.
3. The other two rows of the table, for completeness: a public repository
   is deleted — an active public fork becomes the new upstream of the
   network; a private repository is made public — private forks stay
   private and disconnect into separate private networks.
4. Removing a person's access to a private repository deletes their forks
   of it; local clones are kept. The same happens when a team's access is
   revoked or the team is deleted, unless the member has access through
   another team. (From the reusable.)
5. Side effects and duties: making a public repository private can also
   affect stars, watchers, the dependency graph, Dependabot alerts and code
   scanning; you are responsible for making sure people who lost access
   delete confidential material; Git data of a network can stay reachable
   from other repositories of the network after a fork is deleted.

Trap: two passages apply to GitHub Enterprise Server only (`ifversion
ghes`): LDAP Sync keeping the forks, and anonymous Git read access. Stating
them as general behaviour is wrong.

---

## Q3 — two-factor authentication: setting up the app by hand

> My authenticator app cannot scan the QR code. Which values do I have to type in by hand to set up two-factor authentication on GitHub?

Kind: the answer is in a reusable file; the article only points to it.
Files: `data/reusables/two_fa/manual-totp-app-setup.md`; the pointer is the
section "Manually configuring a TOTP app" of
`content/authentication/securing-your-account-with-two-factor-authentication-2fa/configuring-two-factor-authentication.md`.

Reference points:

1. Type `TOTP`; Label `GitHub:<username>`, where the username is the
   GitHub handle (example `monalisa`).
2. Secret: the encoded setup key, shown when you click "Setup key" during
   configuration.
3. Issuer `GitHub`; Algorithm SHA1 (the default); Digits 6 (the default);
   Period 30 seconds (the default).
4. Context from the article: the "setup key" is the TOTP secret and can be
   saved to configure several devices; if 2FA is already enabled, adding a
   device means re-configuring the TOTP app from the security settings.

Trap: the article's section has no text of its own, only the reference. An
answer with general advice about TOTP apps and none of these exact values
did not reach the reusable file.

---

## Q4 — Actions: how long logs and artifacts are kept

> How long does GitHub keep the logs and artifacts of our workflow runs, and how far can we change that? Is it different for public and private repositories?

Kind: reusable inside a reusable (two steps), with product differences.
Files: `data/reusables/actions/about-artifact-log-retention.md`, which
includes `data/reusables/actions/checks-and-statuses-retention-scope.md`;
pointed to from the section "Configuring the retention period for checks,
workflow runs, commit statuses, artifacts, and logs in your repository" of
`content/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository.md`.

Reference points:

1. Default: 90 days, then automatic deletion (checks, workflow runs, commit
   statuses, artifacts and log files).
2. On GitHub.com plans: public repositories, between 1 and 90 days; private
   repositories (and internal ones on Enterprise Cloud), between 1 and 400
   days.
3. On GitHub Enterprise Server: between 1 and 400 days.
4. A changed period applies to new objects only, not to existing ones; a
   managed repository or organization cannot go above the limit set by the
   organization or enterprise that manages it.
5. From 1 October 2026 the policy also covers checks, workflow runs and
   commit statuses; until then those were kept 400+ days whatever the
   setting.
6. Scope (the inner reusable): the policy applies to checks data (check
   suites, check runs) and commit statuses, including those created by
   third-party integrations, not only to data created by GitHub Actions.
   Where it is set: repository settings, Actions, General, under "Check,
   workflow run, status, artifact and log retention".

Trap: the same article has "Cache retention" (default 7 days, up to 90
days public or 365 days private). That is the dependency cache, a different
setting; mixing the two is an error.

---

## Q5 — linear history, signed commits and the merge methods

> We want a linear history on `main` and we also require signed commits there. Which ways of merging a pull request can we still use, how do we enforce the linear history, and what problems should we expect?

Kind: several articles and reusables joined. Files:
`content/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github.md`;
`content/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches.md`
(sections "Require linear history", "Require signed commits");
`data/reusables/pull_requests/default_merge_option.md`,
`squash_and_merge_summary.md`, `rebase_and_merge_summary.md`,
`rebase_and_merge_verification.md`, `rebase_and_merge_verification_2.md`;
`data/reusables/repositories/required-signed-commits.md`.

Reference points:

1. The three methods: merge commit (the default, `--no-ff`, all commits
   plus a merge commit); squash and merge (the commits become one commit);
   rebase and merge (the commits are added one by one, no merge commit).
2. "Require linear history" on the protected branch stops merge commits
   from being pushed to it, so a pull request must be merged by squash or
   by rebase.
3. Precondition: the repository must allow squash merging or rebase
   merging before linear history can be required; each method is switched
   on in the repository's settings and needs write permission to use.
4. Rebase and merge: the commits reach the base branch without commit
   signature verification. GitHub creates modified commits, so it cannot
   sign them as a system user, and it has no access to the committer's
   private signing keys.
5. Workaround for 4: rebase and merge locally, then push to the pull
   request's base branch.
6. Squash and merge with required signatures (GitHub.com plans): GitHub
   signs the final squash commit, but unsigned commits on the head branch
   can still block the merge, because GitHub checks the commits of a test
   merge. Remedy: rewrite and sign those commits, or have someone with
   bypass permission merge.
7. GitHub Enterprise Server: with required signed commits, pull requests
   cannot be merged on GitHub at all; merge locally and sign the result
   before pushing.
8. Other points to expect, any two: rebase on GitHub differs from
   `git rebase` (always new committer information and new SHAs, drops
   empty commits); squash loses who made which change and when, and a
   long-running branch shows the squashed commits again; with a merge
   queue the queue decides the method; a repository method that conflicts
   with a rule blocks merging.

Trap: "squash is signed by GitHub, so it always works" is the tempting
short answer. Point 6 says otherwise.

---

## Q6 — text-message codes where the docs say no

> I work from Nigeria and my company runs GitHub Enterprise Server. Can I get my two-factor authentication codes by text message, and can I add a second phone number as a backup?

Kind: the honest answer is "no" twice; the tempting text describes the
steps. Files:
`content/authentication/securing-your-account-with-two-factor-authentication-2fa/configuring-two-factor-authentication.md`
(section "Configuring two-factor authentication using text messages");
`…/countries-where-sms-authentication-is-supported.md`;
`…/recovering-your-account-if-you-lose-your-2fa-credentials.md` (section
"Authenticating with a fallback number");
`data/reusables/two_fa/sms-warning.md`, `sms-cap-note.md`.

Reference points:

1. (2 points) Text-message 2FA is documented for GitHub.com plans only.
   The text-message section is inside `{% ifversion fpt or ghec %}`, the
   article's intro offers "or via text message" under the same condition,
   and the countries article exists for `fpt` and `ghec` only. It does not
   apply to GitHub Enterprise Server.
2. Nigeria is not on the list of supported countries and regions; for a
   country not on the list GitHub cannot deliver text messages reliably,
   and the article says to use a TOTP app instead.
3. A second number: "Configuring a fallback SMS number in addition to your
   primary SMS number is no longer supported"; the docs recommend
   registering several authentication methods instead.
4. The docs strongly recommend a TOTP app, with security keys as backup,
   over SMS: SMS can be intercepted, does not resist phishing, is
   unreliable to deliver and is not supported in all countries.
5. What to do instead: configure a TOTP app, then add a security key or a
   passkey, and keep the recovery codes. Also: an organization or
   enterprise can block content access for members who use SMS 2FA.

Trap: the steps for adding a phone number are easy to find and easy to
repeat. An answer that gives them as if they applied here fell in.

---

## Q7 — locked out: phone lost, no recovery codes

> I lost the phone with my authenticator app and I cannot find my recovery codes. I still know my password. How do I get back into my GitHub account, how long does it take, and can Support simply switch two-factor authentication off for me?

Kind: one article whose steps and warnings are mostly reusables. Files:
`content/authentication/securing-your-account-with-two-factor-authentication-2fa/recovering-your-account-if-you-lose-your-2fa-credentials.md`;
`data/reusables/two_fa/support-may-not-help.md`, `unlink-email-address.md`;
`data/reusables/accounts/start-automated-recovery-with-password.md`,
`choose-recovery-verification-factor.md`,
`automated-recovery-review-period-notice.md`.

Reference points:

1. Support cannot switch it off: for security reasons GitHub Support will
   not restore access to an account with 2FA when the 2FA credentials or
   the recovery methods are lost.
2. Try first what may already be on the account: a passkey (it satisfies
   both the password and the 2FA requirement) or a registered security
   key.
3. With the password but no 2FA credentials and no recovery codes (GitHub.com
   plans): have a one-time password sent to the verified email address,
   then prove identity with a recovery factor — a device previously used
   to sign in, an SSH key, or a personal access token.
4. The steps: sign in with user name and password; under "More options"
   click "Begin account or email recovery"; "I understand, get started";
   "Send one-time password" (it goes to the primary and the backup email
   addresses); type it in; choose the recovery factor.
5. Time: a member of GitHub Support reviews the request and emails within
   three business days; approved means a link to complete the recovery,
   denied means the email says how to contact support.
6. If no method works, access to the account is permanently lost; the
   email address can be unlinked from the locked account and linked to a
   new or existing one. A factor can be unavailable even if it was used
   before (for example SSH keys are removed after a period of inactivity).

Trap: the article has a section "Authenticating with a fallback number";
its own note says a fallback SMS number is no longer supported. Offering
it as a way back in is wrong.

---

## Q8 — REST API: requests per hour

> Our CI script calls the GitHub REST API. How many requests per hour do we get with no token, with a personal access token, with the `GITHUB_TOKEN` inside a workflow, and as a GitHub App installation?

Kind: every number is in a reusable file; two articles point to them.
Files: `data/reusables/rest-api/primary-rate-limit-unauthenticated-users.md`,
`…-authenticated-users.md`, `…-github-token-in-actions.md`,
`…-github-app-installations.md`; pointed to from
`content/rest/using-the-rest-api/rate-limits-for-the-rest-api.md` and
`content/actions/reference/limits.md`.

Reference points:

1. No token: 60 requests per hour, counted per originating IP address;
   public data only.
2. Personal access token (an authenticated user): 5,000 requests per hour;
   requests made on the user's behalf by apps count toward the same limit.
   15,000 per hour for an app owned by a GitHub Enterprise Cloud
   organization.
3. `GITHUB_TOKEN`: 1,000 requests per hour per repository; 15,000 per hour
   per repository for resources that belong to an Enterprise Cloud account.
4. GitHub App installation: at least 5,000 per hour; 15,000 on an
   Enterprise Cloud organization; otherwise it grows by 50 per hour for
   each repository above 20 and for each user above 20, up to 12,500.
5. The budgets are shared: requests by a higher-limit app reduce what is
   left for lower-limit methods (the example: 10,000 requests by a
   15,000-limit app use up the 5,000 of the personal access tokens).
   Secondary rate limits apply on top of these.

Trap: 5,000 is the number everyone remembers. For `GITHUB_TOKEN` it is
1,000 per repository.

---

## Q9 — GitHub Pages for a small shop

> Can I run my small online shop on GitHub Pages? What are the limits on size, traffic and builds, and can I publish from a private repository on the Free plan?

Kind: one short article; one fact is in its front matter through a
reusable. Files:
`content/pages/getting-started-with-github-pages/github-pages-limits.md`;
`data/reusables/pages/no_sensitive_data_pages.md`;
`data/reusables/gated-features/pages.md` (named in the article's front
matter, `product:`).

Reference points:

1. Not for a shop: Pages is not intended for, or allowed as, free web
   hosting for an online business, an e-commerce site or software as a
   service; it should not be used for sensitive transactions such as
   passwords or credit card numbers.
2. Size and time: source repository, recommended limit 1 GB; published
   site, at most 1 GB; a deployment times out after 10 minutes; one user
   or organization site per account.
3. On GitHub.com plans: a soft bandwidth limit of 100 GB per month; a soft
   limit of 10 builds per hour, which does not apply when the site is
   built and published with a custom GitHub Actions workflow; rate limits
   answer with HTTP status 429.
4. Over the limits: GitHub may not be able to serve the site, or Support
   may send an email suggesting a CDN in front of the site, other GitHub
   features such as releases, or a different hosting service.
5. Plans: with GitHub Free, Pages is available in public repositories
   only; private repositories need Pro, Team, Enterprise Cloud or
   Enterprise Server. So: not from a private repository on the Free plan.

Trap: the bandwidth and build limits are "soft" and are stated for
GitHub.com plans only (`ifversion fpt or ghec`); calling them hard limits,
or applying them to Enterprise Server, is wrong.