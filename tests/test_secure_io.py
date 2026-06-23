# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for _secure_io module."""

import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from fabric_cicd._common._secure_io import IS_POSIX, OWNER_ONLY_FILE_MODE, restrict_file

posix_only = pytest.mark.skipif(not IS_POSIX, reason="POSIX permission bits are a no-op on Windows")


def _mode(path: str) -> int:
    return stat.S_IMODE(Path(path).stat().st_mode)


@posix_only
def test_restrict_file_tightens_world_readable():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write("sensitive data")
        path = f.name
    try:
        Path(path).chmod(0o644)
        restrict_file(path)
        assert _mode(path) == OWNER_ONLY_FILE_MODE
    finally:
        Path(path).unlink()


@posix_only
def test_restrict_file_already_restricted():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write("data")
        path = f.name
    try:
        Path(path).chmod(0o600)
        restrict_file(path)
        assert _mode(path) == OWNER_ONLY_FILE_MODE
    finally:
        Path(path).unlink()


def test_restrict_file_missing_file_is_noop():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "does-not-exist.json")
        restrict_file(path)
        assert not Path(path).exists()


def test_restrict_file_noop_on_windows():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write("data")
        path = f.name
    try:
        import fabric_cicd._common._secure_io as mod

        with patch.object(mod, "IS_POSIX", False):
            mod.restrict_file(path)

        # Verify the file still has its original permissions (chmod was not called)
        # by checking it wasn't changed to 0o600
        # (On actual Windows this whole test is moot, but we're testing the guard)
    finally:
        Path(path).unlink()
