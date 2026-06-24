"""Thumbnail resizing worker."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ResizeJob:
    source_key: str
    target_width: int
    target_height: int


def load_bucket_name() -> str:
    return os.environ["STORAGE_BUCKET"]


def resize(job: ResizeJob) -> bytes:
    raise NotImplementedError("wire up the actual image library here")


def main() -> None:
    bucket = load_bucket_name()
    print(f"watching bucket {bucket} for new uploads")


if __name__ == "__main__":
    main()
