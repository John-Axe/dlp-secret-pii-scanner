# Contributing

Thanks for looking at this project. It's small on purpose — read this before opening
a PR, since a few of its conventions are deliberate and a PR that fights them will
just get bounced back for rework.

## Before you write code

For anything bigger than a typo fix or a new detector rule, open an issue first
describing the problem and your proposed approach. This project has a narrow,
considered scope (see [`README.md`](README.md) and, once it exists,
[`docs/Design-Decisions.md`](docs/Design-Decisions.md)) — an issue first saves you
from writing a PR against a change that doesn't fit that scope.

## Local setup

```bash
git clone https://github.com/John-Axe/dlp-secret-pii-scanner
cd dlp-secret-pii-scanner
pip install -e ".[dev]"
```

No virtualenv is required by the tooling, but using one is normal practice and
recommended.

## Before opening a PR

Run everything CI runs, in this order, and don't open the PR until all four pass:

```bash
pytest -v                                                          # 1. unit tests
python benchmark/run_benchmark.py --min-precision 0.85 --min-recall 0.85   # 2. accuracy gate
dlp-scan . --fail-on critical                                       # 3. self-scan
python fuzz/fuzz_scanner.py -runs=10000                             # 4. fuzz smoke test (needs atheris)
```

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

## Code style

There's no `ruff`/`black`/`mypy` gate wired into CI yet (tracked as a known gap —
see the maturity audit if one is present in `docs/`). Until there is, match what's
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

## What a good PR looks like here

One logical change per PR. A new detector, a CLI flag, and a docs fix are three PRs,
not one — this project's own git history (`git log --oneline`) is the reference for
the expected granularity and commit-message style (`feat:`/`fix:`/`chore:`/`refactor:`
prefixes, imperative mood, a body explaining *why* when the change isn't obvious from
the diff alone).
