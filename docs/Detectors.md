# Detectors

A rule-by-rule reference for every detector in `src/dlp/detectors.py` — what
it matches, why, and its known false-positive/false-negative shape.
`README.md`'s [Detectors](../README.md#detectors) section is the one-line
summary list; this is the audit trail behind each line. Every regex quoted
below is copied verbatim from `detectors.py`, not paraphrased — diff this
file against that one if they ever drift.

## Shared shape

Every regex detector is a `Detector` (`detectors.py`): a compiled `pattern`
plus an optional `validator(text, match) -> bool` that runs only on
substrings the pattern already matched, to reject shapes that are
syntactically right but semantically impossible (an invalid SSN area code,
a credit-card-shaped number that fails its checksum). `scan_line` runs
every detector's pattern independently against every line, unconditionally
— there's no shared pre-filter or short-circuiting (see
[`Performance.md`](Performance.md) for what that costs). The entropy
detector (last section below) isn't pattern-based at all; it's the odd one
out and is covered separately.

See [ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md) for why
detection stays regex+entropy rather than a trained classifier, and
[`Limitations.md`](Limitations.md) for coverage gaps that apply across all
detectors (no decoding/de-obfuscation, no cross-file correlation).

---

## `aws_access_key_id` — AWS Access Key ID

- **Severity**: `high`
- **Pattern**: `\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}\b`
- **Detection strategy**: AWS unique identifiers are a fixed-length,
  base32-ish alphabet (`[0-9A-Z]`) string with a stable 4-letter prefix
  denoting resource type. This pattern matches any of 8 known prefixes
  followed by exactly 16 such characters — no validator, since the prefix
  set itself is the signal.
