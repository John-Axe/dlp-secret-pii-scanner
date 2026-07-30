# FAQ

Questions a reader is likely to actually ask that don't fit
[`Troubleshooting.md`](Troubleshooting.md)'s symptom-to-fix format — this
is about *why* the tool is shaped the way it is, not what to do when
something breaks. Where a full design record already exists, this points
to it rather than restating it; where the honest answer is genuinely new
synthesis not written down elsewhere, it's here in full.

## Why not just use an existing tool like gitleaks or detect-secrets?

This repo already runs [gitleaks](../.github/workflows/gitleaks.yml)
alongside `dlp-scan` in its own CI — the two aren't positioned as
either/or. The real differences:

- **Scope.** gitleaks and `git-secrets` scan git *history* — every commit
  ever made, including ones since amended or reverted. `dlp-scan` only
  ever looks at the current working tree (or, with `--diff-only`, the
  current diff). That's a deliberate scope boundary, not an oversight —
  see [`Limitations.md`](Limitations.md#what-this-tool-deliberately-does-not-do)
  — and it's exactly why running both makes sense: history scanning and
  working-tree scanning catch different things.
- **Secrets *and* PII, in one pipeline.** gitleaks and `detect-secrets`
  are secrets-focused; SSNs, emails, and credit card numbers aren't
  their job. `dlp-scan` treats both as the same underlying
  problem — see the next question.
- **The accuracy claim is the product, not a side note.** Every rule in
  `benchmark/corpus/` is graded per-rule and the number is CI-enforced on
  every push, not a one-time claim in a README. Whether that's actually
  more trustworthy than a tool that doesn't publish this is for the next
  question.

None of this makes `dlp-scan` a strict replacement for either tool — the
gitleaks workflow in this repo's own CI is the honest answer to "which one
should I use": both, for what each one actually covers.

## Why does this tool detect secrets and PII together, not as two separate tools?

Because they're the same underlying mechanism pointed at different regex
patterns, not two different mechanisms. Every detector — whether it flags
an AWS key or a Social Security number — is the same `Detector` dataclass
(`detectors.py`): a compiled pattern plus an optional validator function
(`_luhn_ok` for credit cards, `_ssn_ok` for SSNs; AWS/GitHub/Slack tokens
use the same shape without a validator). They share one `Finding` schema,
one severity/`--fail-on` gate, one benchmark harness, one config surface.
The only place "secret" vs. "PII" exists as a distinction at all is a
five-line lookup table in `shared_finding.py`
(`_PII_RULE_IDS = {"email", "us_ssn", "credit_card"}`) used solely to
categorize findings when exporting to the shared ecosystem finding schema —
nothing about how a rule is written, matched, validated, benchmarked, or
gated cares whether it's PII or a credential. Splitting this into two
tools would mean maintaining two copies of the CLI, config loading, CI
integration, and benchmark infrastructure around one mechanism that
doesn't actually branch on the distinction anywhere it matters.

## How do I know the precision/recall numbers aren't cherry-picked?

Reasonable skepticism — a self-reported accuracy number is easy to
exaggerate. Three things make this one checkable rather than a bare claim
— including one place this project's own claim was too strong and has
since been corrected, which is itself part of the answer:

- **It's re-run in CI on every push to `main`**, and the shields.io badge
  at the top of the README is written by that same CI job
  (`update-badge`), not hand-typed — see
  [`Operations.md`](Operations.md#maintenance). An earlier version of
  this FAQ entry claimed "nothing in the pipeline allows" the badge and
  the actual benchmark output to drift apart — that turned out to be
  overstated: the badge only regenerates on a `main`-branch push, so a
  string of local commits that changed the corpus (real ones, in this
  repo's own history) left `README.md`'s table and
  `.github/badges/benchmark.json` stale until it was caught by a manual
  audit and fixed. The actual current safeguard is narrower and more
  honest: `tests/test_benchmark.py::test_committed_badge_matches_fresh_run`
  regenerates a badge from the live corpus and diffs it against the
  committed one on every `pytest` run, so a mismatch fails the same gate
  every other change already has to pass — not a claim that drift is
  structurally impossible, a claim that it's now actively checked for.
- **You can re-run it yourself**: `python benchmark/run_benchmark.py`
  against `benchmark/corpus/` and `benchmark/labels.json`, both committed
  in this repo, not held back.
- **The honest limit, named rather than hidden**: the corpus is small —
  see [`Benchmark-Methodology.md`](Benchmark-Methodology.md) for the
  current file count and category breakdown — and synthetic, written
  specifically so it never contains a real leaked credential (see
  [ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md)'s Alternatives
  section, and `Benchmark-Methodology.md`'s "Threats to validity" section
  for the fuller treatment). A precise-looking number from a corpus this
  size isn't a claim about how this tool performs on the full diversity
  of secrets that exist in the wild — it's a regression gate (CI fails
  below 85% precision/recall) that catches an accuracy regression a code
  change introduces, not a proof of generalization. Both things can be
  true at once: the number is real and un-gamed, *and* it's measuring a
  smaller, curated slice of the problem than a bare percentage would
  suggest if taken out of context — which is exactly why this project
  reports sample size (the **N** column) alongside every percentage now,
  not just the percentage alone.

## Why zero runtime dependencies?

Short version: nothing to compromise in the dependency tree of a tool
that runs in pre-commit hooks and CI jobs with write-scoped GitHub tokens,
because there's no dependency tree — `urllib` instead of `requests`,
`argparse` instead of `click`, stdlib `tomllib` instead of a TOML
library. Full reasoning, including the one real cost this pays (no
`[tool.dlp]` config support on Python 3.10), is in
[ADR 0002](adr/0002-zero-runtime-dependencies.md).

## Why regex and entropy instead of an AI/ML model?

Short version: determinism (a baseline or SARIF fingerprint has to mean
the same thing on every re-scan), a direct conflict with the
zero-runtime-dependency decision above, and a benchmark corpus (see
[`Benchmark-Methodology.md`](Benchmark-Methodology.md) for the current
size) nowhere near large enough to train something that would
generalize. Full
reasoning, including the specific alternative of a classifier scoped
narrowly to the entropy detector's one known false-positive class, is in
[ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md).
