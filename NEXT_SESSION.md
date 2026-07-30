# Handoff — engineering transformation, in progress

**Last updated:** 2026-07-30, Phase 3 complete, Phase 4 not yet started.
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
`CONTRIBUTING.md`, `CHANGELOG.md`, issue/PR templates + `CODEOWNERS`,
`--version`/`python -m dlp`/`--help` examples.

### Phase 2 — Engineering improvements (branch `engineering-audit/phase-2-engineering-improvements`, stacked on Phase 1, 6 commits)
CI gates (ruff/mypy strict/90% coverage + `py.typed`), fixed two silent-skip
bugs (`ScanStats`), bounded + rate-limit-hardened `github_pr.py`, Hypothesis
property tests (+ fixed a self-inflicted `.hypothesis`-cache-dir bug),
`pyproject.toml [tool.dlp]` config support.

### Phase 3 — Architecture improvements (branch `engineering-audit/phase-3-architecture-improvements`, stacked on Phase 2, 6 commits) — **COMPLETE**
1. `c3626f9` — `docs/adr/0001-no-plugin-system-yet.md`, grounded in real git
   history data.
2. `99131bd` — `benchmark/run_throughput_benchmark.py` (not CI-gated) +
   `tests/test_performance_smoke.py` (CI-gated, catches catastrophic ReDoS-
   style regressions). Baseline: ~1050 files/sec sequential on this machine.
