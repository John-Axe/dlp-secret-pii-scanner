"""Fixtures used by the auth tests. These look like credentials but aren't real."""

# This fake key matches the AWS key-id shape on purpose, to test that our
# auth client rejects malformed keys. Suppressed because it is a fixture.
FAKE_AWS_KEY_FOR_TESTS = "AKIAFAKEFAKEFAKEFAKE"  # dlp-ignore

# This high-entropy-looking string is just a fixed test nonce, not a secret.
TEST_NONCE = "kQ7vXz2LpN9wTr4FbHc8Ym1Jd6Ks3EoZa5Vt"  # dlp-ignore
