---
id: C-XXX
kind: constraint
title: "<краткое имя правила>"
statement: "<одна проверяемая формулировка: что запрещено/обязательно>"
status: proposed
severity: blocking      # blocking ломает CI; soft — только отчёт о покрытии
origin: human
verified_by: []
verified_at: null
anchors:
  - path: "src/**"
check:                  # машинная проверка; без неё constraint считается soft
  type: grep-absent     # dependency-absent | grep-absent | path-absent
  scope: "src"
  pattern: "<запрещённый regex>"
  files: "**/*.py"
evidence: []
ttl: 365d
tags: []
---
## Почему
<причина запрета; инцидент/провал, из которого правило выросло>

## Что делать вместо этого
<разрешённая альтернатива>
