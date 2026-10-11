import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> dict:
    load_dotenv(ROOT / ".env")
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve(path_value: str) -> Path:
    """Config paths are relative to the project root."""
    path = Path(os.path.expandvars(path_value))
    return path if path.is_absolute() else (ROOT / path).resolve()
