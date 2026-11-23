"""brain — эталонный CLI Project Brain. Python 3.11+, офлайн, зависимость: PyYAML."""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, templates
from .cards import PREFIX_BY_KIND, load_cards, next_id
from .checks import lint, verify
from .compiler import build_hot, compile_all
from .config import brain_dir, find_root, get_budget, load_config
from .decay import run_decay
from .scaffold import init as scaffold_init
from .search import impact as search_impact
from .search import search as search_cards
from .search import why as search_why


def _slug(text: str, maxlen: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:maxlen].strip("-") or "card")


def cmd_init(args: argparse.Namespace) -> int:
    return scaffold_init(Path(args.dir), level=args.level, project=args.name)


def cmd_boot(args: argparse.Namespace) -> int:
    root = find_root()
    cfg = load_config(root)
    if not (brain_dir(root) / "brain.yaml").exists():
        print("brain boot: .brain/ не найден. Выполните `brain init --level 1`.")
        return 1
    hot, tokens, err = build_hot(root, cfg, budget=args.budget, scope=args.scope)
    if err:
        print(f"brain boot: ОШИБКА сборки HOT: {err}")
        return 1
    print(hot)
    budget = get_budget(cfg, args.budget)
    print("---")
    print(f"контекст: ≈{tokens}/{budget} токенов"
          + (f" · scope: {args.scope}" if args.scope else ""))
    print("операции: brain why <path|symbol|id> · brain impact <path> · "
          "brain search \"запрос\" · brain propose · brain handoff")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    root = find_root()
    return compile_all(root, load_config(root),
                       budget=args.budget, check=args.check)


def cmd_lint(args: argparse.Namespace) -> int:
    root = find_root()
    return lint(root, load_config(root), changed_only=args.changed)


def cmd_verify(args: argparse.Namespace) -> int:
    root = find_root()
    return verify(root, load_config(root), changed_only=args.changed)


def cmd_why(args: argparse.Namespace) -> int:
    return search_why(find_root(), args.target)


def cmd_impact(args: argparse.Namespace) -> int:
    return search_impact(find_root(), args.path)


def cmd_search(args: argparse.Namespace) -> int:
    root = find_root()
    hits = search_cards(root, args.query, limit=args.limit)
    if not hits:
        print(f"brain search: по '{args.query}' ничего не найдено.")
        return 1
    from .cards import trust_level
    for score, c, snippet in hits:
        print(f"{score:6.2f}  {c.id} [{c.kind}] ({trust_level(c)}) {c.title}")
        print(f"        {c.rel(root)}")
        if snippet:
            print(f"        {snippet}")
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    root = find_root()
    pid = next_id(root, "P")
    kind_prefix = PREFIX_BY_KIND.get(args.kind, "D")
    body = (templates.PROPOSAL
            .replace("id: P-XXXX", f"id: {pid}")
            .replace("<предлагаемое изменение памяти>", args.title))
    tmpl = {
        "decision": templates.DECISION, "constraint": templates.CONSTRAINT,
        "fact": templates.FACT, "pointer": templates.POINTER,
    }.get(args.kind, templates.DECISION)
    target_id = next_id(root, kind_prefix, width=3 if kind_prefix in ("C", "F", "L") else 4)
    delta = tmpl.replace("id: D-XXXX", f"id: {target_id}").replace("id: C-XXX", f"id: {target_id}") \
                .replace("id: F-XXX", f"id: {target_id}").replace("id: L-XXX", f"id: {target_id}")
    body = body.replace(
        "<готовая карточка (frontmatter + тело), которую предлагается принять\n"
        "в decisions/ constraints/ facts/ map/. Канонические пути меняются\n"
        "только через PR с аппрувом человека.>",
        "```yaml\n" + delta.strip() + "\n```")
    out = brain_dir(root) / "proposals" / f"{pid}-{_slug(args.title)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"brain propose: создано {out.relative_to(root)}")
    print("Предложение попадёт в канон только через PR с аппрувом человека "
          "(см. policies в .brain/brain.yaml).")
    return 0


