# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for _secure_io module."""

import os
import stat
import tempfile
from unittest.mock import patch

import pytest

from fabric_cicd._common._secure_io import IS_POSIX, OWNER_ONLY_FILE_MODE, restrict_file

posix_only = pytest.mark.skipif(not IS_POSIX, reason="POSIX permission bits are a no-op on Windows")


def _mode(path: str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


@posix_only
def test_restrict_file_tightens_world_readable():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write("sensitive data")
        path = f.name
    try:
        os.chmod(path, 0o644)
        restrict_file(path)
        assert _mode(path) == OWNER_ONLY_FILE_MODE
    finally:
        os.unlink(path)


@posix_only
def test_restrict_file_already_restricted():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write("data")
        path = f.name
    try:
        os.chmod(path, 0o600)
        restrict_file(path)
        assert _mode(path) == OWNER_ONLY_FILE_MODE
    finally:
        os.unlink(path)


def test_restrict_file_missing_file_is_noop():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "does-not-exist.json")
        restrict_file(path)
        assert not os.path.exists(path)


def test_restrict_file_noop_on_windows():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write("data")
        path = f.name
    try:
        with patch("fabric_cicd._common._secure_io.IS_POSIX", False):
            from fabric_cicd._common._secure_io import restrict_file as _rf

            # Re-import won't pick up the patch; call with patched module
            import fabric_cicd._common._secure_io as mod

            original_chmod = os.chmod
            chmod_called = []
            with patch("os.chmod", side_effect=lambda *a, **k: chmod_called.append(a)):
                mod.restrict_file(path)
            # On "Windows" (mocked), chmod should not be called
            assert chmod_called == []
    finally:
        os.unlink(path)
