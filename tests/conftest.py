"""Test fixtures for resilient-read.

Path resolution anchors at the current working directory by default. Each
test runs with CWD chdir'd into its ``tmp_path`` so that relative reads
resolve inside the workspace.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _chdir_to_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
