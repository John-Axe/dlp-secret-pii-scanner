"""Map this tool's Finding onto the ecosystem-wide shared finding schema.

Deliberately has zero new runtime dependency, matching this repo's
zero-dependency design (see pyproject.toml). Anyone who wants strict
validation against the schema can install `finding-schema` (../finding-schema)
and pass these dicts to `finding_schema.Finding(**d)`; this module doesn't
require it.

Schema: ../finding-schema/schema/finding.schema.json
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .scanner import Finding

SOURCE = "dlp-secret-pii-scanner"

# rule_id -> shared-schema category. Everything not listed here is a "secret".
_PII_RULE_IDS = {"email", "us_ssn", "credit_card"}

# rule_id -> MITRE ATT&CK technique IDs. Conservative on purpose: only map
# what's actually a credential-theft-relevant technique, don't invent
# mappings for PII detectors (privacy exposure isn't an ATT&CK technique).
_MITRE_ATTACK = {
    "aws_access_key_id": ["T1552.001"],
    "aws_secret_key": ["T1552.001"],
    "github_token": ["T1552.001"],
    "gitlab_token": ["T1552.001"],
    "slack_token": ["T1552.001"],
    "generic_password": ["T1552.001"],
    "private_key_block": ["T1552.004"],
    "jwt": ["T1528"],
}

# rule_id -> OWASP Top 10 (2021) category. Left empty for PII rule_ids on
# purpose -- exposed PII isn't cleanly one OWASP Top 10 code, so don't force it.
_OWASP = {
    "aws_access_key_id": ["A02:2021"],
    "aws_secret_key": ["A02:2021"],
    "github_token": ["A02:2021"],
    "gitlab_token": ["A02:2021"],
    "slack_token": ["A02:2021"],
    "generic_password": ["A02:2021"],
    "private_key_block": ["A02:2021"],
    "jwt": ["A02:2021"],
}


def _category(rule_id: str) -> str:
    return "pii" if rule_id in _PII_RULE_IDS else "secret"


def to_shared_finding(finding: Finding) -> dict:
    """Map one dlp Finding onto a dict matching finding.schema.json."""
    return {
        "id": str(uuid.uuid4()),
        "source": SOURCE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": finding.severity,
        "category": _category(finding.rule_id),
        "title": finding.rule_name,
        "description": f"{finding.rule_name} detected in {finding.file}:{finding.line}.",
        "resource": f"{finding.file}:{finding.line}",
        "mitre_attack": _MITRE_ATTACK.get(finding.rule_id, []),
        "owasp": _OWASP.get(finding.rule_id, []),
        "remediation": None,
        "raw": {
            "rule_id": finding.rule_id,
            "column": finding.column,
            "redacted": finding.redacted,
            "fingerprint": finding.fingerprint,
        },
    }


def write_shared_findings_jsonl(findings: list[Finding], path: str | Path) -> None:
    """Write findings.jsonl for the observability stack's Promtail to tail.

    Overwrites the file each run -- a scan is a fresh point-in-time snapshot,
    not an append-only event log.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for finding in findings:
            f.write(json.dumps(to_shared_finding(finding)))
            f.write("\n")
