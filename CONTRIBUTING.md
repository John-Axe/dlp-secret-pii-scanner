# Contributing

Thanks for looking at this project. It's small on purpose — read this before opening
a PR, since a few of its conventions are deliberate and a PR that fights them will
just get bounced back for rework.

## Before you write code

For anything bigger than a typo fix or a new detector rule, open an issue first
describing the problem and your proposed approach. This project has a narrow,
considered scope (see [`README.md`](README.md) and [`docs/adr/`](docs/adr/) — the
ADRs are the actual design-decisions record, e.g.
[0001](docs/adr/0001-no-plugin-system-yet.md) on why there's no plugin system and
[0002](docs/adr/0002-zero-runtime-dependencies.md) on why there are zero runtime
dependencies) — an issue first saves you from writing a PR against a change that
doesn't fit that scope.

## Local setup

```bash
git clone https://github.com/John-Axe/dlp-secret-pii-scanner
cd dlp-secret-pii-scanner
pip install -e ".[dev]"
```

No virtualenv is required by the tooling, but using one is normal practice and
recommended.

## Before opening a PR

Run everything CI runs, in this order, and don't open the PR until all six pass:

```bash
ruff check .                                                        # 1. lint
mypy src/                                                           # 2. type-check (library code only, see ci.yml's comment on why)
pytest -v --cov=dlp --cov-report=term-missing                       # 3. unit tests + coverage gate (90% floor)
python benchmark/run_benchmark.py --min-precision 0.85 --min-recall 0.85   # 4. accuracy gate
dlp-scan . --fail-on critical                                       # 5. self-scan
python fuzz/fuzz_scanner.py -runs=10000                             # 6. fuzz smoke test (needs atheris)
```

The coverage gate is a floor (90%), not a target — don't write a test just to nudge
the percentage. A test earns its place by covering a real branch (see `--cov-report
=term-missing`'s "Missing" column for what isn't), not by existing.

If you changed anything under `benchmark/corpus/`, also re-run
`python benchmark/run_benchmark.py --badge-output .github/badges/benchmark.json`
and include the regenerated badge file in your diff — CI does this automatically on
`main`, but a PR branch doesn't get that commit until it merges, so a reviewer should
be able to see the real number in the diff, not a stale one.

## Adding a new detector

This is the most common contribution shape, so it gets its own checklist. A new rule
in [`src/dlp/detectors.py`](src/dlp/detectors.py) needs, in the same PR:

1. The `Detector` entry itself — pick a `rule_id` that's stable forever (it's part of
   the fingerprint hash used by baseline mode and SARIF; renaming it later silently
   invalidates every existing baseline entry for that rule).
2. At least one positive fixture in `benchmark/corpus/positives/` and, if the pattern
   is prone to false positives, a negative fixture in `benchmark/corpus/negatives/`.
3. A matching entry in `benchmark/labels.json` so the new rule is graded, not just
   present.