- **Known false positive, verified against AWS's own docs**: only 2 of the
  8 matched prefixes are actually *credentials*. Per
  [AWS's IAM unique-ID-prefix reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html#identifiers-prefixes):
  `AKIA` is a long-term access key and `ASIA` is a temporary (STS) access
  key ID — real secrets. The other six this pattern also matches are
  **not credentials at all**: `AGPA` (user group), `AIDA` (IAM user),
  `AIPA` (EC2 instance profile), `ANPA` (managed policy), `ANVA` (managed
  policy version), `AROA` (role) are AWS's internal unique *resource*
  identifiers — the same kind of thing as a database primary key, sharing
  this format by convention, not a secret. A `AROA...`/`AIDA...`/etc.
  string appearing in an IAM policy `Condition` block (a documented,
  normal usage — see the AWS reference above) will fire this rule despite
  not being sensitive. This was true of this pattern from the project's
  first commit and had never been checked against AWS's own prefix table
  until this doc was written.
- **Known false negative**: prefixes not in this set (`ABIA` bearer
  tokens, `ACCA` context-specific credentials, `APKA` public keys, `ASCA`
  certificates — also from the same AWS reference) aren't matched at all.
  `ABIA` in particular is a real credential-adjacent bearer token this
  rule misses.
- **Why `high` not `critical`**: an access key ID alone can't authenticate
  anything — it needs the paired secret access key. Real risk, but one
  step short of `aws_secret_key`'s directly-usable credential.
- **References**: [AWS IAM unique identifiers](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html#identifiers-prefixes).

## `aws_secret_key` — AWS Secret Access Key

- **Severity**: `critical`
- **Pattern**: `(?i)aws_secret_access_key\s*[=:]\s*["']?([A-Za-z0-9/+]{40})["']?`
- **Detection strategy**: unlike `aws_access_key_id`, an AWS secret key
  has no distinguishing prefix — it's 40 arbitrary base64-alphabet
  characters, indistinguishable from any other 40-character base64 blob
  on its own. This rule instead anchors on the *key name* it's almost
  always assigned to (`aws_secret_access_key`, case-insensitive) rather
  than the value's shape — a context-based match, the only detector here
  that works this way.
- **Known false positive**: `test_aws_secret_key_negative` documents the
  main one directly — `aws_secret_access_key =
  ${AWS_SECRET_ACCESS_KEY}` doesn't match, since `${...}` isn't 40
  base64-alphabet characters. Any *other* 40-char base64-shaped value
  assigned to a variable that happens to be named
  `aws_secret_access_key` but isn't actually one (a test fixture, a
  deliberately fake value) will still fire — this rule can't distinguish
  "shaped like a secret and named like a secret" from "is one."
  `benchmark/corpus/negatives/ignored_test_fixture.py` and
  `.dlp-baseline.json` are this project's own examples of exactly that
  case, worked around with `# dlp-ignore`/baseline rather than a smarter
  pattern.
- **Known false negative**: renamed variables (`secret_key`, `AWS_SECRET`,
  a key embedded in JSON/YAML without the `key = value` shape this regex
  expects) aren't caught by this rule at all — only by the entropy
  detector, if the value clears the threshold.
- **Why `critical`**: directly usable to authenticate as the paired
  access key with no further secret needed — the most severe class of
  credential this tool detects, same tier as `private_key_block`.

## `github_token` — GitHub Token

- **Severity**: `high`
- **Pattern**: `\bgh[pousr]_[A-Za-z0-9]{36}\b`
- **Detection strategy**: matches GitHub's five classic token prefixes in
  one pattern via the `[pousr]` character class.
- **Verified prefix meanings** (per [GitHub's own docs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)):
  `ghp_` personal access token (classic), `gho_` OAuth access token,
  `ghu_` GitHub App user access token, `ghs_` GitHub App installation
  access token, `ghr_` GitHub App refresh token — `tests/test_detectors.py`
  has a positive test for each of the five
  (`test_github_token_gho_prefix` etc.).
- **Known false negative, verified against GitHub's own docs**: **fine-
  grained personal access tokens use the `github_pat_` prefix**, a
  different format entirely, introduced after this project's classic-only
  pattern was written — this rule does not match them at all. This is a
  real, previously-undocumented coverage gap, not a hypothetical one.
- **Known false positive**: `test_github_token_negative` — prose
  mentioning a URL like `github.com/ghp_examples` doesn't match, since
  the literal text after `ghp_` isn't 36 alphanumeric characters, but any
  36-character alphanumeric string genuinely following one of the five
  prefixes (a non-secret test fixture, a deliberately fake example token
  of the right length) reads identically to a real one — same shape-not-
  liveness limitation `Limitations.md` names generally.

## `gitlab_token` — GitLab Token

- **Severity**: `high`
- **Pattern**: `\bglpat-[A-Za-z0-9\-_]{20}\b`
- **Detection strategy**: GitLab personal access tokens use a stable
  `glpat-` prefix followed by 20 URL-safe characters.
- **Known false negative**: GitLab also issues other token types with
  different prefixes (deploy tokens, CI/CD job tokens, project/group
  access tokens) that this rule — scoped specifically to personal access
  tokens — doesn't attempt to cover.
- **Known false positive**: `test_gitlab_token_negative` — an
  unexpanded `${GITLAB_TOKEN}` placeholder doesn't match; a fake but
  correctly-shaped 20-character token after `glpat-` does, same
  shape-only limitation as every prefix-anchored rule here.

## `slack_token` — Slack Token

- **Severity**: `high`
- **Pattern**: `\bxox[baprs]-[A-Za-z0-9-]{10,72}\b`
- **Detection strategy**: matches five `xox*-` prefixes in one pattern.
- **Verified prefix meanings**: per
  [Slack's current token-types docs](https://docs.slack.dev/authentication/tokens),
  `xoxb-` is a bot token and `xoxp-` is a user token — the two Slack
  documents today. This pattern's other three prefixes (`xoxa-`, `xoxr-`,
  `xoxs-`) aren't in Slack's current documentation, consistent with them
  being older/legacy token types (workspace app tokens, refresh tokens)
  Slack no longer documents but may still accept — not verified further
  here, flagged as unconfirmed rather than asserted.
- **Known false negative, verified against Slack's own docs**: Slack's
  current docs list two prefixes this pattern does **not** match at all:
  `xwfp-` (workflow tokens) and `xapp-` (app-level tokens) — both real,
  current Slack credential types introduced after this pattern was
  written.
- **Known false positive**: `test_slack_token_negative` — an unexpanded
  `${SLACK_BOT_TOKEN}` doesn't match; a fake-but-correctly-shaped token
  does.

## `jwt` — JSON Web Token

- **Severity**: `medium`
- **Pattern**: `\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b`
- **Detection strategy**: a JWT (RFC 7519) is three base64url segments
  joined by `.`; the header segment reliably starts `eyJ` because it's
  the base64url encoding of a JSON object opening with `{"` (`e`=`{`,
  `y`=`"`... the base64 encoding of `{"` deterministically starts `eyJ`).
  This anchors on that structural fact rather than a vendor prefix, since
  JWTs aren't vendor-specific.
- **Known false positive**: any three dot-separated base64url-shaped
  segments where the first happens to start `eyJ` matches, whether or not
  it's a real token in use — e.g. a JWT-shaped placeholder in
  documentation or a test fixture (this repo's own
  `benchmark/corpus/positives/jwt_token.txt` is exactly this: a
  fabricated example, not a real credential).
- **Known false negative**: a JWT is only as sensitive as what's inside
  it and how it's used — this rule can't and doesn't distinguish a
  short-lived, low-privilege token from a long-lived admin one; both
  match identically.
- **Why `medium` not `high`**: JWTs are frequently short-lived by design
  and the token alone doesn't reveal the signing key — lower severity
  than a static, long-lived credential, but still real enough not to be
  `low`.

## `private_key_block` — Private Key Block

- **Severity**: `critical`
- **Pattern**: `-----BEGIN (?:RSA|EC|OPENSSH|DSA|PGP) ?PRIVATE KEY-----`
- **Detection strategy**: PEM-format private key headers are a fixed,
  unambiguous string — no shape-guessing needed, the header line itself
  *is* the signal. Covers RSA, EC, OpenSSH, DSA, and PGP key types (the
  optional space handles both `OPENSSH PRIVATE KEY` and the
  no-space-variant header forms).
- **Known false positive**: essentially none by construction — this
  exact header string appearing anywhere means a private key block
  follows; there's no ambiguous case a validator would need to rule out.
- **Known false negative**: `test_private_key_block_public_key_negative`
  documents the deliberate one — `-----BEGIN RSA PUBLIC KEY-----` (a
  *public* key, safe to share) correctly does not match, since the
  pattern requires the literal word `PRIVATE`. Key types not in the
  four-way alternation (e.g. an `EC PRIVATE KEY` is covered, but a
  raw `-----BEGIN PRIVATE KEY-----` with no algorithm prefix — the
  PKCS#8 unencrypted format — is **not** matched by this pattern, since
  the regex requires one of the four listed algorithm words before
  `PRIVATE KEY`). This is a real, previously-undocumented gap: PKCS#8
  keys (a common `openssl genpkey` output format) without an algorithm
  prefix in the header line pass through undetected.
- **Why `critical`**: a private key is immediately, directly usable —
  same tier as `aws_secret_key`.

## `generic_password` — Generic Password Assignment

- **Severity**: `medium`
- **Pattern**: `(?i)\b(?:password|passwd|pwd)["']?\s*[=:]\s*["']?([^\s"'][^"'\n]{5,})["']?`
- **Detection strategy**: the broadest, least-specific rule here on
  purpose — catches `password`/`passwd`/`pwd` (case-insensitive) followed
  by an assignment (`=` or `:`) and at least 6 non-whitespace characters,
  regardless of what's actually assigned. No validator; this is the rule
  `.dlp-baseline.json` documents as intentionally self-triggering — see
  its entry in [`README.md`](../README.md#3-diff-only-scanning--baseline-mode).
- **Known false positive**: this project's own biggest documented
  example — `test_generic_password_negative_placeholder_only` and
  `test_generic_password_negative_suffix_key` show two mitigations
  (prose without an `=`/`:` doesn't match; `database_password:
  ${DATABASE_PASSWORD}` doesn't match since `${...}` isn't 6+ literal
  characters), but a genuinely non-secret, hardcoded-but-fake value of
  the right shape (a docs example, this file's own text above) matches
  identically to a real password.
- **Known false negative**: any password not assigned via `password`/
  `passwd`/`pwd` as the literal variable name (a custom field name, a
  password embedded in a URL, a password split across multiple lines) is
  invisible to this rule.
- **Why `medium`**: high false-positive rate by design (see above) makes
  this a noisier signal than a format-anchored rule like `aws_access_key_id`
  — appropriately lower confidence, not appropriately lower real-world
  severity when it *is* a true positive.

## `email` — Email Address

- **Severity**: `low`
- **Pattern**: `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b`
- **Detection strategy**: a standard, deliberately permissive
  `local@domain.tld` shape — not RFC 5322's full grammar (which allows
  quoted strings, comments, and other rarely-used forms this project has
  no reason to also match).
- **Known false positive**: `test_email_negative` shows prose without an
  `@`-shaped token doesn't match; per
  [`Limitations.md`](Limitations.md#detection-coverage) ("PII detectors
  flag shape, not reality"),
  this rule "flags shape, not reality" — `jane.doe@example.com` in a code
  comment or this repo's own documentation (see
  `docs/Limitations.md`'s own worked example) is flagged exactly like a
  real customer's address.
- **Known false negative**: obfuscated forms (`jane [at] example [dot]
  com`) intentionally don't match — matching them reliably would require
  much looser matching with a much higher false-positive cost.
- **Why `low`**: a bare email address is a much smaller exposure than a
  credential — identifying, not directly exploitable — and false-positive
  risk is nontrivial, so lower confidence-weighted severity is
  appropriate.

## `us_ssn` — US Social Security Number

- **Severity**: `high`
- **Pattern**: `\b(\d{3})-(\d{2})-(\d{4})\b`
- **Validator**: `_ssn_ok` rejects area codes `000`/`666` or starting
  with `9` (never validly issued — the SSA never assigns these), a `00`
  group, or a `0000` serial — real SSA-published structural invalidity
  rules, not arbitrary cutoffs.
- **Detection strategy**: the pattern alone matches any `NNN-NN-NNNN`
  shape; the validator narrows that to numbers the SSA could plausibly
  have issued.
- **Known false positive**: `tests/test_detectors.py`'s
  `test_ssn_ok_area_666_rejected`/`_area_starts_with_9_rejected`/
  `_serial_0000_rejected`/`_group_00_rejected` show what the validator
  *does* catch; anything passing all four checks but still not a real,
  currently-issued SSN (a syntactically valid but never-actually-issued
  number, exactly the case `Limitations.md` names) still matches.
- **Known false negative**: SSNs written without dashes (`123456789`) or
  with spaces (`123 45 6789`) aren't matched — only the canonical
  hyphenated format.
- **Why `high`**: PII with real, direct identity-theft utility on its
  own, unlike email — appropriately more severe.

## `credit_card` — Credit Card Number

- **Severity**: `high`
- **Pattern**: `\b(?:\d[ -]?){13,19}\b`
- **Validator**: `_luhn_ok` implements the standard Luhn checksum (double
  every second digit from the right, subtract 9 if the result exceeds 9,
  sum everything, valid iff divisible by 10) — the same check every real
  card issuer's numbers satisfy.
- **Detection strategy**: the pattern alone is maximally broad (any
  13-19 digit run, optionally space/dash-separated) — the Luhn validator
  does essentially all the real narrowing.
- **Known false positive**: `Limitations.md` states this precisely —
  "any arbitrary 13-19 digit sequence has roughly a 1-in-10 chance of
  passing the Luhn checksum by coincidence" — an invoice number, phone
  number, or serial number can occasionally read as valid.
  `test_credit_card_negative_luhn_invalid` and
  `test_credit_card_negative_too_short` cover the two structural
  rejections (fails checksum; too few digits); `test_luhn_ok_too_many_digits`
  covers the upper bound.
  Documented as intentional and accepted, not a bug to fix without
  changing the tradeoff.
- **Known false negative**: no issuer/BIN-range checking (Visa starts
  with `4`, Mastercard `51`-`55`/`2221`-`2720`, etc.) — any Luhn-valid
  digit run of the right length matches regardless of whether it falls
  in a real card network's actual issued range.
- **Why `high`**: direct financial fraud utility, tempered slightly by
  the coincidental-Luhn-pass false-positive risk named above (not
  `critical`, since — unlike a private key or AWS secret — a card number
  alone, without CVV/expiry, has limited standalone usability for most
  fraud vectors).

---

## `high_entropy_string` — High Entropy String (not a `Detector`, not regex-only)

- **Severity**: `medium`
- **Token pattern**: `[A-Za-z0-9+/_=-]{20,}` (candidate tokens — not a
  detection pattern by itself)
- **Threshold**: Shannon entropy ≥ `4.3` bits/character by default
  (`DEFAULT_ENTROPY_THRESHOLD`, configurable via `--entropy-threshold` or
  `[tool.dlp] entropy_threshold`)
- **Detection strategy**: the fallback for secrets with no known format.
  Every 20+ character token matching the base64-ish charset above is
  scored by `shannon_entropy()` (character-frequency-distribution
  entropy, the same formula used across the security-tooling industry
  for this purpose) and flagged if it clears the threshold — this is the
  one detector with no fixed pattern to match against, only a statistical
  property of the string.
- **Known false positive, this project's one directly-measured one**:
  per [`README.md`'s benchmark table](../README.md#benchmark-results),
  `benchmark/corpus/negatives/embedded_icon_asset.py` — a base64-encoded
  binary icon asset — is exactly as high-entropy as a real secret,
  because compressed/binary data *is* high-entropy by nature to a
  detector that only sees character distribution, not semantic meaning.
  This is the project's only benchmark false positive (94% precision,
  driven entirely by this one case) and the reason `.dlpignore`/
  `# dlp-ignore` exist as the accepted workaround rather than a smarter
  entropy heuristic — see [ADR 0003](adr/0003-regex-entropy-over-ml-classifier.md)
  for why a classifier scoped to fix exactly this case was considered and
  not pursued now.
- **Known false negative**: any secret under 20 characters, or one that
  happens not to clear the entropy threshold (a short, low-entropy
  password, a predictable/structured token), is invisible to this
  detector — the same territory `generic_password`/format-specific rules
  are meant to cover instead.
- **Why `medium`**: the least specific signal here — real risk when it
  fires on an actual secret, but the highest false-positive *class*
  (binary/compressed data) of any detector, so calibrated a notch below
  the format-anchored `high` rules.
