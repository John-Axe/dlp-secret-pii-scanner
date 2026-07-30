"""Legacy deployment script for the widget-service worker fleet.

PLANTED FAKE CREDENTIALS for benchmark testing only - this file exists to
exercise multiple detectors firing on one realistic-looking file, not to
represent a real incident. Contact platform-team@example.com with questions.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REGION = "us-east-1"
DEFAULT_INSTANCE_TYPE = "t3.medium"


@dataclass
class DeployTarget:
    name: str
    region: str
    instance_type: str


def load_targets() -> list[DeployTarget]:
    return [
        DeployTarget("worker-a", DEFAULT_REGION, DEFAULT_INSTANCE_TYPE),
        DeployTarget("worker-b", DEFAULT_REGION, DEFAULT_INSTANCE_TYPE),
    ]


# --- Cloud credentials (hardcoded here temporarily during migration) -------
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
aws_secret_access_key = "EXAMPLEFAKESECRETKEYNOTREALPLANTED00000A"

# --- CI notification hook ---------------------------------------------------
SLACK_BOT_TOKEN = "xoxb-000000000000-000000000000-FAKEFAKEFAKEFAKEFAKEFAKE"

# --- Internal release-notes bot (reads PR titles, posts a summary) ---------
GITHUB_TOKEN = "ghp_00000000000000000000000000000000000A"

# --- Legacy admin console, scheduled for removal ---------------------------
password = "Tr0ub4dor&3Fake"  # admin console, scheduled for removal


def notify_slack(message: str) -> None:
    print(f"[slack:{SLACK_BOT_TOKEN[:8]}...] {message}")


def notify_github(pr_number: int, summary: str) -> None:
    print(f"[github:{GITHUB_TOKEN[:8]}...] PR #{pr_number}: {summary}")


def build_aws_client_config() -> dict[str, str]:
    return {
        "access_key_id": AWS_ACCESS_KEY_ID,
        "secret_access_key": aws_secret_access_key,
        "region": DEFAULT_REGION,
    }


def rsync_artifact(target: DeployTarget, artifact_path: Path) -> None:
    subprocess.run(
        ["rsync", "-az", str(artifact_path), f"deploy@{target.name}:/opt/app/"],
        check=True,
    )


def deploy_all(artifact_path: Path) -> int:
    for target in load_targets():
        rsync_artifact(target, artifact_path)
        notify_slack(f"deployed to {target.name} ({target.region})")
    return 0


def main() -> int:
    artifact = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/app.tar.gz")
    return deploy_all(artifact)


if __name__ == "__main__":
    raise SystemExit(main())
