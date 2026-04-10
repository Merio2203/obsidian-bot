from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "scripts" / "auto_update.sh"


def test_auto_update_script_is_valid_bash() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_auto_update_script_is_executable() -> None:
    assert os.access(SCRIPT_PATH, os.X_OK)


def test_auto_update_script_has_safety_guards() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "flock -n 9" in content
    assert "git merge-base --is-ancestor" in content
    assert "git pull --ff-only" in content
    assert "docker compose up -d --build" in content
    assert "AUTO_UPDATE_BRANCH" in content
    assert "AUTO_UPDATE_IGNORE_PATHS" in content
    assert ":(exclude)" in content
