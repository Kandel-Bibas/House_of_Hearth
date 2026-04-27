import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect

from core.db import Base, make_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run alembic via the running interpreter, with DATABASE_URL pointing at the temp DB."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_alembic_upgrade_creates_all_tables(tmp_path):
    db_path = tmp_path / "migrated.db"
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade failed:\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )

    engine = make_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables_after_alembic = set(inspector.get_table_names()) - {"alembic_version"}
    assert tables_after_alembic == set(Base.metadata.tables.keys())


def test_alembic_downgrade_to_base(tmp_path):
    db_path = tmp_path / "migrated.db"

    up = _run_alembic(db_path, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    down = _run_alembic(db_path, "downgrade", "base")
    assert down.returncode == 0, down.stderr

    engine = make_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    assert tables == set()
