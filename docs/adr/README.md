# Architecture Decision Records

Each ADR here documents a real decision this project made, with the
alternatives it was weighed against and why they were passed over — not just
what the code does, but why it does it that way. Format: Context, Problem,
Alternatives, Decision, Consequences, Tradeoffs.

| # | Title | Status |
|---|---|---|
| [0001](0001-no-plugin-system-yet.md) | Detectors stay a hardcoded list; no plugin system yet | Accepted |
| [0002](0002-zero-runtime-dependencies.md) | Zero runtime dependencies | Accepted |
| [0003](0003-regex-entropy-over-ml-classifier.md) | Regex + Shannon entropy, not an ML/statistical classifier | Accepted |
| [0004](0004-finding-fingerprint-design.md) | `Finding.fingerprint`: what it hashes, and what it excludes | Accepted |

New ADRs are numbered sequentially and never renumbered or deleted, even if
superseded — mark a superseded one's Status line accordingly and link
forward to what replaced it, so the history of *why* stays intact.
