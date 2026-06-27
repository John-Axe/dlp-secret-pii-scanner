"""DLP secret & PII scanner."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dlp-secret-pii-scanner")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"
