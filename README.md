# Project Brain

`.brain/` — версионируемая, проверяемая и компилируемая **операционная память**
репозитория: не документация и не инструкции, а состояние, доказательства и
намерения, которые невозможно дёшево восстановить из кода. Источник истины —
код, git и тесты; Brain — их проверяемая проекция плюс то, чего в них
принципиально нет.

Этот репозиторий — готовый скелет уровня **L1** («Ядро»), который кладётся
поверх любого проекта: JSON-схема карточки, дефолтный `brain.yaml`, шаблоны
ADR / constraint / handoff, референсный CLI на Python и GitHub Action.
Сам репозиторий тоже живёт со своим `.brain/` (dogfooding) — смотрите его
как рабочий пример.

## Пять принципов

1. **Храним только невыводимое.** Знание, восстанавливаемое `grep` за секунды,
   не хранится, а генерируется. Ручная память — для *почему так*, *что уже
   пробовали и провалилось*, *что запрещено*, *что сейчас в работе*.
2. **Каждое утверждение имеет якорь и доказательство.** Память без привязки
   к коду/коммиту/прогону тестов — слух, который гниёт молча.
3. **Агенты предлагают, люди утверждают.** Запись в канон — через PR,
   как код. Агент физически ограничен путями `proposals/` и `sessions/`.
4. **Контекст — бюджет, а не свалка.** HOT-пакет ограничен в токенах жёстко;
   превышение — ошибка сборки.
5. **Всё генерируемое восстановимо.** Удалите HOT, адаптеры, индексы —
   `brain compile` вернёт их. Невосстановимое живёт только в тексте под git.

## Быстрый старт

```bash
pipx install .            # или: pip install . / uv tool install .
cd ваш-проект
brain init --level 1      # скелет .brain/ за 30 секунд
brain boot                # HOT-пакет + доступные операции
```

Fallback без всего: открыть `AGENTS.md` → `.brain/HOT.md`. Память работает
даже у человека с блокнотом.

## Команды CLI

| Команда | Что делает |
|---|---|
| `brain init --level 0\|1\|2` | скелет `.brain/` поверх любого репо |
| `brain boot [--budget 800] [--scope services/api]` | старт сессии: HOT + операции |
| `brain compile [--check]` | собрать HOT.md и адаптеры из канона; `--check` — проверка синхронности (CI) |
| `brain lint [--changed]` | схема карточек, бюджет HOT, секреты, дубликаты ID, ttl |
| `brain verify [--changed]` | исполняемые constraints + anchor drift |
| `brain why <path\|symbol\|id>` | «почему здесь так?» — решения и ограничения по коду |
| `brain impact <path>` | что заденет правка: constraints, решения, тесты, owners |
| `brain search "почему не Kafka"` | BM25-lite по памяти, офлайн, с trust-уровнем |
| `brain propose --kind decision --title "…"` | дельта памяти в `proposals/` (единственный путь записи агента) |
| `brain handoff --author имя` | структурированная передача смены |
| `brain decay [--strict] [--write] [--archive ID]` | job устаревания (L2): drift, ttl, дубликаты, архивация |

## Decay (L2): механическое обнаружение устаревания

Еженедельный job (`.github/workflows/brain-decay.yml`, понедельник 04:17 UTC)
собирает отчёт о гниении памяти:

- **anchor drift** — код под якорем изменился, запись не перепроверена → `needs-review`;
- **ttl-истечения** — `verified_at + ttl` в прошлом → `needs-review`;
- **семантические дубликаты** — пары записей со сходством формулировок ≥ 60%
  (нужен явный `supersedes` или слияние);
