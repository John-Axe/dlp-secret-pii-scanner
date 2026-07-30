# Benchmark Methodology

[`README.md`'s Benchmark results](../README.md#benchmark-results) shows
*what* the numbers are (94% precision, 100% recall) and how to reproduce
them. This is *how grading actually works* — the mechanics behind that
table, quoted from `benchmark/run_benchmark.py` itself rather than
restated from memory, so the numbers can be interpreted correctly, not
just cited.

## Corpus construction

`benchmark/corpus/` has 20 files: 12 under `positives/`, 8 under
`negatives/`. Every file is a hand-written, synthetic fixture — none
contains a real leaked credential, by deliberate policy (see
`benchmark/corpus/positives/aws_credentials.txt`'s own header comment:
`PLANTED FAKE CREDENTIALS for benchmark testing only`). This keeps the
corpus safe to commit and share, at a real cost named honestly in
[ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md): 20 files is
nowhere near enough diversity to prove real-world generalization, only
enough to catch a regression in this project's own detectors against
cases it already knows about. See [`docs/FAQ.md`](FAQ.md)'s "How do I know the 94% precision / 100%
recall numbers aren't cherry-picked?" entry for what the benchmark number
does and doesn't prove.

`positives/` files each contain one or more deliberately planted findings
a specific set of rules should catch. `negatives/` files contain none —
clean code, config, docs, and (deliberately) two harder cases: a base64
binary asset that's high-entropy without being a secret
(`embedded_icon_asset.py`) and near-miss lookalikes that should *not*
trigger a detector (`invalid_lookalikes.txt`) — negative fixtures exist
specifically to catch a detector becoming *too* loose, the same way
positive fixtures catch it becoming too strict.

## Labeling

`benchmark/labels.json` maps each corpus file (path relative to
`benchmark/corpus/`) to the list of `rule_id`s expected to fire on it.
Every `negatives/` entry maps to `[]`. A `positives/` file can expect
more than one rule — `leaked_env_combo.env` expects three
(`aws_access_key_id`, `email`, `generic_password`) because it plants all
three in one file, deliberately, to exercise multi-rule-per-file grading
in the same corpus that mostly tests one rule per file:

```json
"positives/leaked_env_combo.env": ["aws_access_key_id", "email", "generic_password"],
"negatives/clean_code.py": [],
```

Adding a new detector without a matching `labels.json` entry means the
rule runs but is never graded — `CONTRIBUTING.md`'s "Adding a new
detector" checklist calls this out as the most common miss.

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
secrets did this rule find." A tool wanting a match-level count (how many
individual findings, not how many correctly-graded files) should look at
`--format json`'s raw finding list instead — that's a different question
than what this benchmark answers.

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

## Reproducing it

```bash
python benchmark/run_benchmark.py                                    # table + overall, exit 0 always
python benchmark/run_benchmark.py --min-precision 0.85 --min-recall 0.85  # CI's actual invocation; exits 1 below threshold
```

CI additionally passes `--badge-output .github/badges/benchmark.json`,
which writes a [shields.io endpoint-badge](https://shields.io/badges/endpoint-badge)
JSON (`badge_color()`: `brightgreen` at ≥90% precision, `yellow` at
≥75%, `red` below) — the mechanism behind the README's live badge, per
[`Operations.md`](Operations.md#maintenance).

## What this benchmark does not measure

- **Real-world generalization** — a 20-file synthetic corpus can't prove
  this; see the Corpus construction section above and
  [ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md)'s Alternatives
  section for the tradeoff this accepts.
- **Match-level recall within a file** — per the grading algorithm above,
  a rule that catches 1 of 3 planted instances of itself in one file
  scores identically (one TP) to a rule that catches all 3, as long as it
  fires at least once. A regression that made a rule miss 2 of 3
  instances in a multi-instance file would not, by itself, move this
  benchmark's numbers.
- **Runtime performance** — a separate concern, covered by
  `benchmark/run_throughput_benchmark.py` and
  [`Performance.md`](Performance.md), not this file.
