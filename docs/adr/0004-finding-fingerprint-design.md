# 0004 — `Finding.fingerprint`: what it hashes, and what it deliberately excludes

## Status

Accepted (2026-07-30, retroactive — the decision itself dates to
`Finding.fingerprint`'s introduction in commit `e580fc0`)

## Context

`Finding.fingerprint` (`scanner.py`) is a `sha256(file | rule_id |
redacted)` digest, truncated to 16 hex characters. It's the identity two
independent features build on: `baseline.py`'s `--baseline`/
`--write-baseline` (a known-finding is one whose fingerprint is already in
the baseline file) and `report.py`'s SARIF `partialFingerprints`. Both
depend on the same finding producing the same fingerprint across separate
scans — a baseline written today has to still match the same, unmodified
secret when re-scanned next week, and SARIF's own fingerprinting contract
exists specifically so tools like GitHub's Security tab can track a finding
across commits. The method's docstring already states the core reasoning
("deliberately excludes the line number so it survives unrelated edits
earlier in the file"); this ADR formalizes that into the same
Context/Alternatives/Decision record the project's other structural
choices get, and makes explicit two things the docstring doesn't spell
out: why `redacted` and not the raw match text, and what the exclusion of
line number and column actually costs.

## Problem

What should identify "the same finding" across two scans of a file that
may have changed elsewhere — precisely enough that baseline suppression
and SARIF tracking work as intended, without over- or under-matching?

## Alternatives considered

**A. Include the line number** (`file | line | rule_id | redacted`). The
most precise option — pins a finding to an exact location. Rejected:
`--diff-only` and iterative development mean lines shift constantly as a
file changes elsewhere. A baseline entry keyed to a line number would stop
matching the moment someone adds a blank line above it, silently
un-suppressing an already-accepted, unmodified finding and failing a build
for no real reason — the opposite of what a baseline is for.

**B. Hash the raw matched secret text**, not its redacted preview
(`file | rule_id | raw_match`). Superficially more precise — no risk of
two different secrets sharing the same redacted preview. Rejected on two
grounds:
- Not actually available: `scan_file` calls `detectors.redact(match.text)`
  at the point a `Finding` is constructed (`scanner.py`) and never stores
  the unredacted match anywhere in the `Finding` dataclass. The raw secret
  exists only transiently, inside the loop that builds each `Finding` — by
  design, so nothing downstream (a baseline file on disk, a SARIF log, a
  PR comment payload) can ever hold the literal secret even by accident.
  Fingerprinting the raw text would mean threading a second, sensitive
  field through `Finding` for exactly one internal purpose, widening
  exactly the exposure the redaction step exists to prevent.
- Even setting that aside, hashing the raw secret would make the
  *fingerprint itself* effectively equivalent to knowing the secret existed
  in an unredacted form somewhere in memory/logs at hash time — a smaller
  version of the same problem `redacted` was introduced to avoid, for a
  precision gain that doesn't matter in practice (see Consequences).

**C. Hash `file | rule_id | redacted`, excluding line and column
(status quo).** Stable across unrelated edits anywhere else in the file;
built only from fields the `Finding` already carries for other reasons
(`redacted` exists for display; column is not part of the fingerprint but
line is a `Finding` field the fingerprint doesn't use).

## Decision

**Stay with (C).** Concretely, `Finding.fingerprint` hashes exactly three
fields — `file`, `rule_id`, `redacted` — and nothing else. `line` and
`column` are `Finding` fields but are not part of the fingerprint
computation.

## Consequences

- A finding survives a baseline round-trip across any edit that doesn't
  change its own file, rule, or redacted preview — including edits earlier
  in the same file that shift its line number. `test_scanner.py`'s
  `test_fingerprint_stable_across_line_number_changes` and
  `test_baseline.py`'s round-trip tests cover exactly this property.
- A real, accepted collision class exists: two distinct secrets in the
  same file, same rule, whose `redact()` output happens to be identical —
  most plausible for short secrets, where `redact()` collapses anything
  ≤8 characters to a fixed-length run of `*` regardless of content (e.g.
  two different 8-character passwords both redact to `"********"`). Two
  such findings on the same file/rule collide to the same fingerprint.
  This is a real precision cost, not a hidden bug: `baseline.py`'s
  `write_baseline` stores fingerprints in a `set`, and `cli.py`'s
  `--write-baseline` output message
  (`len({f.fingerprint for f in findings})`) already counts *distinct*
  fingerprints rather than assuming one-per-finding — the collision case
  was accounted for in how the count is reported, even though it isn't
  named explicitly anywhere before this ADR.
- The practical consequence of a collision is suppression, not silence: a
  baselined fingerprint that matches two real, distinct secrets means
  accepting one via baseline also silently baselines the other. For the
  short-secret case this can matter is exactly the class `Limitations.md`
  already flags as low-precision by nature (`generic_password`,
  short-token cases) — a real, if narrow, interaction between two
  already-documented tradeoffs, worth naming here so it isn't rediscovered
  as a surprise later.
- This is revisitable the same way ADR 0001/0002/0003 are: on evidence, not
  a timeline. If the collision case above turned out to matter in practice
  (a real baseline silently absorbing a second, different secret), the
  fix that best preserves this ADR's guarantees would be widening what
  `redact()` reveals for short secrets specifically — not adding the raw
  match back into the fingerprint, which would reopen the exposure
  question in Alternative B.

## Tradeoffs

|  | Chosen (C, file\|rule_id\|redacted) | A (+ line number) | B (raw match instead of redacted) |
|---|---|---|---|
| Survives unrelated edits earlier in the file | Yes | No — re-flags on every line shift | Yes |
| Requires storing the raw secret in `Finding` | No | No | Yes — reopens the redaction boundary |
| Collision risk | Real, for short/identical-redacted secrets on the same file+rule | None (line pins exact position) | None (raw text is unique per secret) |
| Baseline usability across normal development | High | Low — brittle to unrelated changes | High |
