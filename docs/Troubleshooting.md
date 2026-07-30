# Troubleshooting

Symptom → likely cause → fix, for the specific problems most likely to
actually come up. For what the tool doesn't attempt to catch at all (as
opposed to a bug getting in the way of something it should catch), see
[`Limitations.md`](Limitations.md) instead.

## "It didn't catch a secret I know is there"

Work through these in order:

1. **Was the file skipped?** Run with `-v` (or check stderr on any run —
   the skip notice appears unprompted whenever it applies). A file over
   5MB or detected as binary is never scanned at all, not just
   deprioritized. See [`Limitations.md`](Limitations.md#files-and-size).
2. **Is it suppressed?** Check for a trailing `# dlp-ignore`/`// dlp-ignore`
   on that exact line, or a matching pattern in `.dlpignore`, or a fingerprint
   in the `--baseline` file you're using (if any). All three suppress
   silently by design — that's the point of them — but it means "no output"
   doesn't always mean "nothing found."
3. **Does a detector for this format exist at all?** This tool has 11
   detectors total, not exhaustive coverage of every credential format.
   Check [`README.md`](../README.md#detectors) against what you're
   expecting to be caught — a provider with no dedicated rule (Stripe,
   Twilio, most cloud providers besides AWS) is only caught, if at all, by
   the generic entropy detector, and only if the string clears the entropy
   threshold. See [ADR 0001](adr/0001-no-plugin-system-yet.md) if you need
   a rule that doesn't exist yet.
4. **Is the secret transformed somehow?** Base64-encoded, split across
   variables, reversed, etc. — see
   [`Limitations.md`](Limitations.md#detection-coverage). This tool matches
   what's literally on the line.

## "`--jobs` made my scan slower, not faster"

Expected for a small scan (few files, e.g. a `--diff-only` PR check) —
process-pool startup cost isn't free, and outweighs the per-file speedup
until there's enough work to spread across workers. See
[`Performance.md`](Performance.md) for the measured numbers this is based
on. Use `--jobs 1` (the default) for small scans; reach for `--jobs 0`/`N`
on a full-repo scan instead.

## "`[tool.dlp]` in `pyproject.toml` doesn't seem to apply"

1. **Check your Python version.** Config-file support needs the stdlib
   `tomllib`, which is Python 3.11+. On 3.10 it's a silent, documented
   no-op — confirm with `python --version`.
2. **Check you didn't pass `--no-config`.**
3. **Check you're not also passing the same flag on the CLI.** An explicit
   CLI flag always wins over the config file, by design — if `--fail-on
   critical` is in your CI command *and* `fail_on = "low"` is in
   `pyproject.toml`, the CLI flag wins and that's not a bug.
4. **Check the file is actually found.** Config loading walks upward from
   the current directory looking for the nearest `pyproject.toml` — if
   you're running `dlp-scan` from an unexpected working directory (a
   subdirectory, or a different `cwd` in a CI job than you expect), it may
   be finding a different (or no) `pyproject.toml` than the one you're
   editing.

## `dlp-scan: Unknown key(s) in [tool.dlp] (...)`

A key in your `[tool.dlp]` table isn't one of the six recognized ones
(`format`, `fail_on`, `no_entropy`, `entropy_threshold`, `no_color`,
`base_ref`) — almost always a typo (`fail-on` with a hyphen instead of
`fail_on`, or a flag that isn't config-eligible at all, like `--jobs`,
which is deliberately CLI-only — see `README.md`'s config-file section for
why). This is a hard failure (exit 1), not a warning, on purpose — see
`CONTRIBUTING.md` for why this project prefers loud failure over silently
ignoring a misconfiguration.

## "`dlp-scan: command not found`"

The console script isn't on `PATH` — common right after
`pip install --target=<dir>` or in a minimal container image. Use
`python -m dlp` instead of `dlp-scan` — it's the exact same tool, just
invoked as a module rather than through the installed script.

## The pre-commit hook and running `dlp-scan` myself give different results

Expected, not a bug — see [`Operations.md`](Operations.md#as-a-pre-commit-hook):
pre-commit passes the specific staged file paths as arguments, so it's
scanning exactly what's about to be committed, not a directory. Running
`dlp-scan .` yourself scans everything in the current directory tree
instead. If you want to reproduce exactly what pre-commit will do, pass it
the same specific file paths, not `.`.

## `ruff`/`mypy`/`pytest` fail locally but the file I changed looks fine

Almost always a dev-environment mismatch, not a real problem with your
change. Reinstall the pinned versions from `requirements/dev.txt` (not
whatever `pip install ruff` happens to resolve to today) and re-run the
exact sequence in `CONTRIBUTING.md`'s "Before opening a PR" section, in
order — a failure in an earlier step (e.g. `ruff`) can sometimes produce a
confusing downstream symptom in a later one if skipped.

## `--jobs N` (N > 1) raises an OS-level error about creating a process

Some sandboxed or restricted environments (certain serverless platforms,
heavily locked-down CI runners) don't permit spawning subprocesses at all.
`--jobs` uses `concurrent.futures.ProcessPoolExecutor`, which needs that
permission. Fall back to `--jobs 1` (the default) in an environment like
this — there's no other parallelism path today.

## Self-scanning this repo's own docs flags something in a Limitations/Threat-Model-style file

Expected, not a bug: any document that discusses secrets, credentials, or
example values *as examples* (like this repo's own `docs/`, `README.md`,
and `benchmark/corpus/`) will legitimately match a detector pattern written
to catch exactly that shape. Distinguish a real leak from an intentional
illustrative example the same way this repo does for its own docs: a
`.dlpignore` entry, an inline `# dlp-ignore`, or (for an accepted, known
case) a `.dlp-baseline.json` entry with a comment explaining why — never a
silent rewrite to dodge the scanner, per `CONTRIBUTING.md`.
