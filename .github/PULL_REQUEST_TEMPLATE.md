## What this changes and why

<!-- One paragraph. If this fixes an issue, write "Fixes #123". -->

## Checklist

- [ ] `ruff check .` passes
- [ ] `mypy src/` passes
- [ ] `pytest -v --cov=dlp --cov-report=term-missing` passes (90% coverage floor)
- [ ] `python benchmark/run_benchmark.py --min-precision 0.85 --min-recall 0.85` passes
- [ ] `dlp-scan . --fail-on critical` (self-scan) passes
- [ ] If this adds/changes a detector: `benchmark/corpus/` and `benchmark/labels.json`
      updated so the new rule is graded, not just present (see
      [`CONTRIBUTING.md`](../CONTRIBUTING.md#adding-a-new-detector))
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] This PR is one logical change, not several bundled together

## Tradeoffs / things a reviewer should know

<!-- Anything you considered and rejected, anything you're unsure about,
     anything that trades one thing for another. If there's nothing
     non-obvious here, delete this section. -->
