"""Фикстуры: временный репозиторий уровня L2 с двумя каноническими карточками.

Содержимое карточек фиксировано — на него опирается golden-тест HOT
(tests/golden/HOT.demo.md). Меняете фикстуру — пересоздайте golden.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.compiler import compile_all
from brain.config import load_config
from brain.scaffold import init

DECISION = """\
---
id: D-0001
kind: decision
title: Тестовый транспорт — только in-memory очередь
status: accepted
supersedes: []
origin: human
verified_by: ["@tester"]
verified_at: 2026-11-01
confidence: 1.0
anchors:
  - path: "src/**"
evidence:
  - {type: test, cmd: "python -m pytest", result: pass, at: 2026-11-01T00:00Z}
scope: []
ttl: 365d
tags: [transport]
---
## Контекст
Нужен транспорт событий для тестового проекта.

## Решение
In-memory очередь: зависимостей ноль, офлайн.

## Отвергнутые альтернативы
Kafka — избыточна для однопроцессного проекта.

## Последствия
Горизонтальное масштабирование потребует пересмотра.
"""

CONSTRAINT = """\
---
id: C-001
kind: constraint
title: Запрет requests в src
statement: "В src/ запрещён импорт requests"
status: accepted
severity: blocking
origin: human
verified_by: ["@tester"]
verified_at: 2026-11-01
anchors:
  - path: "src/**"
check:
  type: grep-absent
  scope: "src"
  pattern: "import requests"
  files: "**/*.py"
evidence: []
ttl: 365d
tags: [offline]
---
## Почему
Проект обязан работать офлайн.

## Что делать вместо этого
Локальные вычисления без сети.
"""

STATUS = """\
# STATUS — живой срез проекта

## В работе
- Настройка памяти — @tester

## Заблокировано
- Ожидает ревью: политика релизов — @lead
"""

MAP = """\
# Карта проекта

## Модули
- `src/` — ядро приложения — @tester

## Точки входа
- `src/main.py` — запуск
"""


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """Готовый репозиторий: init L2 + карточки + скомпилированный HOT."""
    root = tmp_path / "demo-repo"
    root.mkdir()
    init(root, level=2, project="demo")
    (root / ".brain" / "decisions" / "D-0001-transport.md").write_text(
        DECISION, encoding="utf-8")
    (root / ".brain" / "constraints" / "C-001-no-requests.md").write_text(
        CONSTRAINT, encoding="utf-8")
    (root / ".brain" / "state" / "STATUS.md").write_text(STATUS, encoding="utf-8")
    (root / ".brain" / "map" / "index.md").write_text(MAP, encoding="utf-8")
    src = root / "src"
    src.mkdir()
    (src / "main.py").write_text("print('ok')\n", encoding="utf-8")
    compile_all(root, load_config(root))
    monkeypatch.chdir(root)
    return root
