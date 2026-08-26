"""Shared pytest fixtures."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests.

    The path is resolved to its canonical (long) form. ``tempfile.mkdtemp``
    returns whatever the OS ``TEMP`` env var points at, and on Windows CI
    runners that is an 8.3 short path (``C:\\Users\\RUNNER~1\\...``). Leaving the
    short form made tests that compare a path against ``find_codenexus_index``'s
    resolved output fail on Windows only — ``RUNNER~1`` != ``runneradmin`` even
    though they are the same directory. Resolving here aligns ``temp_dir`` with
    pytest's own ``tmp_path`` (which resolves its basetemp) so every test using
    this fixture sees one canonical path representation.
    """
    dir_path = Path(tempfile.mkdtemp()).resolve()
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