3. `c66049b` — `--jobs N` parallel scanning. **Measured before implementing**:
   a throwaway benchmark showed threading was *slower* than sequential
   (0.75-0.86x, GIL contention) while multiprocessing gave a real 1.4-3.6x
   speedup — this determined the implementation, overturning the original
   audit's tentative "threads" guess. Confirmed end-to-end through the real
   CLI: 2.985s → 1.171s (~2.5x) on a 3000-file corpus, byte-identical output.
   Caught a real Python 3.14 `forkserver`-start-method gotcha while writing
   the tests (monkeypatched globals don't propagate to worker processes) —
   fixed by testing with real file conditions instead.
4. `5f0a47e` — `-v`/`--verbose` and `-q`/`--quiet` logging. Named `dlp`
   logger, never the root logger, handlers only configured in `main()` (the
   CLI entry point) — `dlp`'s modules stay safely importable as a library.

**Net so far:** 130 → 215 tests, coverage 96.45% → 97.46%, five real bugs
found and fixed along the way (three Phase-2 operational-trust bugs, one
Phase-3 benchmark-script bug, one Phase-3 test-design bug from the
forkserver gotcha), zero regressions. Every commit individually verified
against the full local gate sequence (ruff, mypy, pytest+coverage,
benchmark, self-scan, 10k-iteration fuzz) before landing — several commits
also verified with real end-to-end CLI runs beyond the test suite (the
`--jobs` speedup measurement, manual `-v`/`-vv`/`-q` output checks).

## Current architecture (for orientation, not re-derivation)

```
src/dlp/
  cli.py            argparse entry point + logging config (LOGGER = "dlp")
  config.py         pyproject.toml [tool.dlp] loading/validation
  scanner.py        file walk + Finding + ScanStats + parallel scan (jobs=N)
  detectors.py       11 regex detectors + Shannon-entropy detector
  report.py          table/json/sarif rendering
  baseline.py         fingerprint-based suppression
  diff.py             git diff --name-only wrapper for --diff-only
  ignore.py            .dlpignore + inline # dlp-ignore
  github_pr.py        inline PR comments, rate-limit-aware, still uses print()
  shared_finding.py    maps onto the ecosystem-wide finding schema
scripts/coverage_badge.py
benchmark/
  run_benchmark.py            accuracy (precision/recall), CI-gated
  run_throughput_benchmark.py  speed (files/sec, MB/sec), NOT CI-gated
docs/adr/0001-no-plugin-system-yet.md
```

Zero runtime dependencies is a load-bearing, deliberate constraint — respect
it. `tomllib` and everything test-only (`hypothesis`, `pytest-cov`, `ruff`,
`mypy`) are dev-only, not runtime.

## Known issues / gaps still open

- **Pre-existing, low-priority, not tied to a real bug:** `scanner.py:90,121`
  (`ignore_root`-fallback path, empty-file early return), `scanner.py:192-201`
  (`_scan_file_worker`'s body — only executes in a worker process, coverage.py
  can't instrument it; functionally proven by the parallel-vs-sequential
  equality tests instead), `github_pr.py:231-232`, `cli.py:306`
  (`--emit-findings`'s write call). None security- or correctness-relevant.
- `github_pr.py` still uses `print()` for its own operational messages
  (not converted to the new `LOGGER` — deliberately out of scope for the
  logging commit, noted as a reasonable follow-up, not urgent).
- CI itself has not been run (nothing pushed) — everything verified
  *locally*. Watch the first real push closely, especially the `--jobs`
  ProcessPoolExecutor path — CI runners may have fewer/different CPU
  characteristics or a different default multiprocessing start method than
  this sandbox's Python 3.14 (`forkserver`).
- This repo's own `pyproject.toml` deliberately has no `[tool.dlp]` section
  (see commit `14b62fd`'s message for why).

## Recommended next task: Phase 4 — production-readiness docs

Phase 3 is done. Phase 4 is pure documentation (no code risk), covering:
`docs/Architecture.md`, `docs/Threat-Model.md`, `docs/Operations.md`,
`docs/Troubleshooting.md`, `docs/Performance.md`, `docs/Limitations.md`.

**Suggested order and why:**

1. **`docs/Limitations.md` first** — the highest-leverage one to write, and
   the most already-known: this session's work has already surfaced several
   honest limitations worth collecting in one place rather than scattered
   across commit messages and ADR 0001: no way to add an org-private secret
   format without forking (ADR 0001), `--jobs` startup cost not worth it for
   small scans, the entropy detector's known false-positive class (binary/
   compressed data), detectors can't catch a secret split across multiple
   files or encoded beyond simple entropy detection. Fast to write since the
   content already exists, just not consolidated.
2. **`docs/Threat-Model.md`** — trust boundaries are already mostly *lived*
   in this codebase (redaction, GITHUB_TOKEN scoping, SHA-pinned Actions)
   but never written down as a single document. Should state explicitly:
   what's trusted input (the source tree being scanned), what's an
   untrusted output sink (PR comment bodies — already backtick-escaped
   against Markdown injection, worth citing as evidence of real threat
   modeling, not just claiming it), and what's out of scope (network
   attacks, supply-chain compromise of a dependency — though there are
   none at runtime).
3. **`docs/Architecture.md`** — largely already written, in the README's
   embedded Mermaid diagram and its surrounding prose. This is mostly
   *extraction and expansion*, not new content: pull it out, add a
   component diagram (the 10 `src/dlp/` modules and their actual import
   relationships — genuinely simple, verify with a quick import-graph check
   rather than assuming) and a sequence diagram for one real flow (a
   `pull_request` CI run: checkout → diff-only scan → baseline filter →
   SARIF upload + inline comments).
4. **`docs/Operations.md`** — how to actually run this in production: the
   pre-commit hook, the GitHub Action, the `pr-scan.yml`/`ci.yml` workflows,
   what `--jobs` is worth turning on for, upgrade path (bump the pinned
   `rev:`/tag).
5. **`docs/Performance.md`** — mostly already exists in README's new
   "Parallel scanning" section + the throughput benchmark's own docstring;
   promote/expand into its own doc with the actual measured numbers from
   this session (baseline ~1050 files/sec sequential, ~2.5x at `--jobs 0`
   on a 24-core machine) framed honestly as *this machine's* numbers, not a
   portable claim.

**Estimated effort:** 4-6 hours total across all six files. **Risk: none**
(pure documentation, no code changes).

## Phase 5 (after Phase 4)

`docs/Design-Decisions.md`, `docs/FAQ.md`, `docs/Roadmap.md`,
`docs/Development-Log.md`, `docs/Case-Study.md`, retroactive ADRs (0002:
zero-runtime-dependencies; 0003: regex+entropy over an ML/statistical
classifier; 0004: the fingerprint design — see `Finding.fingerprint`'s
existing docstring, which already contains the reasoning, just not in ADR
form yet). See the original audit's roadmap for full effort/ROI estimates.

## Open questions for the human

- Push Phases 1-3 now for real CI validation, or keep accumulating locally
  through Phase 4 (docs-only, so lower urgency than after Phase 3's
  `--jobs` change)?
- Is `[tool.dlp]` config support something you actually want dog-fooded in
  this repo's own `pyproject.toml`, or "built and tested, not
  self-adopted" long-term?

## Potential risks if continuing unattended

- None of Phase 4 touches code — lowest-supervision phase so far. The one
  thing worth double-checking per doc: don't let `Architecture.md`/
  `Performance.md` drift into re-describing what the README already covers
  well; extract and cross-link rather than duplicate, per the original
  audit's Documentation finding (the README is already doing five jobs;
  Phase 4 exists to relieve it, not add a sixth thing that also needs
  updating every time something changes).
