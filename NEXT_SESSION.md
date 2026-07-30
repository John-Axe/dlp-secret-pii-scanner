# Handoff — engineering transformation, in progress

**Last updated:** 2026-07-30, mid-Phase 3.
**Read this file first** if you're picking this work up cold — it should let
you continue without re-deriving anything below.

## What this is

`dlp-secret-pii-scanner` is going through a structured engineering-quality
pass: audit → 5-phase roadmap → incremental, individually-verified PRs, each
with its own Goal/Reasoning/Tradeoffs writeup in its commit message. Nothing
has been pushed to `origin` or merged — everything lives on three stacked
local branches, one commit per coherent change, matching how this repo
already holds PR merges for an explicit human go-ahead.

## Completed work

### Phase 1 — Quick wins (branch `engineering-audit/phase-1-quick-wins`, 5 commits)
1. `6552c88` — `CONTRIBUTING.md`
2. `9a58a85` — `CHANGELOG.md`, backfilled from git history
3. `7c6d026` — 3 tailored issue forms, PR template, `CODEOWNERS`
4. `3435130` — `--version`, `python -m dlp`, worked `--help` examples
5. `7d73713` — CHANGELOG catch-up for #3/#4

### Phase 2 — Engineering improvements (branch `engineering-audit/phase-2-engineering-improvements`, stacked on Phase 1, 6 commits)
1. `9ec4343` — `ruff check` + `mypy src/` (strict) + 90% coverage floor, all as CI gates. `py.typed` added (PEP 561).
2. `d6d9a3c` — Fixed two silent-failure paths (`scan_file`'s `except OSError` and >5MB skip both returned `[]`). Added `ScanStats`.
3. `c9cd3c4` — `dlp.github_pr.post_review_comments` capped at 25 comments, rate-limit-aware with backoff.
4. `f6d685c` — Hypothesis property tests for Luhn/SSN/entropy. Found and fixed a real self-inflicted bug: `.hypothesis` cache dir wasn't skipped.
5. `14b62fd` — `pyproject.toml [tool.dlp]` per-project config support (stdlib `tomllib`, zero new runtime dep).
6. `c720e48` — this file, first version.

### Phase 3 — Architecture improvements (branch `engineering-audit/phase-3-architecture-improvements`, stacked on Phase 2, 2 commits so far)
1. `c3626f9` — `docs/adr/0001-no-plugin-system-yet.md`. Grounded in real data (`git log --follow -- src/dlp/detectors.py`: all 11 detectors landed in the initial commit, zero new rules since — not the "once a quarter" guess this file previously stated).
2. `99131bd` — `benchmark/run_throughput_benchmark.py` (not CI-gated — machine-dependent) + `tests/test_performance_smoke.py` (CI-gated, generous 10s ceiling, targets catastrophic ReDoS-style regressions specifically). **Baseline established this session, this machine: ~1050 files/sec, ~5.7 MB/sec, 2000 synthetic files / 11MB in 1.9s.** Also caught and fixed a real bug in the benchmark script itself (planted-secret interval was mathematically unreachable at the default file size — see commit message).

**Net so far:** 130 → 202 tests, coverage 96.45% → 97.98%, four real bugs
fixed (three operational-trust bugs in Phase 2, one benchmark-script bug in
Phase 3), zero regressions. Every commit individually verified against the
full local gate sequence (ruff, mypy, pytest+coverage, benchmark, self-scan,
10k-iteration fuzz) before landing.

## Current architecture (for orientation, not re-derivation)

```
src/dlp/
  cli.py            argparse entry point, thin orchestration only
  config.py         pyproject.toml [tool.dlp] loading/validation
  scanner.py        file walk + Finding dataclass + ScanStats
  detectors.py       11 regex detectors + Shannon-entropy detector
  report.py          table/json/sarif rendering
  baseline.py         fingerprint-based suppression
  diff.py             git diff --name-only wrapper for --diff-only
  ignore.py            .dlpignore + inline # dlp-ignore
  github_pr.py        inline PR comments, rate-limit-aware
  shared_finding.py    maps onto the ecosystem-wide finding schema
scripts/coverage_badge.py
benchmark/
  run_benchmark.py            accuracy (precision/recall), CI-gated
  run_throughput_benchmark.py  speed (files/sec, MB/sec), NOT CI-gated
docs/adr/0001-no-plugin-system-yet.md
```

Zero runtime dependencies is a load-bearing, deliberate constraint across the
whole codebase — respect it. `tomllib` and everything test-only (`hypothesis`,
`pytest-cov`, `ruff`, `mypy`) are dev-only, not runtime.

## Known issues / gaps still open

- **Pre-existing, low-priority, not tied to a real bug:** `scanner.py:89,120`,
  `github_pr.py:231-232`. Skip unless doing a dedicated coverage pass.
- CI itself has not been run (nothing pushed) — everything is verified
  *locally* against the exact commands CI runs. Watch the first real push
  closely for anything environment-specific that differs from this sandbox.
- This repo's own `pyproject.toml` deliberately has no `[tool.dlp]` section
  (see commit `14b62fd`'s message for why).

## Recommended next task: Phase 3, item 2 — `--jobs` parallel scanning

**This is the one that needs real attention, not a quick continuation.**
Unlike everything shipped so far in Phases 2-3 (additive: new modules, new
tests, new CLI flags that default to old behavior), this touches
`scan_paths`' actual hot path.

**Before writing code, measure first, don't assume:** the original audit
guessed threads would help (I/O-bound file reads) but flagged the GIL as a
limit on the regex/CPU side. Now that `run_throughput_benchmark.py` exists,
actually build a `ThreadPoolExecutor` version and a `ProcessPoolExecutor`
version and benchmark both against the same synthetic corpus before
committing to one — don't guess when a 5-minute measurement answers it.

**The one correctness property that must not break:** findings currently
come back in a stable, deterministic order (files walked via `sorted(root.
rglob("*"))`, one file at a time). A naive `executor.map()` over that same
file list preserves order (concurrent.futures' `map` yields results in
submission order, not completion order — verify this is actually being
relied on correctly, don't assume). A parallel `--jobs` mode must produce
byte-identical output to the sequential path for the same input, or:
- `run_benchmark.py`'s `(file, rule_id)` pairing breaks
- Any test asserting finding order breaks
- `--write-baseline`'s fingerprint set is unaffected (it's a set, order-
  independent) but worth confirming explicitly rather than assuming

**Suggested test to write first, before the implementation:** scan the same
directory tree sequentially and with `--jobs N` for several values of N,
assert the findings lists are identical (not just same-length — actually
equal, in order). This is the test that proves the feature is safe to ship;
write it before or alongside the implementation, not after.

**Design sketch, not gospel — reconsider after measuring:**
- `scan_paths(..., jobs: int = 1)` — default 1 (today's exact sequential
  behavior, zero risk to existing callers/tests).
- CLI: `--jobs N` (or `--jobs auto` → `os.cpu_count()`).
- Whichever executor wins the benchmark, wrap file-level `scan_file` calls
  in it; keep the file *list* built exactly as today (same walk, same
  order), only parallelize the per-file scan work, then reassemble results
  in original file-list order regardless of completion order.

**Estimated effort:** 3-4 hours including the measure-first step and the
order-preservation test. **Risk: medium** — real behavior change, but fully
contained by defaulting to `jobs=1` (unchanged behavior unless a user opts
in) and the order-equality test.

## Suggested implementation order after that

Phase 3 remainder:
3. Structured `logging` adoption + `--verbose`/`--quiet` (~2hrs) — natural
   follow-on to the `ScanStats`/stderr work already done in Phase 2.

Phase 4 (docs: `Architecture.md`, `Threat-Model.md`, `Operations.md`,
`Troubleshooting.md`, `Performance.md`, `Limitations.md`) and Phase 5
(`Design-Decisions.md`, `FAQ.md`, `Roadmap.md`, `Development-Log.md`,
`Case-Study.md`, retroactive ADRs for zero-deps and regex-vs-ML) are still
fully open — see the original audit's roadmap for full effort/ROI estimates
per item (not yet its own committed file — worth promoting out of chat
history into `docs/Roadmap.md` when Phase 4 starts).

## Open questions for the human

- Push Phases 1-3 now for real CI validation, or keep accumulating locally?
  Recommend pushing once `--jobs` lands, since that's the first change in
  this whole pass with real behavioral risk.
- Is `[tool.dlp]` config support something you actually want dog-fooded in
  this repo's own `pyproject.toml`, or is "built and tested, not
  self-adopted" the right call long-term?

## Potential risks if continuing unattended

- `--jobs` is the one item flagged above needing real scrutiny — don't rush
  it into a commit without the order-preservation test passing.
- Everything else remaining (structured logging, all of Phase 4/5 docs) is
  additive/documentation-only — lower supervision needed than `--jobs`.
