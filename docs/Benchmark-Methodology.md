# Benchmark Methodology

[`README.md`'s Benchmark results](../README.md#benchmark-results) shows
*what* the numbers are (97% precision, 100% recall) and how to reproduce
them. This is *how grading actually works* — the mechanics behind that
table, quoted from `benchmark/run_benchmark.py` itself rather than
restated from memory, so the numbers can be interpreted correctly, not
just cited.

## What precision and recall mean here

Skip this section if you already know the terms. In plain language, for
one detector rule:

- **Precision** answers "when this rule fires, how often is it right?" —
  of everything it flagged, what fraction was actually expected. Low
  precision means a noisy rule that cries wolf.
- **Recall** answers "of everything this rule *should* have caught, how
  much did it actually catch?" Low recall means a rule that misses real
  cases.
- **F1** is the harmonic mean of the two — a single number that penalizes
  a rule for being bad at either one, so a rule can't hide poor recall
  behind great precision (or vice versa) and still get a high F1.

The exact formulas, and what "right"/"expected" mean operationally, are
in the Grading algorithm and Precision/recall/F1 sections below.

## Corpus construction

`benchmark/corpus/` has 35 files: 23 under `positives/`, 12 under
`negatives/`. Every file is a hand-written, synthetic fixture — none
contains a real leaked credential, by deliberate policy (see
`benchmark/corpus/positives/aws_credentials.txt`'s own header comment:
`PLANTED FAKE CREDENTIALS for benchmark testing only`). This keeps the
corpus safe to commit and share, at a real cost named honestly in
[ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md): 35 files is
still nowhere near enough diversity to prove real-world generalization,
only enough to catch a regression in this project's own detectors
against cases it already knows about. See [`docs/FAQ.md`](FAQ.md)'s "How
do I know the precision/recall numbers aren't cherry-picked?" entry for
what the benchmark number does and doesn't prove, and Threats to
validity below for a more rigorous treatment of the same question.

**Fixture categories**, not just a flat file list:

- **Straightforward positives** — one planted artifact, one expected
  rule, e.g. `pii_ssn.txt`, `credit_card.txt`.
- **Multi-rule positives** — `leaked_env_combo.env` (3 rules) and
  `multi_secret_deployment_script.py` (6 rules) plant several different
  secret types in one realistic-looking file, exercising multi-rule
  grading on a single file rather than assuming rules never interact.
- **Format-diversity positives** — every rule with more than one example
  has its second example in a genuinely different file format/context
  than the first (e.g. `aws_secret_key`'s two examples are a shell-style
  export and a Terraform `.tfvars` file; `slack_token`'s two are a bot
  token in a `.env`-style file and a user token in JSON), so a passing
  grade isn't tied to one specific surrounding syntax.
- **Edge-case positives** — `unicode_secret_context.py` (a secret
  surrounded by non-ASCII text) and `crlf_line_endings.txt` (Windows
  line endings), confirming detection isn't accidentally
  ASCII-only or Unix-line-ending-only.
- **Negative fixtures**, three sub-kinds: general "clean codebase"
  simulation (`clean_code.py`, `clean_config.yaml`, etc.), a known hard
  case (`embedded_icon_asset.py` — high-entropy binary data that isn't a
  secret), and **near-miss traps** purpose-built per detector family —
  `invalid_lookalikes.txt` (SSN/credit-card validator-rejection cases),
  `token_prefix_mentions.md` (prose describing token formats without a
  real token), `boundary_length_tokens.txt` (one-character-short/
  wrong-case/wrong-segment-count near-misses), `pkcs8_public_key.pem`
  (a public, not private, key header), `config_with_env_placeholders.json`
  (unexpanded `${VAR}` placeholders in JSON). Negative fixtures exist
  specifically to catch a detector becoming *too* loose, the same way
  positive fixtures catch it becoming too strict.

**Deliberately not done, and why**: exhaustive per-detector boundary/
validator-failure fixtures for every one of the 11 rules. The two rules
with a real validator (`_luhn_ok`, `_ssn_ok`) already get boundary
coverage from Hypothesis property-based tests
(`tests/test_detectors_properties.py`), which check the validator's
invariant across a *generated* distribution of inputs — a strictly
stronger guarantee than a handful of additional hand-picked corpus files
could add. The corpus is for what property tests can't cover: multi-file,
multi-rule, realistic-context interactions. Duplicating property-test
coverage into corpus fixtures would be padding the file count, not adding
signal.

## Labeling

`benchmark/labels.json` maps each corpus file (path relative to
`benchmark/corpus/`) to the list of `rule_id`s expected to fire on it.
Every `negatives/` entry maps to `[]`. A `positives/` file can expect
more than one rule:

```json
"positives/leaked_env_combo.env": ["aws_access_key_id", "email", "generic_password"],
"negatives/clean_code.py": [],
```

Adding a new detector, or a new fixture, without a matching
`labels.json` entry means it runs but is never graded —
`CONTRIBUTING.md`'s "Adding a new detector" checklist calls this out as
the most common miss. Every fixture added to this corpus should be
verified with a direct `dlp-scan <file>` run *before* its label is
written, confirming the actual finding set matches what's being claimed
— not assumed from what the fixture was intended to contain.

## Grading algorithm, exact

`evaluate()` in `run_benchmark.py` grades per **`(file, rule_id)` pair —
not per match**. For each corpus file, `expected` is the set of `rule_id`s
`labels.json` lists for it; `actual` is the set of *distinct* `rule_id`s
that fired anywhere in the file (built from `{f.rule_id for f in
findings}` — a set, so multiple matches of the same rule on the same file
collapse to one membership check):

```python
for rule_id in expected & actual:
    per_rule[rule_id]["tp"] += 1
for rule_id in actual - expected:
    per_rule[rule_id]["fp"] += 1
for rule_id in expected - actual:
    per_rule[rule_id]["fn"] += 1
```

- **True positive**: the rule was expected on this file, and fired at
  least once.
- **False positive**: the rule fired on this file but wasn't expected —
  scored per rule, even if a *different* rule correctly caught the same
  underlying artifact (see the module's own docstring: "this keeps the
  benchmark honest about each detector's individual signal quality").
- **False negative**: the rule was expected but never fired.

**Real interpretive consequence, not just a technicality**: a file with
three separate planted AWS access keys, all three correctly caught by
`aws_access_key_id`, contributes exactly **one** true positive for that
rule — not three. The benchmark measures "did this rule correctly fire on
this file," a per-file signal-quality question, not "how many individual
secrets did this rule find."

## Match-level diagnostics (supplementary, not gating)

`run_benchmark.py`'s table output includes two things beyond the core
TP/FP/FN grading above:

- An **N** column (`tp + fn`) on every row — the sample size behind that
  row's precision/recall. A `1.00` next to `N=2` is a real result from
  two examples; treat it accordingly, not as equivalent in strength to a
  `1.00` backed by a larger sample.
- A separate **"Match-level diagnostics"** section, printed after the
  core table, reporting the raw count of `Finding` objects per rule
  across the whole corpus — a genuinely different number than TP (e.g.
  `high_entropy_string` has TP=4 but a raw match count of 8, because
  several fixtures contain more than one entropy-eligible token). This
  is informational only and does **not** affect `--min-precision`/
  `--min-recall` — the pass/fail contract is exactly the per-`(file,
  rule)` grading above, unchanged.

**Why not full "matches planted vs. matches detected vs. matches missed"
grading**: that would need per-file *exact expected match counts* in
`labels.json` (not just which rules are expected, but how many times
each), a schema change requiring retroactive annotation on every existing
fixture to stay meaningful — real, ongoing maintenance burden for a
metric the file-level TP/FP/FN grading already substantially serves (a
rule that stops matching *entirely* in a multi-instance file already
shows up as a straight FN today; see the "not just a technicality" note
above for what it *doesn't* catch). Match-level diagnostics were added as
an unGraded supplement instead — real signal, zero added annotation
burden, and the existing pass/fail contract stays exactly what it's
always been.

## Precision, recall, F1 — exactly as computed

```python
def precision_recall_f1(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1
```

Standard formulas, with the zero-division edge cases resolved
deliberately, not left to crash or silently produce `NaN`:

- **Precision defined as `1.0`** when a rule has zero TP and zero FP
  (it never fired at all, correctly or not) — vacuously "never wrong,"
  the conventional convention for this edge case.
- **Recall defined as `1.0`** when a rule has zero TP and zero FN (every
  expected occurrence was found — trivially true if none were expected
  either).
- **F1 defined as `0.0`** only in the degenerate case where precision and
  recall are both `0`.

Per-rule rows are computed this way, then a final `OVERALL` row using the
sum of TP/FP/FN across every rule — the number in the README's badge and
top-line claim is this `OVERALL` row, not an average of the per-rule
scores.

## Reproducibility

```bash
python benchmark/run_benchmark.py                                        # table + overall, exit 0 always
python benchmark/run_benchmark.py --min-precision 0.85 --min-recall 0.85 # CI's actual invocation; exits 1 below threshold
```

What's needed to reproduce the exact numbers in this repo:

- **Python**: CI (`.github/workflows/ci.yml`) runs the benchmark job on
  `3.12`; the project supports `3.10+` (`pyproject.toml`
  `requires-python`). The grading logic doesn't depend on version-specific
  behavior, but a reported number should still say what it was measured
  on if precision differs from what's committed here.
- **OS**: CI runs `ubuntu-latest` exclusively — no cross-platform matrix
  exists for this job today.
- **Dependencies**: none at runtime (`dependencies = []`, see
  [ADR 0002](adr/0002-zero-runtime-dependencies.md)) — nothing to pin or
  version-mismatch against.
- **Determinism**: every detector is a regex or a fixed-formula entropy
  calculation (see [ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md)),
  so the same corpus at the same commit produces the same result on any
  machine meeting the above — no seeded randomness, no model version to
  drift.
- **Commit SHA**: a benchmark number is only meaningful paired with the
  commit it was measured at, since the corpus itself changes over time
  (this document's own numbers changed twice in one engineering pass —
  see `CHANGELOG.md`'s `[Unreleased]` entries for the exact history).
  Cite the SHA when reporting a number outside this repo's own docs.

CI additionally passes `--badge-output .github/badges/benchmark.json`,
which writes a [shields.io endpoint-badge](https://shields.io/badges/endpoint-badge)
JSON (`badge_color()`: `brightgreen` at ≥90% precision, `yellow` at
≥75%, `red` below) — the mechanism behind the README's live badge, per
[`Operations.md`](Operations.md#maintenance).
`tests/test_benchmark.py::test_committed_badge_matches_fresh_run` checks
the committed badge against a fresh run on every `pytest` invocation, so
this file and `README.md`'s table shouldn't be able to silently drift
from the actual corpus the way they once did (see `CHANGELOG.md`'s
`[Unreleased]` `Fixed` entry for that incident).

## Threats to validity

Named directly, the way a review would ask for, not hedged into vague
disclaimers:

- **Construct validity**: synthetic fixtures approximate what a real
  leaked secret looks like; they don't replicate the full diversity of
  how real secrets actually appear in real commit history (real
  encodings, real surrounding code idioms, real accidental truncations).
  A benchmark built entirely on fixtures the same people who wrote the
  detectors also wrote is measuring "does this tool catch the cases its
  authors anticipated," which is a real, useful, but narrower claim than
  "does this tool catch secrets in general."
- **Selection bias**: every fixture in this corpus was written by
  whoever was doing the engineering pass at the time, not sourced
  independently or contributed by a third party. Corpus composition
  reflects what was anticipated as a plausible false-positive/negative
  case, not a random or independently-audited sample of real-world
  secret-leak shapes.
- **Small sample sizes per rule**: even after this pass's expansion,
  most rules are graded on 2-4 examples (see the **N** column). A `1.00`
  precision on `N=2` is a real, honestly-reported result — and also not
  strong statistical evidence of a true near-100% rate in the wild. See
  "What precision and recall mean here" above and `docs/FAQ.md` for how
  to read that correctly.
- **No adversarial/red-team corpus**: fixtures test realistic accidental
  leaks, not secrets deliberately obfuscated to evade this specific
  tool's regex patterns. `Limitations.md`'s "No decoding or
  de-obfuscation" entry already names this as a detection-capability
  limit; it's also, separately, a benchmark blind spot — a deliberately
  evasive secret wouldn't show up as a missed detection here, because
  none of the fixtures attempt evasion.

None of these are reasons to distrust the numbers as *reported* — they're
reasons not to extrapolate beyond what a synthetic, author-written,
mid-double-digit-sample corpus can actually prove. Both things are true
at once, which is the point of writing this section down explicitly.

## What this benchmark does not measure

- **Real-world generalization** — see Threats to validity above and
  [ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md)'s Alternatives
  section for the tradeoff this accepts.
- **Match-level recall within a file, in the pass/fail gate** — the
  Match-level diagnostics section above reports raw match counts as a
  supplement, but a rule that catches 1 of 3 planted instances in one
  file still scores identically (one TP) to catching all 3 in the
  *graded* result, as long as it fires at least once.
- **Runtime performance or memory** — a separate concern, covered by
  `benchmark/run_throughput_benchmark.py` and
  [`Performance.md`](Performance.md), not this file.