- **кандидаты в archive/** — записи `superseded`/`rejected` вне архива.

Ничего не удаляется молча: отчёт (`brain decay --write` →
`.brain/state/decay-report.md`) уходит в тот же PR-ревью, а архивация —
только явная команда человека `brain decay --archive D-0042`.

## Структура

```
schema/memory-card.schema.json   # JSON Schema единой карточки памяти
templates/                       # brain.yaml, decision, constraint, handoff, proposal, fact, pointer
src/brain/                       # референсный CLI (Python 3.11+, зависимость: PyYAML)
.github/workflows/brain.yml      # CI: lint → verify → compile --check
.brain/                          # память этого репозитория (рабочий пример)
```

Канонический layout `.brain/` в целевом проекте:

```
.brain/
  brain.yaml            # манифест: версия схемы, бюджеты, политики, scope
  HOT.md                # скомпилированный стартовый пакет (generated, ≤ бюджет)
  map/index.md          # курируемая карта модулей и границ
  decisions/D-xxxx-*.md # ADR+: одна запись = один файл
  constraints/C-xxx-*.md# жёсткие правила, по возможности исполняемые
  facts/                # глоссарий, окружение, указатели (не копии docs/)
  state/                # STATUS.md, handoffs/, tasks.jsonl (append-only)
  proposals/            # staging: дельты памяти от агентов
  evals/                # «тесты памяти»: вопрос → ожидаемые ID/якоря
  templates/            # шаблоны карточек
```

## Единая карточка памяти

Все сущности — один формат (Markdown + YAML frontmatter), различаются `kind`:
`decision | constraint | fact | map-node | status | handoff | pointer | proposal`.
Схема: `schema/memory-card.schema.json`.

**Лестница доверия** (агент не может подняться сам):
`ai-inferred` → `agent-observed` (есть evidence) → `human-verified` (аппрув PR)
→ `machine-checked` (зелёный CI-check).

**Anchor drift:** изменился код под якорем (blob-хэш не совпал), а запись не
перепроверена — `brain verify` ставит `needs-review`. Устаревание ловится
механически, а не «когда-нибудь заметим».

## Исполняемые ограничения

```yaml
kind: constraint
id: C-007
statement: "В core запрещены ORM и любые БД-драйверы"
check: {type: dependency-absent, scope: "packages/core", names: ["sqlalchemy", "psycopg*"]}
severity: blocking
```

Поддержанные проверки: `dependency-absent` (манифесты зависимостей),
`grep-absent` (запрещённый regex в файлах), `path-absent` (запрещённые пути).
Constraint без `check` помечается `soft` и попадает в отчёт о покрытии.

## CI

`.github/workflows/brain.yml` прогоняет на каждый PR:

```yaml
- run: brain lint --changed      # схема, бюджет HOT, секреты
- run: brain verify --changed    # исполняемые constraints + anchor drift
- run: brain compile --check     # HOT и адаптеры синхронны с каноном
```

Политика ревью по видам: `handoff|status|session` — авто-мерж;
`decision|constraint|map` — обязательный человек. Закрепите в CODEOWNERS:

```
.brain/constraints/  @your-team-leads
.brain/decisions/    @your-team-leads
```

## Уровни зрелости

| Уровень | Что включено | Время внедрения |
|---|---|---|
| **L0 Скелет** | AGENTS.md + HOT + handoff, без CLI | 15 минут |
| **L1 Ядро** | + decisions, constraints, lint в CI, один адаптер | 1 день |
| **L2 Полный** | + anchors с blob, evidence, proposals, evals, decay | 1–2 недели |
| **L3 Федерация** | + монорепо/полирепо, imports/exports, MCP | квартал |

## Разработка

```bash
pip install -e .[dev]
PYTHONPATH=src python -m pytest tests/ -q   # 23 теста: golden на HOT + lint/verify/decay
PYTHONPATH=src python -m brain lint && python -m brain verify
```

Тесты golden-типа: фикстура `tests/conftest.py` поднимает временный
репозиторий L2 с фиксированными карточками, `tests/golden/HOT.demo.md` —
эталонный скомпилированный HOT (сборка детерминирована; меняете фикстуру —
пересоздайте golden).

Ограничение C-001 (проверяется `brain verify`): ядро CLI не делает сетевых
вызовов — Brain обязан работать офлайн.
