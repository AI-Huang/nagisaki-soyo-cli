from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_NAME = PROJECT_ROOT.name
REPO_DATA_LINK = PROJECT_ROOT / "data"
HOME_DATA_DIR = Path.home() / "Data" / PROJECT_NAME

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
DEFAULT_MODEL = os.getenv("SOYO_MODEL", "gpt-4.1-mini")
DEFAULT_TEMPERATURE = float(os.getenv("SOYO_TEMPERATURE", "0.8"))
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "xhs_crawler")
MYSQL_BIN = os.getenv("MYSQL_BIN", "mysql")


def _move_repo_data(src: Path, dst: Path) -> None:
    if not dst.exists():
        shutil.move(str(src), str(dst))
        return
    if not dst.is_dir():
        raise RuntimeError(f"Data target exists but is not a directory: {dst}")

    for entry in src.iterdir():
        target = dst / entry.name
        if target.exists():
            if entry.is_dir() and target.is_dir():
                _move_repo_data(entry, target)
                entry.rmdir()
                continue
            raise RuntimeError(f"Cannot migrate data because target already exists: {target}")
        shutil.move(str(entry), str(target))

    src.rmdir()


def ensure_data_dir() -> Path:
    HOME_DATA_DIR.parent.mkdir(parents=True, exist_ok=True)

    if REPO_DATA_LINK.is_symlink():
        HOME_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if REPO_DATA_LINK.resolve() != HOME_DATA_DIR.resolve():
            REPO_DATA_LINK.unlink()
            REPO_DATA_LINK.symlink_to(HOME_DATA_DIR, target_is_directory=True)
        return HOME_DATA_DIR

    if REPO_DATA_LINK.exists():
        _move_repo_data(REPO_DATA_LINK, HOME_DATA_DIR)
    else:
        HOME_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if REPO_DATA_LINK.exists():
        if REPO_DATA_LINK.is_dir() and not any(REPO_DATA_LINK.iterdir()):
            REPO_DATA_LINK.rmdir()
        else:
            raise RuntimeError(f"Expected data path to be removable before linking: {REPO_DATA_LINK}")

    REPO_DATA_LINK.symlink_to(HOME_DATA_DIR, target_is_directory=True)
    return HOME_DATA_DIR


DATA_DIR = ensure_data_dir()
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_RUNS_DIR = DATA_DIR / "profile_runs"
PROFILE_RUNS_DIR.mkdir(parents=True, exist_ok=True)
