"""Shared pytest fixtures."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    dir_path = Path(tempfile.mkdtemp())
    yield dir_path
    # Force close any open connections first
    try:
        for f in dir_path.rglob("*.db"):
            try:
                os.chmod(f, 0o777)
            except OSError:
                pass
    except OSError:
        pass
    shutil.rmtree(dir_path, ignore_errors=True)
