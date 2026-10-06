import shutil
import subprocess
import sys
from pathlib import Path

import main


def test_console_menu_runs_from_another_directory(tmp_path):
    data_dir = tmp_path / "data"
    shutil.copytree(
        main.DATA_DIR, data_dir, ignore=shutil.ignore_patterns("*.sqlite3*")
    )
    result = subprocess.run(
        [
            sys.executable, str(Path(main.__file__).resolve()),
            "--data-dir", str(data_dir),
        ],
        cwd=tmp_path, input="9\n1\n\n0\n", capture_output=True, text=True,
        encoding="utf-8", timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "4.67/5" in result.stdout
    assert "5/5" in result.stdout


def test_console_rejects_incomplete_seed_files(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    (tmp_path / "users.json").write_text("[]", encoding="utf-8")
    assert main.main([]) == 1
    assert not (tmp_path / "journal.sqlite3").exists()
