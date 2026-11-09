import os
import sys
import tempfile
from pathlib import Path

import pytest

# Use a throw-away database and the offline evidence pack for every test run.
_TMP = tempfile.mkdtemp(prefix="rc_tests_")
os.environ["RC_DB"] = str(Path(_TMP) / "test.db")
os.environ["RC_MODE"] = "offline"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("RC_DB", str(tmp_path / "fresh.db"))
    monkeypatch.setenv("RC_MODE", "offline")
    application = app_module.create_app()
    return application.test_client()


@pytest.fixture()
def make_app(monkeypatch, tmp_path):
    """Factory used by the persistence test: two app instances sharing one database file."""
    monkeypatch.setenv("RC_DB", str(tmp_path / "persist.db"))
    monkeypatch.setenv("RC_MODE", "offline")
    return app_module.create_app
