# Performance

## Measured numbers (this machine, this session — not a portable claim)

From the session that added `benchmark/run_throughput_benchmark.py` and
`--jobs` (see that commit's message for the full methodology):

| Configuration | 3000 synthetic files (~11MB) |
|---|---|
| Sequential (`--jobs 1`, default) | ~1050 files/sec, ~5.7 MB/sec |
| `--jobs 0` (24 CPUs available) | ~2.5x faster, byte-identical output |

**Why these numbers aren't a promise for your machine**: CPU core count,
clock speed, filesystem (SSD vs. network mount vs. WSL-mounted drive), and
what else is running all affect them directly. Run
`python benchmark/run_throughput_benchmark.py` yourself for a number that
means something on your actual hardware — that's the whole reason this
script exists as a separate, non-CI-gated tool rather than a single
committed number (see its own docstring).

## What's actually CI-gated, and why it's not a throughput number

`tests/test_performance_smoke.py` runs in CI on every push, but asserts a
generous (10-second) ceiling against workloads that normally complete in
well under half a second — it exists to catch a *catastrophic* regression
(the classic case: a future detector regex that starts backtracking
exponentially against adversarial input), not to enforce a specific
files/sec floor. A hard throughput threshold in CI would fail intermittently
whenever a CI runner happens to be slower that day, for reasons that have
nothing to do with a real regression in this codebase — see that test
file's own docstring for the full reasoning.

## Where the time actually goes

Not profiled with a dedicated profiler as part of this pass — the
following is a description of the algorithm's shape from reading
`scanner.py`/`detectors.py`, not a flame-graph result. Worth being clear
about that distinction rather than presenting a read-through as a
measurement.

For a single file, `scan_file`:
1. Reads up to `MAX_FILE_SIZE_BYTES` (5MB) into memory.
2. Splits into lines, and for **every line**, runs **all 10 regex
   detectors** (`detectors.REGEX_DETECTORS`) plus the entropy tokenizer —
   there's no early-exit once one detector matches, and no per-line
   short-circuiting (e.g. skipping obviously-detector-irrelevant lines
   before running all 10 patterns). Every line pays the cost of every
   detector, unconditionally.
3. The entropy detector additionally computes Shannon entropy
   (`shannon_entropy`, an O(token length) operation) for every token
   matching `[A-Za-z0-9+/_=-]{20,}` on the line.

This means total work scales roughly with
`files × lines-per-file × (10 regex passes + entropy-token-scan)` per
line — which is exactly the shape `--jobs` parallelizes across files (see
[`README.md`](../README.md#6-parallel-scanning---jobs)), and exactly the
shape a single adversarial line (many matches, or many entropy-eligible
tokens) could stress, which is what
`tests/test_performance_smoke.py`'s adversarial-line test targets directly.

## Known non-optimizations

Named explicitly rather than left to look like oversights, matching this
project's general practice (see [ADR 0001](adr/0001-no-plugin-system-yet.md)
for the same framing applied to the plugin-system question):

- **No regex pre-filtering.** A line with no `@` character still gets
  tested against the email pattern; a line with no digits still gets
  tested against the credit-card and SSN patterns. A cheap containment
  check before each full regex match (e.g. skip the email pattern unless
  `"@"` is in the line) was not implemented in this pass — plausible future
  work if profiling ever shows regex matching, not I/O, as the actual
  bottleneck for a real workload.
- **`--jobs` has no size-based auto-tuning.** The tool doesn't inspect how
  many files it's about to scan and decide parallelism is or isn't worth
  it — that judgment is left entirely to the caller (see
  [`Limitations.md`](Limitations.md#performance)).
- **No caching across runs.** Every invocation re-scans every file from
  scratch, even if `--diff-only`/`--baseline` weren't used and nothing
  changed since the last run. There's no persistent scan-result cache
  keyed on file content hash.
