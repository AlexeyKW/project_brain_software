"""Golden- и behaviour-тесты CLI brain: lint / verify / compile / decay и адресный доступ."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from brain.checks import _git_blob_hash
from brain.cli import main

GOLDEN = Path(__file__).parent / "golden" / "HOT.demo.md"


def write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------- compile

def test_compile_check_deterministic(repo):
    assert main(["compile", "--check"]) == 0


def test_golden_hot(repo):
    hot = (repo / ".brain" / "HOT.md").read_text(encoding="utf-8")
    assert hot == GOLDEN.read_text(encoding="utf-8")


def test_compile_budget_overflow_is_error(repo, capsys):
    assert main(["compile", "--budget", "10"]) == 1
    assert "бюджет" in capsys.readouterr().out.lower()


def test_boot_budget_profile(repo, capsys):
    assert main(["boot", "--budget", "800"]) == 0
    out = capsys.readouterr().out
    assert "≤ 800 токенов" in out
    assert "C-001" in out and "D-0001" in out  # constraints и реестр решений в HOT


# ---------------------------------------------------------------- lint

def test_lint_clean(repo):
    assert main(["lint"]) == 0


def test_lint_schema_error(repo, capsys):
    write(repo, ".brain/decisions/D-0002-broken.md",
          "---\nid: D-0002\nkind: decision\nstatus: proposed\n---\nтело\n")
    assert main(["lint"]) == 1
    assert "title" in capsys.readouterr().out


def test_lint_duplicate_id(repo, capsys):
    src = (repo / ".brain" / "decisions" / "D-0001-transport.md").read_text(encoding="utf-8")
    write(repo, ".brain/facts/D-0001-copy.md", src)
    assert main(["lint"]) == 1
    assert "дубликат id D-0001" in capsys.readouterr().out


def test_lint_id_prefix_mismatch(repo, capsys):
    write(repo, ".brain/constraints/C-002-wrong.md",
          "---\nid: D-0099\nkind: constraint\ntitle: x\nstatement: y\n"
          "status: proposed\n---\nтело\n")
    assert main(["lint"]) == 1
    assert "префикс" in capsys.readouterr().out


def test_lint_secret_blocked(repo, capsys):
    write(repo, ".brain/facts/F-001-leak.md",
          "---\nid: F-001\nkind: fact\ntitle: Доступ\nstatus: proposed\n---\n"
          "ключ: AKIA1234567890ABCDEF\n")
    assert main(["lint"]) == 1
    assert "СЕКРЕТ" in capsys.readouterr().out


# ---------------------------------------------------------------- verify

def test_verify_pass(repo):
    assert main(["verify"]) == 0


def test_verify_constraint_violation(repo, capsys):
    write(repo, "src/bad.py", "import requests\n")
    assert main(["verify"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_verify_anchor_drift(repo, capsys):
    target = repo / "src" / "main.py"
    blob = _git_blob_hash(target.read_bytes())[:8]
    write(repo, ".brain/decisions/D-0002-anchored.md", f"""\
---
id: D-0002
kind: decision
title: Якорь на main.py
status: accepted
origin: human
verified_by: ["@tester"]
anchors:
  - {{path: "src/main.py", blob: {blob}}}
evidence: []
---
тело
""")
    assert main(["verify"]) == 0  # код не менялся — drift нет
    target.write_text("print('changed')\n", encoding="utf-8")
    assert main(["verify"]) == 1
    assert "DRIFT" in capsys.readouterr().out


# ---------------------------------------------------------------- why / impact / search

def test_why_by_id(repo, capsys):
    assert main(["why", "D-0001"]) == 0
    assert "In-memory" in capsys.readouterr().out


def test_why_by_path(repo, capsys):
    assert main(["why", "src/main.py"]) == 0
    assert "C-001" in capsys.readouterr().out


def test_impact_lists_constraints(repo, capsys):
    assert main(["impact", "src/main.py"]) == 0
    out = capsys.readouterr().out
    assert "C-001" in out and "python -m pytest" in out


def test_search_finds_kafka(repo, capsys):
    assert main(["search", "почему не Kafka"]) == 0
    assert "D-0001" in capsys.readouterr().out


# ---------------------------------------------------------------- propose / handoff

def test_propose_writes_to_staging(repo, capsys):
    assert main(["propose", "--kind", "constraint", "--title", "No ORM"]) == 0
    props = list((repo / ".brain" / "proposals").glob("P-*.md"))
    assert len(props) == 1
    text = props[0].read_text(encoding="utf-8")
    assert "kind: proposal" in text and "id: C-002" in text


def test_handoff_lists_proposals(repo):
    main(["propose", "--kind", "fact", "--title", "Fakt"])
    assert main(["handoff", "--author", "tester"]) == 0
    handoffs = list((repo / ".brain" / "state" / "handoffs").glob("*.md"))
    assert len(handoffs) == 1
    text = handoffs[0].read_text(encoding="utf-8")
    assert "Провалившиеся гипотезы" in text
    assert re.search(r"P-\d{4}", text)  # предложение памяти подхвачено


# ---------------------------------------------------------------- decay

def _old_card(root: Path, cid: str = "F-001") -> Path:
    return write(root, f".brain/facts/{cid}-old.md", f"""\
---
id: {cid}
kind: fact
title: Старый факт про окружение
status: accepted
origin: human
verified_by: ["@tester"]
verified_at: 2020-01-01
ttl: 30d
evidence: []
---
тело
""")


def test_decay_clean(repo):
    assert main(["decay", "--strict"]) == 0


def test_decay_ttl_expired(repo, capsys):
    _old_card(repo)
    assert main(["decay", "--strict"]) == 1
    out = capsys.readouterr().out
    assert "TTL истёк" in out and "F-001" in out


def test_decay_duplicates(repo, capsys):
    write(repo, ".brain/decisions/D-0002-dup.md",
          (repo / ".brain" / "decisions" / "D-0001-transport.md")
          .read_text(encoding="utf-8").replace("id: D-0001", "id: D-0002"))
    assert main(["decay", "--strict"]) == 1
    assert "D-0001" in capsys.readouterr().out


def test_decay_write_report(repo):
    assert main(["decay", "--write"]) == 0
    report = repo / ".brain" / "state" / "decay-report.md"
    assert report.is_file()
    assert "Decay-отчёт" in report.read_text(encoding="utf-8")


def test_decay_archive_move(repo, capsys):
    assert main(["decay", "--archive", "D-0001"]) == 0
    assert (repo / ".brain" / "archive" / "D-0001-transport.md").is_file()
    assert not (repo / ".brain" / "decisions" / "D-0001-transport.md").exists()
    # повторная архивация — ошибка
    assert main(["decay", "--archive", "D-0001"]) == 1
