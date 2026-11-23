"""brain init — скелет .brain/ поверх любого существующего репозитория.

Уровни зрелости:
  L0 Скелет  — brain.yaml, HOT, AGENTS.md, STATUS, handoffs/
  L1 Ядро    — + decisions, constraints, map, facts, proposals, шаблоны
  L2 Полный  — + evidence, evals, sessions, archive
"""

from __future__ import annotations

from pathlib import Path

from . import templates
from .compiler import compile_all
from .config import load_config

L0_DIRS = ["state/handoffs"]
L1_DIRS = L0_DIRS + ["decisions", "constraints", "facts/pointers", "map",
                     "state", "proposals", "templates"]
L2_DIRS = L1_DIRS + ["evidence", "evals", "sessions", "archive", ".generated"]

TEMPLATE_FILES = {
    "decision.md": templates.DECISION,
    "constraint.md": templates.CONSTRAINT,
    "handoff.md": templates.HANDOFF,
    "proposal.md": templates.PROPOSAL,
    "fact.md": templates.FACT,
    "pointer.md": templates.POINTER,
}


def _write(path: Path, content: str, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def init(root: Path, level: int = 1, project: str | None = None) -> int:
    root = root.resolve()
    project = project or root.name
    brain = root / ".brain"
    created: list[Path] = []

    def put(rel: str, content: str) -> None:
        p = root / rel
        if _write(p, content):
            created.append(p)

    dirs = {0: L0_DIRS, 1: L1_DIRS, 2: L2_DIRS}[level]
    for d in dirs:
        (brain / d).mkdir(parents=True, exist_ok=True)

    put(".brain/brain.yaml", templates.BRAIN_YAML.format(project=project))
    put(".brain/state/STATUS.md", templates.STATUS_MD)
    put(".brain/state/tasks.jsonl", templates.TASKS_JSONL_HEAD)
    put(".brain/HOT.md", templates.HOT_PLACEHOLDER)

    if level >= 1:
        put(".brain/map/index.md", templates.MAP_INDEX)
        for name, content in TEMPLATE_FILES.items():
            put(f".brain/templates/{name}", content)
    if level >= 2:
        put(".brain/evals/golden.yaml", templates.EVALS_GOLDEN)
        put(".brain/.generated/.gitignore", templates.GENERATED_GITIGNORE)

    # сразу собираем HOT и адаптеры из (пока пустого) канона
    cfg = load_config(root)
    compile_all(root, cfg)

    print(f"\nbrain init: уровень L{level} готов для '{project}'")
    if created:
        print("Создано:")
        for p in created:
            print(f"  + {p.relative_to(root)}")
    print(
        "\nСледующие шаги:\n"
        "  1. Заполните .brain/state/STATUS.md и .brain/map/index.md\n"
        "  2. Добавьте первую карточку:  brain propose --kind decision --title \"...\"\n"
        "     (после аппрува перенесите её из proposals/ в decisions/)\n"
        "  3. brain compile && brain lint && brain verify\n"
        "  4. Подключите CI: .github/workflows/brain.yml из этого репозитория\n"
        "  5. CODEOWNERS: .brain/constraints/ и .brain/decisions/ → человек-аппрувер")
    return 0
