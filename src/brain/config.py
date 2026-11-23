"""Поиск корня репозитория и загрузка .brain/brain.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml


def find_root(start: Path | None = None) -> Path:
    """Идём вверх от start: корень — где .brain/brain.yaml, иначе где .git."""
    p = (start or Path.cwd()).resolve()
    git_root = None
    for d in (p, *p.parents):
        if (d / ".brain" / "brain.yaml").is_file():
            return d
        if git_root is None and (d / ".git").exists():
            git_root = d
    return git_root or p


def brain_dir(root: Path) -> Path:
    return root / ".brain"


def load_config(root: Path) -> dict:
    cfg_path = brain_dir(root) / "brain.yaml"
    if cfg_path.is_file():
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    return {}


def get_budget(cfg: dict, override: int | None = None) -> int:
    if override:
        return override
    return int(cfg.get("budgets", {}).get("hot", 2000))


def token_chars(cfg: dict) -> float:
    return float(cfg.get("token_chars", 3))


def hot_path(root: Path) -> Path:
    return brain_dir(root) / "HOT.md"
