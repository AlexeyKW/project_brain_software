"""lint (схема, бюджет, секреты, дубликаты) и verify (constraints + anchor drift)."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
from pathlib import Path

from .cards import Card, load_cards, validate_card
from .compiler import build_hot
from .config import brain_dir, get_budget

DEFAULT_SECRETS = [
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"ghp_[A-Za-z0-9]{36}",
    r"sk-[A-Za-z0-9]{20,}",
    r"(?i)(password|passwd|secret|api[_-]?key)\s*[:=]\s*['\"]?\S{8,}",
]

MANIFEST_NAMES = {
    "requirements.txt", "requirements-dev.txt", "requirements.in",
    "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
    "package.json", "poetry.lock",
}


def glob_match(path: str, pattern: str) -> bool:
    """glob с поддержкой ** ; пути нормализуются к posix."""
    path = path.replace("\\", "/").lstrip("./")
    pattern = pattern.replace("\\", "/").lstrip("./")
    rx = re.escape(pattern)
    rx = rx.replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", ".")
    if re.fullmatch(rx, path):
        return True
    # каталог-префикс: "src/bus" покрывает "src/bus/x.py"
    if "*" not in pattern and path.startswith(pattern.rstrip("/") + "/"):
        return True
    return False


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True,
                             text=True, timeout=20)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def changed_brain_files(root: Path) -> set[Path] | None:
    """Изменённые/новые файлы .brain относительно HEAD~1; None ⇒ git недоступен."""
    out = _git(root, "diff", "--name-only", "HEAD~1", "HEAD", "--", ".brain")
    untracked = _git(root, "ls-files", "-o", "--exclude-standard", "--", ".brain")
    if out is None and untracked is None:
        return None
    files = set()
    for blob in (out or "", untracked or ""):
        for ln in blob.splitlines():
            if ln.strip():
                files.add((root / ln.strip()).resolve())
    return files


def _secrets_scan(root: Path, cfg: dict, files: set[Path] | None) -> list[str]:
    patterns = cfg.get("policies", {}).get("secrets_patterns") or DEFAULT_SECRETS
    rxs = [re.compile(p) for p in patterns]
    targets: list[Path] = []
    if files is not None:
        targets = [p for p in files if p.suffix in (".md", ".yaml", ".yml", ".jsonl")]
    else:
        bd = brain_dir(root)
        if bd.is_dir():
            targets = [p for p in bd.rglob("*")
                       if p.suffix in (".md", ".yaml", ".yml", ".jsonl")
                       and ".generated" not in p.parts]
    hits = []
    for p in targets:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for rx in rxs:
            for m in rx.finditer(text):
                hits.append(f"{p.relative_to(root)}: секрет-паттерн "
                            f"'{rx.pattern[:40]}…' → {m.group(0)[:24]}…")
    return hits


def lint(root: Path, cfg: dict, changed_only: bool = False) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    changed = changed_brain_files(root) if changed_only else None
    if changed_only and changed is None:
        print("brain lint: git недоступен, проверяю все файлы (--changed проигнорирован)")

    card_words = int(cfg.get("budgets", {}).get("card_words", 400))
    cards = load_cards(root)
    if changed is not None:
        cards = [c for c in cards if c.path.resolve() in changed]
        if not cards:
            print("brain lint: изменённых карточек нет")

    seen: dict[str, Path] = {}
    for c in load_cards(root):  # дубликаты ID — всегда по всему канону
        if c.id in seen and seen[c.id] != c.path:
            errors.append(f"дубликат id {c.id}: {seen[c.id]} и {c.path}")
        seen.setdefault(c.id, c.path)

    for c in cards:
        errs, warns = validate_card(c, card_words=card_words)
        for e in errs:
            errors.append(f"{c.rel(root)}: {e}")
        for w in warns:
            warnings.append(f"{c.rel(root)}: {w}")

    # бюджет HOT — жёсткая проверка, всегда по канону
    _, tokens, err = build_hot(root, cfg)
    if err:
        errors.append(f"HOT: {err}")
    else:
        budget = get_budget(cfg)
        if tokens > budget:
            errors.append(f"HOT {tokens} токенов > бюджета {budget}")

    for hit in _secrets_scan(root, cfg, changed):
        errors.append(f"СЕКРЕТ: {hit}")

    for w in warnings:
        print(f"  warn: {w}")
    for e in errors:
        print(f"  ERROR: {e}")
    print(f"brain lint: {len(errors)} ошибок, {len(warnings)} предупреждений")
    return 1 if errors else 0


# ---------------------------------------------------------------- verify

def _git_blob_hash(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def anchor_hash(anchor: dict, root: Path) -> str | None:
    """Текущий хэш содержимого под якорем; None — якорь не разрешился."""
    path = anchor.get("path")
    if not path:
        return None  # символьные якоря требуют tree-sitter/LSP адаптера (L2)
    matches = sorted(p for p in root.glob(path) if p.is_file())
    if not matches:
        return None
    hashes = []
    for p in matches[:200]:
        try:
            hashes.append(_git_blob_hash(p.read_bytes()))
        except OSError:
            return None
    if len(hashes) == 1:
        return hashes[0]
    return hashlib.sha1("\n".join(hashes).encode()).hexdigest()


def anchor_drift(card: Card, root: Path) -> list[str]:
    """Список якорей с дрейфом (записанный blob ≠ текущий)."""
    drifted = []
    for a in card.meta.get("anchors") or []:
        if not isinstance(a, dict):
            continue
        recorded = a.get("blob")
        if not recorded:
            continue
        current = anchor_hash(a, root)
        if current is None:
            drifted.append(f"{a.get('path') or a.get('symbol')}: якорь не разрешился")
        elif not current.startswith(str(recorded)):
            drifted.append(f"{a.get('path') or a.get('symbol')}: "
                           f"blob {recorded} → {current[:8]}")
    return drifted


def _deps_of_manifest(path: Path) -> set[str]:
    deps: set[str] = set()
    try:
        if path.name == "package.json":
            data = json.loads(path.read_text(encoding="utf-8"))
            for k in ("dependencies", "devDependencies"):
                deps.update((data.get(k) or {}).keys())
            return deps
        for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            ln = ln.split("#", 1)[0].strip()
            if not ln or ln.startswith(("-", "[")):
                continue
            name = re.split(r"[=<>~\[; ]", ln, 1)[0].strip().strip('"\'')
            if name:
                deps.add(name.lower())
    except (OSError, json.JSONDecodeError):
        pass
    return deps


def run_check(card: Card, root: Path) -> tuple[str, str]:
    """(result, detail): pass | fail | soft | unknown."""
    check = card.meta.get("check")
    if not check:
        return "soft", "нет машинной проверки"
    ctype = check.get("type")
    scope = root / (check.get("scope") or ".")

    if ctype == "dependency-absent":
        names = [str(n).lower() for n in check.get("names", [])]
        manifests = [p for p in scope.rglob("*") if p.name in MANIFEST_NAMES] \
            if scope.is_dir() else []
        for mp in manifests:
            for dep in _deps_of_manifest(mp):
                if any(fnmatch.fnmatch(dep, pat) for pat in names):
                    return "fail", (f"{mp.relative_to(root)}: запрещённая "
                                    f"зависимость '{dep}'")
        return "pass", f"проверено манифестов: {len(manifests)}"

    if ctype == "grep-absent":
        pattern = re.compile(check.get("pattern", r"$^"))
        files_glob = check.get("files", "**/*")
        scanned = 0
        if scope.is_dir():
            for p in sorted(scope.glob(files_glob)):
                if not p.is_file() or p.stat().st_size > 1_000_000:
                    continue
                scanned += 1
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for i, ln in enumerate(text.splitlines(), 1):
                    if pattern.search(ln):
                        return "fail", (f"{p.relative_to(root)}:{i}: "
                                        f"запрещённый паттерн: {ln.strip()[:80]}")
        return "pass", f"проверено файлов: {scanned}"

    if ctype == "path-absent":
        for pat in check.get("paths", []):
            hits = [p for p in scope.glob(str(pat))]
            if hits:
                return "fail", f"запрещённый путь существует: {hits[0].relative_to(root)}"
        return "pass", "запрещённые пути отсутствуют"

    return "unknown", f"неизвестный тип проверки '{ctype}'"


def verify(root: Path, cfg: dict, changed_only: bool = False) -> int:
    failures: list[str] = []
    soft = 0

    changed = changed_brain_files(root) if changed_only else None
    cards = load_cards(root)
    if changed is not None:
        check_cards = [c for c in cards if c.path.resolve() in changed]
        drift_cards = cards  # drift проверяем по всему канону — код мог измениться
    else:
        check_cards = drift_cards = cards

    print("— constraints —")
    for c in check_cards:
        if c.kind != "constraint" or c.status not in ("accepted", "proposed"):
            continue
        result, detail = run_check(c, root)
        sev = c.meta.get("severity", "soft")
        mark = {"pass": "PASS", "fail": "FAIL", "soft": "SOFT", "unknown": "????"}[result]
        print(f"  [{mark}] {c.id} ({sev}): {c.meta.get('statement', c.title)[:70]} — {detail}")
        if result == "fail" and sev == "blocking":
            failures.append(f"{c.id}: {detail}")
        if result == "soft":
            soft += 1

    print("— anchor drift —")
    drift_count = 0
    for c in drift_cards:
        for d in anchor_drift(c, root):
            drift_count += 1
            print(f"  [DRIFT] {c.id} ({c.rel(root)}): {d} → needs-review")
            if c.status == "accepted":
                failures.append(f"{c.id}: anchor drift ({d})")
    if not drift_count:
        print("  drift не обнаружен")

    print(f"brain verify: {len(failures)} блокирующих нарушений, "
          f"{soft} soft-constraints без проверки, {drift_count} drift")
    return 1 if failures else 0
