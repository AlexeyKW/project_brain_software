"""Единая карточка памяти: разбор, загрузка, валидация."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

KINDS = {
    "decision", "constraint", "fact", "map-node",
    "status", "handoff", "pointer", "proposal", "session",
}
STATUSES = {"proposed", "accepted", "superseded", "rejected"}
ORIGINS = {"human", "agent", "derived", "external"}

ID_RE = re.compile(r"^([A-Z])-(\d{3,4})$")
TTL_RE = re.compile(r"^\d+d$")
PREFIX_BY_KIND = {
    "decision": "D", "constraint": "C", "fact": "F", "map-node": "M",
    "status": "S", "handoff": "H", "pointer": "L", "proposal": "P",
    "session": "S",
}
CARD_DIRS = ["decisions", "constraints", "facts", "map", "state",
             "proposals", "sessions", "archive"]

_FRONT_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)


@dataclass
class Card:
    path: Path
    meta: dict
    body: str

    @property
    def id(self) -> str:
        return str(self.meta.get("id", ""))

    @property
    def kind(self) -> str:
        return str(self.meta.get("kind", ""))

    @property
    def title(self) -> str:
        return str(self.meta.get("title", ""))

    @property
    def status(self) -> str:
        return str(self.meta.get("status", ""))

    def rel(self, root: Path) -> str:
        try:
            return self.path.relative_to(root).as_posix()
        except ValueError:
            return str(self.path)


def parse_card(path: Path) -> Card | None:
    """Карточка — Markdown с YAML frontmatter, где есть id и kind."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = _FRONT_RE.match(text)
    if not m:
        return None
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return Card(path, {"__yaml_error__": True}, text[m.end():])
    if not isinstance(meta, dict) or "id" not in meta and "kind" not in meta:
        return None
    return Card(path, meta, text[m.end():])


def load_cards(root: Path) -> list[Card]:
    brain = root / ".brain"
    cards: list[Card] = []
    for sub in CARD_DIRS:
        d = brain / sub
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.md")):
            c = parse_card(p)
            if c is not None:
                cards.append(c)
    return cards


def trust_level(card: Card) -> str:
    """Лестница доверия: ai-inferred → agent-observed → human-verified → machine-checked."""
    ev = card.meta.get("evidence") or []
    if any(isinstance(e, dict) and e.get("type") == "ci" for e in ev):
        return "machine-checked"
    if card.meta.get("verified_by"):
        return "human-verified"
    if ev:
        return "agent-observed"
    return "ai-inferred"


def validate_card(card: Card, card_words: int = 400) -> tuple[list[str], list[str]]:
    """(errors, warnings) по одной карточке."""
    errors: list[str] = []
    warnings: list[str] = []
    m = card.meta

    if m.get("__yaml_error__"):
        return ["frontmatter: YAML не парсится"], []

    for req in ("id", "kind", "title", "status"):
        if not m.get(req):
            errors.append(f"нет обязательного поля '{req}'")

    kind = m.get("kind")
    if kind and kind not in KINDS:
        errors.append(f"kind '{kind}' не из {sorted(KINDS)}")

    status = m.get("status")
    if status and status not in STATUSES:
        errors.append(f"status '{status}' не из {sorted(STATUSES)}")

    origin = m.get("origin")
    if origin and origin not in ORIGINS:
        errors.append(f"origin '{origin}' не из {sorted(ORIGINS)}")

    cid = str(m.get("id", ""))
    if cid:
        mm = ID_RE.match(cid)
        if not mm:
            errors.append(f"id '{cid}' не соответствует формату X-000")
        elif kind in PREFIX_BY_KIND and mm.group(1) != PREFIX_BY_KIND[kind]:
            errors.append(
                f"id '{cid}': префикс '{mm.group(1)}' не соответствует kind '{kind}' "
                f"(ожидается '{PREFIX_BY_KIND[kind]}')")

    conf = m.get("confidence")
    if conf is not None:
        try:
            if not 0.0 <= float(conf) <= 1.0:
                errors.append("confidence вне диапазона 0..1")
        except (TypeError, ValueError):
            errors.append("confidence не число")

    anchors = m.get("anchors") or []
    if not isinstance(anchors, list):
        errors.append("anchors должен быть списком")
    else:
        for a in anchors:
            if not isinstance(a, dict) or not (a.get("path") or a.get("symbol")):
                errors.append("anchor: нужен path или symbol")

    evidence = m.get("evidence") or []
    if not isinstance(evidence, list):
        errors.append("evidence должен быть списком")
    else:
        for e in evidence:
            if not isinstance(e, dict) or not e.get("type"):
                errors.append("evidence: нужен type")

    ttl = m.get("ttl")
    if ttl is not None and not TTL_RE.match(str(ttl)):
        errors.append(f"ttl '{ttl}' не соответствует формату <N>d")

    if kind == "constraint":
        if not m.get("statement"):
            errors.append("constraint: нет поля statement")
        if not m.get("check"):
            warnings.append("constraint без машинной проверки → soft")

    # trust-правило применимо к каноническим записям; handoff/status/session —
    # низкорисковые и авто-мержатся по политике
    if (kind in ("decision", "constraint", "fact", "map-node", "pointer")
            and status == "accepted" and origin == "agent"
            and not m.get("verified_by")):
        warnings.append("accepted агентом без verified_by — агент не может сам поднять trust")

    if ttl and m.get("verified_at"):
        try:
            days = int(str(ttl)[:-1])
            va = m["verified_at"]
            if isinstance(va, (datetime, date)):
                vd = va.date() if isinstance(va, datetime) else va
            else:
                vd = date.fromisoformat(str(va)[:10])
            if (date.today() - vd).days > days:
                warnings.append(f"ttl {ttl} истёк (verified_at {vd}) → needs-review")
        except (ValueError, TypeError):
            warnings.append("verified_at не дата")

    words = len(card.body.split())
    if words > card_words:
        warnings.append(f"тело {words} слов > лимита {card_words}")

    return errors, warnings


def next_id(root: Path, prefix: str, width: int = 4) -> str:
    """Следующий свободный ID с данным префиксом по всем карточкам."""
    best = 0
    for c in load_cards(root):
        mm = ID_RE.match(c.id)
        if mm and mm.group(1) == prefix:
            best = max(best, int(mm.group(2)))
    return f"{prefix}-{best + 1:0{width}d}"
