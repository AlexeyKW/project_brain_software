---
id: C-001
kind: constraint
title: Ядро CLI не делает сетевых вызовов
statement: "В src/brain запрещены requests, urllib.request, httpx и сокеты"
status: accepted
severity: blocking
origin: human
verified_by: ["@alexey"]
verified_at: 2026-11-21
anchors:
  - path: "src/brain/**"
check:
  type: grep-absent
  scope: "src/brain"
  pattern: "\\b(import requests|from requests|urllib\\.request|import httpx|from httpx|socket\\.)"
  files: "**/*.py"
evidence:
  - {type: test, cmd: "brain verify", result: pass, at: 2026-11-21T16:00Z}
ttl: 365d
tags: [cli, offline, security]
---
## Почему
CLI обязан работать офлайн и в регулируемых средах: никаких обязательных
облаков, ревью памяти = обычный PR. Сетевая зависимость в ядре ломает
это обещание. Сеть допустима только в опциональных адаптерах (MCP, L3).

## Что делать вместо этого
Поиск — локальный (BM25-lite / SQLite FTS5), эмбеддинги — опциональны
и живут в .brain/.generated/ как пересобираемый производный индекс.
