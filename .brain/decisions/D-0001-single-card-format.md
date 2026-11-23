---
id: D-0001
kind: decision
title: Единый формат карточки для всех сущностей памяти
status: accepted
supersedes: []
origin: human
verified_by: ["@alexey"]
verified_at: 2026-11-21
confidence: 1.0
anchors:
  - path: ".brain/**"
evidence:
  - {type: commit, ref: "initial-skeleton"}
scope: []
ttl: 365d
tags: [core, data-model]
---
## Контекст
Память проекта включает решения, ограничения, факты, handoff'ы и узлы карты.
Разные форматы для каждой сущности потребовали бы отдельных парсеров
в каждом инструменте-клиенте.

## Решение
Все сущности — один формат (Markdown + YAML frontmatter), различаются полем
`kind`. Любой инструмент понимает любую запись; валидация — одной
JSON-схемой (`schema/memory-card.schema.json`).

## Отвергнутые альтернативы
- Отдельные схемы на каждый kind — отказ: дублирование tooling.
- Один гигантский MEMORY.md — отказ: merge-ад и неконтролируемый рост
  (явный анти-паттерн концепции).

## Последствия
Один объект = один файл. ID-префикс определяется kind'ом и проверяется lint'ом.
