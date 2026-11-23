# Карта проекта

> Курируемая карта: модули, границы ответственности, точки входа.
> Только верхний уровень — детали восстанавливаются из кода.

## Модули
- `src/brain/cards.py` — карточка памяти: разбор, валидация, trust
- `src/brain/compiler.py` — сборка HOT.md и generated-адаптеров
- `src/brain/checks.py` — lint (схема/бюджет/секреты) и verify (constraints, drift)
- `src/brain/search.py` — why / impact / search (BM25-lite)
- `src/brain/scaffold.py` — `brain init` уровней L0–L2
- `src/brain/cli.py` — точка входа argparse

## Точки входа
- `brain init --level 1` — скелет поверх любого репо
- `brain boot` — старт сессии (HOT + операции)

## Границы
- ядро CLI не делает сетевых вызовов — см. C-001