def cmd_decay(args: argparse.Namespace) -> int:
    root = find_root()
    return run_decay(root, load_config(root), strict=args.strict,
                     write=args.write, archive=args.archive)


def cmd_handoff(args: argparse.Namespace) -> int:
    root = find_root()
    hid = next_id(root, "H")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%MZ")
    body = (templates.HANDOFF
            .replace("id: H-XXXX", f"id: {hid}")
            .replace("<тема>", args.title or "сессия"))
    props = sorted((brain_dir(root) / "proposals").glob("P-*.md")) \
        if (brain_dir(root) / "proposals").is_dir() else []
    listing = "\n".join(f"- {p.stem}" for p in props) if props else "- нет"
    body = body.replace("<список P-xxxx из .brain/proposals/ или «нет»>", listing)
    out = brain_dir(root) / "state" / "handoffs" / f"{ts}-{args.author}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"brain handoff: создано {out.relative_to(root)}")
    print("Заполните секции — особенно «Провалившиеся гипотезы»: "
          "это знание не выводится из кода и экономит больше всего токенов.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="brain",
        description="Project Brain — версионируемая операционная память репозитория")
    p.add_argument("--version", action="version", version=f"brain {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="скелет .brain/ поверх любого репо за 30 секунд")
    s.add_argument("--level", type=int, default=1, choices=[0, 1, 2])
    s.add_argument("--name", default=None, help="имя проекта (по умолчанию — имя каталога)")
    s.add_argument("--dir", default=".", help="корень целевого репозитория")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("boot", help="старт сессии: HOT-пакет + доступные операции")
    s.add_argument("--budget", type=int, default=None, help="профиль: 800 / 2000 / 4000")
    s.add_argument("--scope", default=None, help="например services/api")
    s.set_defaults(fn=cmd_boot)

    s = sub.add_parser("compile", help="собрать HOT.md и адаптеры из канона")
    s.add_argument("--check", action="store_true",
                   help="не писать, а проверить синхронность generated-артефактов")
    s.add_argument("--budget", type=int, default=None)
    s.set_defaults(fn=cmd_compile)

    s = sub.add_parser("lint", help="схема карточек, бюджет HOT, секреты, дубликаты")
    s.add_argument("--changed", action="store_true", help="только изменённые файлы")
    s.set_defaults(fn=cmd_lint)

    s = sub.add_parser("verify", help="исполняемые constraints + anchor drift")
    s.add_argument("--changed", action="store_true")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("why", help="почему здесь так: решения/ограничения по коду")
    s.add_argument("target", help="path | symbol | id (D-0042)")
    s.set_defaults(fn=cmd_why)

    s = sub.add_parser("impact", help="что заденет правка: constraints, owners, тесты")
    s.add_argument("path")
    s.set_defaults(fn=cmd_impact)

    s = sub.add_parser("search", help="поиск по памяти (BM25-lite, офлайн)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("propose", help="дельта памяти в .brain/proposals/ (единственный путь записи для агента)")
    s.add_argument("--kind", default="decision",
                   choices=["decision", "constraint", "fact", "pointer"])
    s.add_argument("--title", required=True)
    s.set_defaults(fn=cmd_propose)

    s = sub.add_parser("decay", help="еженедельный job: drift, ttl, дубликаты, архивация (L2)")
    s.add_argument("--strict", action="store_true",
                   help="exit 1 при любых находках (для CI)")
    s.add_argument("--write", action="store_true",
                   help="сохранить отчёт в .brain/state/decay-report.md")
    s.add_argument("--archive", metavar="ID",
                   help="переместить карточку в .brain/archive/ (явное действие человека)")
    s.set_defaults(fn=cmd_decay)

    s = sub.add_parser("handoff", help="структурированная передача смены")
    s.add_argument("--author", default=os.environ.get("USER")
                   or os.environ.get("USERNAME") or "agent")
    s.add_argument("--title", default=None)
    s.set_defaults(fn=cmd_handoff)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
