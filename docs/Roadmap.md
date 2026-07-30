# Roadmap

This project is going through a structured, five-phase engineering-quality
pass: an initial audit against production-readiness criteria, followed by
incremental work addressing what it found, each phase on its own local
branch with one commit per coherent change. Nothing below is aspirational
marketing — every "done" phase links to the actual commits, and
`[Unreleased]` in [`CHANGELOG.md`](../CHANGELOG.md) is the authoritative
record of what exists but hasn't shipped in a tagged release yet (still
just `v0.1.0` as of this writing — see
[`Operations.md`](Operations.md#upgrading)).

## Phase 1 — Quick wins ✅ Done

Branch: `engineering-audit/phase-1-quick-wins` (5 commits)

The baseline contributor/maintainer surface a project needs before anyone
external can reasonably engage with it: a way to know how to contribute,
what changed and when, and how to file an issue or review a PR.

| Commit | Change |
|---|---|
| `6552c88` | `CONTRIBUTING.md` |
| `9a58a85` | `CHANGELOG.md`, backfilled from `git log` |
| `7c6d026` | Issue/PR templates + `CODEOWNERS` |
| `3435130` | `--version`, `python -m dlp`, worked `--help` examples |
| `7d73713` | `CHANGELOG.md` catch-up for the above |

## Phase 2 — Engineering improvements ✅ Done

Branch: `engineering-audit/phase-2-engineering-improvements` (6 commits)

CI enforcement and real bugs the audit's manual read of the source turned
up — not cosmetic, things that changed program behavior.

| Commit | Change |
|---|---|
| `9ec4343` | CI gates: `ruff`, strict `mypy`, 90% coverage floor, `py.typed` |
| `d6d9a3c` | Fix: silently-skipped files now surfaced via `ScanStats`, not dropped |
| `c9cd3c4` | Fix: bounded + rate-limit-hardened `github_pr.py` |
| `f6d685c` | Hypothesis property-based tests (Luhn, SSN, entropy validators) |
| `14b62fd` | `pyproject.toml [tool.dlp]` per-project config support |
| `c720e48` | `NEXT_SESSION.md` handoff, completing Phase 2 |

## Phase 3 — Architecture improvements ✅ Done

Branch: `engineering-audit/phase-3-architecture-improvements` (6 commits)

Structural decisions and measured, not assumed, performance work.

| Commit | Change |
|---|---|
| `c3626f9` | [ADR 0001](adr/0001-no-plugin-system-yet.md) — why detectors stay a hardcoded list |
| `99131bd` | Throughput benchmark + CI-gated performance smoke test |
| `faa7ae0` | `NEXT_SESSION.md` progress update |
| `c66049b` | `--jobs` parallel scanning — process pool, chosen over threads after measuring both (processes won, 1.4-3.6x; threads were *slower*, see [`Performance.md`](Performance.md)) |
| `5f0a47e` | `-v`/`--verbose` and `-q`/`--quiet` structured logging |
| `2442f7f` | `NEXT_SESSION.md` handoff, completing Phase 3 |

## Phase 4 — Production-readiness docs ✅ Done

Branch: `engineering-audit/phase-4-production-docs` (7 commits)

The documentation a team would actually need to run this in production and
trust its claims — what it doesn't do, what it trusts, how the pieces fit
together operationally, and what to do when something goes wrong. Three
real factual corrections were caught and fixed while writing these, before
committing (a misattributed backtick-escaping defense, a link to a README
section that didn't describe what it was cited for, an overclaimed "PyPI
publish is wired up" state that `release.yml` didn't actually support yet
— see the commit messages for `165b032` and `35c492e`).

| Commit | Change |
|---|---|
| `76f1798` | `docs/Limitations.md` |
| `165b032` | `docs/Threat-Model.md` |
| `35c492e` | `docs/Architecture.md` (component/sequence/deployment diagrams) |
| `52aa625` | `docs/Operations.md` |
| `49dc176` | `docs/Performance.md` |
| `eabbca1` | `docs/Troubleshooting.md` |
| `f36df78` | `NEXT_SESSION.md` handoff, completing Phase 4 |

**Net result across Phases 1-4:** 130 → 215 tests, coverage 96.45% →
97.46%, five real code bugs found and fixed, three real documentation
inaccuracies caught and fixed before committing.

## Phase 5 — Retroactive design records 🚧 In progress

Branch: `engineering-audit/phase-5-retroactive-docs`

The original five-phase scope for this item was broader — six candidate
docs (`Design-Decisions.md`, `FAQ.md`, `Roadmap.md`, `Development-Log.md`,
`Case-Study.md`, plus three retroactive ADRs). Three of those were
deliberately dropped rather than written: `Design-Decisions.md` would have
substantially duplicated [`docs/adr/`](adr/) (the ADRs already *are* the
design-decision record, more precisely than a parallel narrative could
restate them), and `Case-Study.md`/`Development-Log.md` would have been a
sixth retelling of the same "measured, found a bug, fixed it" stories
already told once, well, in this pass's own commit messages — restating
them risked exactly the duplication this phase was scoped to avoid.

| Item | Status |
|---|---|
| [ADR 0002](adr/0002-zero-runtime-dependencies.md) — zero runtime dependencies | ✅ Done |
| [ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md) — regex + entropy over an ML classifier | ✅ Done |
| [ADR 0004](adr/0004-finding-fingerprint-design.md) — `Finding.fingerprint` design | ✅ Done |
| `docs/Roadmap.md` (this file) | ✅ Done |
| `docs/FAQ.md` | Written only if genuinely new content exists beyond what `Limitations.md`/the ADRs already say |
| `docs/Design-Decisions.md` | Skipped — duplicates `docs/adr/` |
| `docs/Case-Study.md` | Skipped — duplicates commit history |
| `docs/Development-Log.md` | Skipped — duplicates commit history |

## Beyond Phase 5

Not committed to, not scheduled — open questions the audit surfaced that
are genuinely for a human to decide, not a phase to execute:

- **Pushing Phases 1-4 (and 5) to `origin` for real CI validation.**
  Everything through this pass has been developed and verified locally
  (full gate sequence: lint, strict type-check, tests + coverage,
  benchmark, self-scan) but never actually run in GitHub Actions' own
  environment — the `--jobs` `ProcessPoolExecutor` path in particular is
  worth watching closely on a first real CI run, since multiprocessing
  start-method defaults can differ from this development sandbox's.
- **`[tool.dlp]` self-adoption** — this repo doesn't currently use its own
  `pyproject.toml [tool.dlp]` config support (see `pyproject.toml`); it's
  built and tested against other projects' configs, not dog-fooded here.
  Whether that's worth doing is independent of this five-phase pass.