4. Unit tests in `tests/test_detectors.py` covering at least: a clear true positive,
   a clear true negative (a string that looks close but shouldn't match), and — if
   the rule has a `validator` (see `_luhn_ok`, `_ssn_ok`) — the validator's reject
   path specifically, not just its accept path.
5. A one-line addition to the README's **Detectors** list.

Skipping step 3 is the most common miss — the rule will work, but the benchmark table
will silently not report on it, which defeats the point of shipping accuracy numbers
as a first-class artifact instead of a claim.

## Testing philosophy

Step 4 above says "unit tests" — this is what backs that up. Five real categories
exist in this repo's test suite, each catching a different failure mode; a PR adding
new detection logic should think about which of these actually apply, not just add a
unit test and stop:

- **Hand-picked unit fixtures** (`tests/test_detectors.py`, most of `tests/`) — a
  clear true positive, a clear near-miss true negative, and (per the checklist above)
  a validator's specific reject path. Cheap, readable, and the right default for most
  changes — but only as good as the examples chosen.
- **Property-based tests** (`tests/test_detectors_properties.py`, via
  [Hypothesis](https://hypothesis.readthedocs.io/)) — for the pure validation/scoring
  functions specifically (`_luhn_ok`, `_ssn_ok`, `shannon_entropy`). These exist
  because a validator like `_ssn_ok` encodes a *rule* ("area code `000`/`666`/`9xx` is
  never valid"), not just a handful of examples of that rule — Hypothesis generates
  many inputs and checks the rule holds across all of them, catching an edge case a
  human wouldn't have thought to hand-write. Reach for this when you're adding a
  validator with a real invariant, not for detectors that are pure pattern matching
  with no separate accept/reject logic.
- **Fuzz testing** (`fuzz/fuzz_scanner.py`, [atheris](https://github.com/google/atheris);
  smoke-checked on every `pytest` run via `tests/test_fuzz_smoke.py`, run for real in
  CI's dedicated fuzz job) — feeds arbitrary bytes at every detector to catch crashes
  and hangs, not incorrect-but-non-crashing detection. A different failure mode than
  anything above: a regex that's *wrong* about what it matches is a unit-test problem;
  a regex that catastrophically backtracks on adversarial input is a fuzzing problem.
- **The benchmark as a regression gate** (`benchmark/run_benchmark.py`, CI-gated at
  85% precision/85% recall — see [`docs/Benchmark-Methodology.md`](docs/Benchmark-Methodology.md)
  for exactly how it grades) — catches an *accuracy* regression across the whole
  detector set on every change, not just whether the specific fixture you wrote still
  passes.
- **Performance smoke test** (`tests/test_performance_smoke.py`) — a generous ceiling
  (10-100x normal), not a throughput target; see
  [`docs/Performance.md`](docs/Performance.md). Exists specifically to catch a change
  that makes a regex backtrack catastrophically (ReDoS-shaped), which nothing else in
  this list would notice — a unit test only checks correctness on inputs you thought
  to try, not wall-clock behavior on ones you didn't.

Coverage (the 90% floor in step 3 above) is a byproduct of writing tests that map to
these real categories, not the goal itself — see the "Before opening a PR" section's
note on what earns a test its place.

## Code style

`ruff check` and `mypy src/` (strict mode) are both CI gates — a PR that doesn't
pass either won't merge. There's deliberately no auto-formatter (`ruff format`/
`black`) wired in: adopting one now would reformat the entire tree in an unrelated
diff, which is a separate decision from "does the code pass lint rules," not one
bundled in silently. Beyond what the linter/type-checker catch, match what's
already there:

- Every public function gets a docstring. Prefer explaining a non-obvious *why* over
  restating the signature — see `Finding.fingerprint` or `scan_paths`'s `ignore_root`
  parameter in `scanner.py` for the standard this project holds itself to.
- Type hints on all new code (`from __future__ import annotations` at the top of the
  file, same as every existing module).
- New modules stay single-responsibility, matching the existing shape
  (`detectors` / `scanner` / `report` / `baseline` / `diff` / `ignore` / `cli`).
  `cli.py` should stay a thin orchestration layer — if you're adding logic there
  beyond argument wiring, it probably belongs in a new or existing module instead.

## Suppressing a false positive in this repo's own tree

If the scanner flags something in your own PR diff that isn't real (a docs example,
a test fixture, a coincidentally high-entropy string), don't work around it by
rewording — suppress it explicitly and say why, the same way
[`.dlp-baseline.json`](.dlp-baseline.json) already does for one existing case:

- One-line fix: trailing `# dlp-ignore` comment.
- Broader: a pattern in [`.dlpignore`](.dlpignore).

A silent rewrite to dodge the scanner just hides the false positive from the next
person who hits the same pattern; an explicit suppression documents it.

## Security-relevant changes

Anything touching `github_pr.py`, the CI `permissions:` blocks, or dependency
pinning gets extra scrutiny — see [`SECURITY.md`](SECURITY.md) for how to report an
actual vulnerability privately rather than in a public PR/issue.

## Changelog

Add an entry to [`CHANGELOG.md`](CHANGELOG.md) under `[Unreleased]` in the same PR
as the change — not as a follow-up. Use the existing `Added`/`Changed`/`Fixed`/
`Security` grouping from [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## What a good PR looks like here

One logical change per PR. A new detector, a CLI flag, and a docs fix are three PRs,
not one — this project's own git history (`git log --oneline`) is the reference for
the expected granularity and commit-message style (`feat:`/`fix:`/`chore:`/`refactor:`
prefixes, imperative mood, a body explaining *why* when the change isn't obvious from
the diff alone).
