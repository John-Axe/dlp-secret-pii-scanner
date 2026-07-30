# Limitations

Collected in one place rather than scattered across the README, ADRs, and
commit messages — every claim here is grounded in the actual current
implementation (`src/dlp/`), not a hedge or a guess. If something below
changes, this file should change with it in the same PR.

## Detection coverage

- **Eleven detectors total** (10 regex + Shannon-entropy) — see
  [`README.md`](../README.md#detectors) for the current list. This is a
  narrow, curated set, not an exhaustive catalog of every secret format in
  the wild. Providers with no dedicated rule (Stripe, Twilio, Azure/GCP
  service-account credentials, and many others) are only caught, if at all,
  by the generic entropy detector — which means no MITRE/OWASP-specific
  mapping, no dedicated benchmark fixture, and a real chance of a miss for
  a low-entropy or short credential. See
  [ADR 0001](adr/0001-no-plugin-system-yet.md) for why growing this list is
  a PR to this repo today, not a plugin you can register yourself.
- **No decoding or de-obfuscation.** A secret that's been base64-encoded,
  reversed, split across two concatenated variables, or otherwise
  transformed before being committed generally won't match the regex
  patterns (which expect the credential in its native format) and may or
  may not clear the entropy threshold depending on what the transformation
  did to the character distribution. This tool scans what's literally on
  the line, not what a program would reconstruct at runtime.
- **No cross-file correlation.** Each file is scanned independently. A
  secret deliberately split across two files (half in each, joined at
  runtime) won't be caught by either half alone.
- **The entropy detector's known false-positive class**: base64-encoded
  binary assets (icons, small compiled blobs checked in as text) are
  themselves high-entropy, so they read as a plausible secret to a
  detector that only sees character distribution. Documented with a real
  example and the exact numbers in
  [`README.md`](../README.md#benchmark-results); this repo's own
  `.dlp-baseline.json` and the benchmark corpus both carry accepted
  instances of this, on purpose, rather than hiding it.
- **The credit-card detector's Luhn check reduces, not eliminates, false
  positives.** Any arbitrary 13-19 digit sequence has roughly a 1-in-10
  chance of passing the Luhn checksum by coincidence — an invoice number,
  a phone number with dashes, or a serial number could occasionally read
  as a valid card number. `.dlpignore`/`# dlp-ignore` exist precisely for
  cases like this.
- **PII detectors flag shape, not reality.** The email and SSN detectors
  match anything in the right *format* — `jane.doe@example.com` in a code
  comment is flagged exactly like a real customer's address, and a
  syntactically valid but never-issued SSN is flagged exactly like a real
  one. This is a deliberate precision/recall tradeoff (validating
  liveness/deliverability is out of scope for a static scanner), not an
  oversight.

## Files and size

- **Files over 5MB (`MAX_FILE_SIZE_BYTES`) are never scanned.** As of the
  Phase 2 `ScanStats` work, this is no longer *silent* — a skip is counted
  and reported — but the file itself is still genuinely not looked at,
  regardless of visibility. A secret that only exists inside a large
  committed log dump or data export past that size will be missed.
- **Binary files are never scanned**, by design — detected via a null-byte
  heuristic on the first 8KB (`_is_probably_binary`). A secret embedded as
  a readable string inside an otherwise-binary file (e.g. a compiled
  binary with a hardcoded API key string) will not be found; this tool has
  no string-extraction step the way a dedicated binary-analysis tool
  might.
- **Text is decoded as UTF-8 with errors ignored**
  (`data.decode("utf-8", errors="ignore")`). A file in a different
  encoding may have corrupted or dropped characters before any detector
  ever sees the line, which could shift a match's column or, in rare
  cases, break a pattern that spans the corrupted bytes.

## Performance

- **`--jobs` (parallel scanning) is opt-in and has real startup cost.**
  Spinning up a process pool is only worth it for a full-repo scan;
  applying it to a small `--diff-only` PR check (a handful of files) can
  make that specific run *slower*, not faster. See
  [`README.md`](../README.md#6-parallel-scanning---jobs) for the measured
  numbers. There's no size-based auto-detection — the tool doesn't guess
  whether a given run is "big enough" to benefit; that's left to the
  caller.
- **Throughput is unmeasured in absolute terms across environments.**
  `benchmark/run_throughput_benchmark.py` reports real numbers, but
  deliberately isn't a portable, cross-machine claim — see its own
  docstring for why. The only CI-gated performance guarantee is
  `tests/test_performance_smoke.py`'s generous catastrophic-regression
  ceiling, not a specific throughput floor.

## Ecosystem integration

- **The GitHub PR-comment integration (`dlp.github_pr`) only works inside
  a GitHub Actions `pull_request` job** — it reads `GITHUB_TOKEN`,
  `GITHUB_REPOSITORY`, and `GITHUB_EVENT_PATH` directly and exits cleanly
  (not an error) if they're absent. It has no equivalent for GitLab CI,
  Bitbucket Pipelines, or other CI providers; those would need to build
  their own equivalent using `dlp-scan --format json`'s output.
- **Inline PR comments are capped at 25 by default** (`--max-comments`),
  highest severity first. A PR introducing more findings than the cap
  still fails the build (findings aren't dropped from `--fail-on`
  evaluation), but only the highest-severity ones get an inline comment —
  see the rest visible only in table/JSON/SARIF output or the Security
  tab.
- **`pyproject.toml [tool.dlp]` config support requires Python 3.11+**
  (stdlib `tomllib`). On Python 3.10 — still within this project's
  declared `requires-python = ">=3.10"` — it's a documented no-op, not a
  crash: every CLI flag still works, just without the config-file
  convenience. See [`README.md`](../README.md#5-per-project-defaults-in-pyprojecttoml).

## What this tool deliberately does not do

Not gaps to be closed later — out of scope by design:

- **It doesn't remediate.** `dlp-secret-pii-scanner` finds and reports;
  it never modifies, redacts, removes, or rotates anything in the scanned
  tree. (Compare `aws-auto-remediation` in the same ecosystem, which does
  take remediation action — a different tool, a different trust model.)
- **It doesn't scan git history**, only the working tree (or, with
  `--diff-only`, the current diff against a base ref). A secret committed
  and later removed but still present in an earlier commit is invisible
  to this tool. Tools like `gitleaks` (already run as an independent
  second opinion in this repo's own CI) or `git-secrets` cover that
  surface; this one doesn't duplicate it.
- **It doesn't authenticate or verify a found credential is real, live,
  or currently valid** — a revoked AWS key and an active one are flagged
  identically. Confirming validity would require making a real API call
  against the credential, which this tool never does.
