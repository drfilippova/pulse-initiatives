import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pulse import db  # noqa: E402


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Отдельная пустая база для каждого теста."""
    path = tmp_path / "test.db"
    monkeypatch.setenv("PULSE_DB", str(path))
    db.init_db()
    return path
