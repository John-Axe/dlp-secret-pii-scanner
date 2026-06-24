"""Positive and negative cases for each regex detector plus the entropy detector."""

from __future__ import annotations

from dlp import detectors


def _fires(rule_id: str, line: str) -> bool:
    det = detectors.REGEX_DETECTORS_BY_ID[rule_id]
    return bool(det.scan_line(line))


def test_aws_access_key_id_positive():
    assert _fires("aws_access_key_id", "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")


def test_aws_access_key_id_negative():
    assert not _fires("aws_access_key_id", "this is just AKIA in prose, not a real key")


def test_aws_secret_key_positive():
    assert _fires(
        "aws_secret_key",
        "aws_secret_access_key = wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY12",
    )


def test_aws_secret_key_negative():
    assert not _fires("aws_secret_key", "aws_secret_access_key = ${AWS_SECRET_ACCESS_KEY}")


def test_github_token_positive():
    assert _fires("github_token", 'token = "ghp_00000000000000000000000000000000000A"')


def test_github_token_negative():
    assert not _fires("github_token", "see github.com/ghp_examples for more info")


def test_gitlab_token_positive():
    assert _fires("gitlab_token", "GITLAB_TOKEN: glpat-0000000000000000000A")


def test_gitlab_token_negative():
    assert not _fires("gitlab_token", "GITLAB_TOKEN: ${GITLAB_TOKEN}")


def test_slack_token_positive():
    assert _fires("slack_token", "SLACK_BOT_TOKEN=xoxb-000000000000-000000000000-FAKEFAKEFAKE")


def test_slack_token_negative():
    assert not _fires("slack_token", "SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}")


def test_jwt_positive():
    assert _fires(
        "jwt",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    )


def test_jwt_negative():
    assert not _fires("jwt", "Authorization: Bearer ${ACCESS_TOKEN}")


def test_private_key_block_positive():
    assert _fires("private_key_block", "-----BEGIN RSA PRIVATE KEY-----")


def test_private_key_block_negative():
    assert not _fires("private_key_block", "-----BEGIN CERTIFICATE-----")


def test_generic_password_positive():
    assert _fires("generic_password", 'password = "Tr0ub4dor&3Fake"')


def test_generic_password_negative_placeholder_only():
    assert not _fires("generic_password", "If a user forgets their password, direct them to reset it")


def test_generic_password_negative_suffix_key():
    assert not _fires("generic_password", "database_password: ${DATABASE_PASSWORD}")


def test_email_positive():
    assert _fires("email", "Contact: jane.doe@example.com")


def test_email_negative():
    assert not _fires("email", "Contact support through the help desk portal")


def test_us_ssn_positive():
    assert _fires("us_ssn", "Social Security Number: 123-45-6789")


def test_us_ssn_negative_invalid_area():
    assert not _fires("us_ssn", "Placeholder SSN: 000-12-3456")


def test_us_ssn_negative_invalid_group():
    assert not _fires("us_ssn", "Placeholder SSN: 123-00-6789")


def test_credit_card_positive_luhn_valid():
    assert _fires("credit_card", "Card on file: 4111-1111-1111-1111")


def test_credit_card_negative_luhn_invalid():
    assert not _fires("credit_card", "Invoice number: 1234-5678-9012-3456")


def test_credit_card_negative_too_short():
    assert not _fires("credit_card", "Order number: 411111111111")


def test_entropy_detector_positive():
    matches = detectors.scan_line_entropy(
        "API_SIGNING_SECRET=kQ7vXz2LpN9wTr4FbHc8Ym1Jd6Ks3EoZa5Vt", threshold=4.3
    )
    assert matches


def test_entropy_detector_negative_low_entropy():
    matches = detectors.scan_line_entropy(
        "package-a sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", threshold=4.3
    )
    assert not matches


def test_entropy_detector_negative_short_token():
    matches = detectors.scan_line_entropy("token=abc123", threshold=4.3)
    assert not matches


def test_shannon_entropy_uniform_vs_repetitive():
    assert detectors.shannon_entropy("aaaaaaaaaaaaaaaaaaaa") < detectors.shannon_entropy(
        "kQ7vXz2LpN9wTr4FbHc8"
    )


def test_redact_short_string():
    assert detectors.redact("abc") == "***"


def test_redact_long_string_keeps_prefix_and_suffix():
    redacted = detectors.redact("AKIAIOSFODNN7EXAMPLE")
    assert redacted.startswith("AKIA")
    assert redacted.endswith("MPLE")
    assert "*" in redacted
