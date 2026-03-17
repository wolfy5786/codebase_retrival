"""
SHA-256 hashing for file content (change detection, manifest).
"""
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA-256 hex digest of file contents.
    """
    logger.info("compute_file_hash started file_path=%s", file_path)

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)

    digest = hasher.hexdigest()
    logger.info("compute_file_hash ended file_path=%s hash=%s", file_path, digest[:16])
    return digest
