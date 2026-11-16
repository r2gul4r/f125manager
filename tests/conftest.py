"""Keep synthetic sessions out of the user’s recording library."""

import pytest


@pytest.fixture(autouse=True)
def recording_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("F125_RECORDING_DIR", str(tmp_path / "recordings"))
    monkeypatch.setenv("F125_PRACTICE_SAVE_DIR", str(tmp_path / "steam-remote"))
