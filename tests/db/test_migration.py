import configparser
import subprocess
from pathlib import Path

from sqlalchemy import inspect

from core.db.models import Base
from core.db.session import make_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_ALEMBIC = REPO_ROOT / ".venv" / "bin" / "alembic"


def _write_custom_ini(tmp_path: Path, db_path: Path) -> Path:
    """Copy the project's alembic.ini and override the URL to point at tmp_path."""
    cp = configparser.ConfigParser()
    cp.read(REPO_ROOT / "alembic.ini")
    cp["alembic"]["sqlalchemy.url"] = f"sqlite:///{db_path}"
    custom_ini = tmp_path / "alembic.ini"
    with custom_ini.open("w") as f:
        cp.write(f)
    return custom_ini


def _run_alembic(custom_ini: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(VENV_ALEMBIC), "-c", str(custom_ini), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_alembic_upgrade_creates_all_tables(tmp_path):
    """`alembic upgrade head` on a fresh DB produces the same table set as Base.metadata."""
    db_path = tmp_path / "migrated.db"
    custom_ini = _write_custom_ini(tmp_path, db_path)

    result = _run_alembic(custom_ini, "upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade failed:\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )

    engine = make_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables_after_alembic = set(inspector.get_table_names()) - {"alembic_version"}
    assert tables_after_alembic == set(Base.metadata.tables.keys())


def test_alembic_downgrade_to_base(tmp_path):
    """`alembic downgrade base` removes every table created by the baseline."""
    db_path = tmp_path / "migrated.db"
    custom_ini = _write_custom_ini(tmp_path, db_path)

    up = _run_alembic(custom_ini, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    down = _run_alembic(custom_ini, "downgrade", "base")
    assert down.returncode == 0, down.stderr

    engine = make_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    assert tables == set()
