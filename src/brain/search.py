"""Адресный доступ к памяти: why / impact / search (BM25-lite, офлайн)."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from .cards import ID_RE, Card, load_cards, trust_level
from .checks import glob_match
from .config import brain_dir

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё_]{2,}")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _doc_tokens(c: Card) -> list[str]:
    tokens = tokenize(c.title) * 3
    tokens += tokenize(" ".join(c.meta.get("tags") or [])) * 2
    tokens += tokenize(str(c.meta.get("statement", ""))) * 2
    tokens += tokenize(c.body)
    return tokens


def search(root: Path, query: str, limit: int = 10) -> list[tuple[float, Card, str]]:
    cards = load_cards(root)
    if not cards:
        return []
    docs = {c.id: Counter(_doc_tokens(c)) for c in cards}
    n = len(docs)
    df: Counter[str] = Counter()
    for tf in docs.values():
        df.update(tf.keys())
    q = tokenize(query)
    scored = []
    for c in cards:
        tf = docs[c.id]
        score = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] / (tf[term] + 1.2)
        if score > 0:
            scored.append((score, c, _snippet(c, q)))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:limit]


def _snippet(c: Card, q: list[str]) -> str:
    for ln in c.body.splitlines():
        low = ln.lower()
        if any(t in low for t in q) and ln.strip() and not ln.startswith("#"):
            return ln.strip()[:160]
    return c.body.strip().splitlines()[0][:160] if c.body.strip() else ""


def _anchor_paths(c: Card) -> list[str]:
    return [a.get("path") for a in (c.meta.get("anchors") or [])
            if isinstance(a, dict) and a.get("path")]


def _anchor_symbols(c: Card) -> list[str]:
    return [a.get("symbol") for a in (c.meta.get("anchors") or [])
            if isinstance(a, dict) and a.get("symbol")]


def find_by_anchor(root: Path, target: str) -> list[Card]:
    """Карточки, чьи якоря покрывают path/symbol."""
    norm = target.replace("\\", "/").lstrip("./")
    hits = []
    for c in load_cards(root):
        if any(glob_match(norm, p) or glob_match(p, norm) for p in _anchor_paths(c)):
            hits.append(c)
        elif norm in _anchor_symbols(c):
            hits.append(c)
    return hits


def print_card(c: Card, root: Path, body_lines: int = 40) -> None:
    print(f"\n=== {c.id} [{c.kind}] — {c.title}")
    print(f"    статус: {c.status} · trust: {trust_level(c)} · {c.rel(root)}")
    body = c.body.strip().splitlines()
    for ln in body[:body_lines]:
        print(f"    {ln}")
    if len(body) > body_lines:
        print(f"    … (+{len(body) - body_lines} строк)")


def why(root: Path, target: str) -> int:
    cards = load_cards(root)
    if ID_RE.match(target):
        hits = [c for c in cards if c.id == target.upper()]
    elif "/" in target or "\\" in target or "." in Path(target).name:
        hits = find_by_anchor(root, target)
    else:
        ranked = search(root, target, limit=3)
        hits = [c for _, c, _ in ranked]
    if not hits:
        print(f"brain why: ничего не найдено по '{target}'. "
              f"Возможно, это знание ещё не записано — `brain propose`.")
        return 1
    for c in hits:
        print_card(c, root)
    return 0


def impact(root: Path, path: str) -> int:
    norm = path.replace("\\", "/").lstrip("./")
    cards = find_by_anchor(root, norm)

    cons = [c for c in cards if c.kind == "constraint" and c.status == "accepted"]
    decs = [c for c in cards if c.kind == "decision" and c.status == "accepted"]
    others = [c for c in cards if c not in cons and c not in decs]

    print(f"brain impact: {norm}")
    print(f"\nОграничения, которые заденет правка ({len(cons)}):")
    for c in cons:
        sev = c.meta.get("severity", "soft")
        print(f"  [{sev}] {c.id}: {c.meta.get('statement', c.title)}")
    if not cons:
        print("  нет")

    print(f"\nРешения, привязанные к этому коду ({len(decs)}):")
    for c in decs:
        print(f"  {c.id}: {c.title} — подробнее: brain why {c.id}")
    if not decs:
        print("  нет")

    tests = []
    for c in cards:
        for e in c.meta.get("evidence") or []:
            if isinstance(e, dict) and e.get("type") == "test" and e.get("cmd"):
                tests.append(e["cmd"])
    if tests:
        print("\nРелевантные проверки (из evidence):")
        for t in sorted(set(tests)):
            print(f"  - {t}")

    owners = _owners_for(root, norm)
    if owners:
        print("\nВладельцы (map/graph.json):")
        for o in owners:
            print(f"  - {o}")

    if others:
        print(f"\nПрочие записи ({len(others)}): "
              + ", ".join(c.id for c in others[:8]))
    return 0


def _owners_for(root: Path, path: str) -> list[str]:
    graph = brain_dir(root) / "map" / "graph.json"
    if not graph.is_file():
        return []
    try:
        data = json.loads(graph.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    owners = []
    for node in data.get("nodes", []):
        paths = node.get("paths", [])
        if any(glob_match(path, p) for p in paths):
            owners.extend(node.get("owners", []))
    return owners
