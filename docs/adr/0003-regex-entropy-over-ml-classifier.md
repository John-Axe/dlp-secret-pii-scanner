# 0003 — Regex + Shannon entropy, not an ML/statistical classifier

## Status

Accepted (2026-07-30, retroactive — the decision itself dates to project
inception)

## Context

`src/dlp/detectors.py` implements every detection rule as either a
compiled regex with an optional validator function (Luhn checksum for
credit cards, area/group/serial range checks for SSNs — see `_luhn_ok`,
`_ssn_ok`) or, for the one non-regex rule, a Shannon-entropy threshold over
20+ character tokens (`shannon_entropy`, `scan_line_entropy`). `git log
--follow -- src/dlp/detectors.py` shows all 11 detectors were added in the
project's first commit and every later change has been a fix or
refactor — this is the detection approach the project has always used, not
one it arrived at after trying something else. The project's central claim
(README: "94% precision and 100% recall on a labeled benchmark corpus...
backed by a benchmark you can re-run yourself") makes the detection
mechanism's properties — determinism, interpretability, and how its
accuracy is validated — load-bearing enough to write down explicitly.

## Problem

Should secret/PII detection be done (in whole or in part) by a trained
ML/statistical classifier — the way some scanners approach the "does this
look like a secret" question as supervised classification over token or
context features — instead of, or alongside, hardcoded regex patterns and
a fixed entropy threshold?

## Alternatives considered

**A. A trained classifier**, either replacing the whole detection pipeline
or narrowly replacing just the entropy detector (the one component
already doing fuzzy, non-format-specific matching, and the one responsible
for this project's only benchmark false positive —
`negatives/embedded_icon_asset.py`, a base64 binary asset that reads as
high-entropy the same way a real secret does).

- Runtime dependency conflict: any classifier worth training needs at
  minimum a numeric/ML runtime to load and run it (`numpy` at the low end,
  a model-serving library at the high end). That's a direct conflict with
  [ADR 0002](0002-zero-runtime-dependencies.md)'s zero-runtime-dependency
  decision — not a minor tension, but the same "nothing to compromise in
  the dependency tree" argument working directly against this option.
- Determinism: `Finding.fingerprint` (see
  [ADR 0004](0004-finding-fingerprint-design.md)) and the baseline/SARIF
  machinery it supports assume the same input always produces the same
  finding. A regex match or an entropy calculation over fixed input is
  exactly reproducible, on any machine, forever. A classifier's output can
  depend on model version, floating-point behavior across platforms and
  hardware, and drift if it's ever retrained — a materially harder
  determinism guarantee to keep, and a new source of "why did this
  baseline stop matching" bug reports.
- Explainability: every finding carries a `rule_id`, exact `line`/`column`
  match boundaries, and a `redacted` preview — used directly in PR review
  comments and the SARIF `rules` array (`report.py`, `github_pr.py`). A
  regex match gives exact span boundaries for free. A classifier making a
  judgment over a window of text doesn't, unless it's a sequence-labeling
  model — real additional complexity, not a drop-in swap for the current
  `Detector.scan_line` contract.
- Training data: `benchmark/corpus/` currently has 12 positive and 8
  negative files, written as synthetic fixtures specifically so the corpus
  never contains a real leaked credential. That's enough to grade a
  regex/threshold-based detector's precision/recall meaningfully, but not
  remotely enough to train a classifier that would generalize — and
  growing it to classifier-training scale would mean either sourcing real
  secret-shaped data (a real privacy/security problem in its own right, to
  curate and store) or accepting a synthetic-only training set's
  generalization risk on top of everything else.
- Auditability: a regex change is a small, readable PR diff — a reviewer
  can see exactly what pattern changed and why, and `CONTRIBUTING.md`'s
  "Adding a new detector" checklist ties every rule change to a benchmark
  fixture. A model's learned weights are not reviewable the same way; the
  project's whole value proposition (accuracy as a "CI-enforced artifact,"
  not "a marketing number," per the README) depends on every detector's
  behavior being something a human can read and reason about, not a black
  box whose behavior is only knowable by re-running the benchmark.

**B. Regex + Shannon entropy (status quo).** Format-specific rules for
patterns that have one (AWS/GitHub/GitLab/Slack tokens, JWTs, private key
blocks, SSNs, credit cards, emails), each independently validated where a
cheap structural check exists (Luhn, SSN range rules) to cut down false
positives without adding a dependency. Shannon entropy as a fallback for
the "no known format" case, at a fixed, user-configurable threshold
(`DEFAULT_ENTROPY_THRESHOLD = 4.3`).

## Decision

**Stay with (B).** Concretely:

- `REGEX_DETECTORS` stays a list of `(pattern, validator)` pairs; no
  detector's decision function is a trained model.
- The entropy detector — the component a classifier would most plausibly
  improve on, since it's the source of this project's only known
  benchmark false-positive class — stays a fixed Shannon-entropy threshold
  over character distribution, not a learned model.
- The benchmark (`benchmark/run_benchmark.py`, CI-gated at 85%
  precision/recall) remains the accuracy validation mechanism for both
  today's rules and any future ones, regex or otherwise.

This isn't a rejection of classifiers as a category — it's that every cost
listed under (A) is a cost this specific project, at its current scale (11
detectors, a 20-file benchmark corpus, zero runtime dependencies by
design), would pay for a benefit (better handling of the entropy
detector's one known false-positive class) that a cheaper fix — a bigger
corpus-tuned threshold, a smarter token filter, or simply
`# dlp-ignore`/`.dlpignore` at the call site — already addresses today.

## Consequences

- Every detector's behavior is fully determined by reading
  `detectors.py` — no separate model artifact to version, ship, or verify
  reproducibility of.
- The entropy detector keeps its known false-positive class (base64
  binary assets), documented in `docs/Limitations.md` and worked around
  per-instance with `.dlpignore`/`# dlp-ignore` rather than solved
  structurally.
- Detecting a genuinely novel secret format still means writing a new
  regex, not something a classifier could pick up from context without a
  dedicated rule — a real coverage gap for formats that don't have one
  (see `docs/Limitations.md`'s "Eleven detectors total" entry), unchanged
  by this decision either way.
- This is revisitable on the same evidence-based terms as ADR 0001 and
  ADR 0002: if the entropy detector's false-positive rate became a
  recurring real complaint at a scale `.dlpignore` doesn't comfortably
  absorb, or if the benchmark corpus grew enough (by an order of
  magnitude or more) to make training a classifier's generalization risk
  tractable, a narrowly-scoped classifier replacing just the entropy
  detector — not the whole pipeline — would be the more defensible
  starting point of the two, since it wouldn't touch any format-specific
  rule's determinism or explainability guarantees.

## Tradeoffs

|  | Chosen (B, regex + entropy) | A (ML/statistical classifier) |
|---|---|---|
| Runtime dependencies | None (fits [ADR 0002](0002-zero-runtime-dependencies.md)) | At least a numeric/model runtime |
| Determinism | Exact, same input → same output always | Model/platform/version dependent |
| Finding match boundaries | Exact span, free | Requires sequence labeling to match |
| Auditability of a rule change | Small, readable PR diff | Opaque learned weights |
| Training/tuning data needed | None beyond the existing 20-file corpus | A much larger labeled corpus |
| Handles the entropy FP class (binary blobs) | No — documented limitation, workaround via `.dlpignore` | Potentially, unproven at this project's scale |
| Novel/unknown secret format coverage | Needs a new regex rule | Possibly better recall, unverified without real data |
