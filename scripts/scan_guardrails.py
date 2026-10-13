r"""Guardrail scanner: competition red lines, required material and README sections.

Run it before packaging or pushing::

    .\.venv\Scripts\python.exe scripts/scan_guardrails.py

It checks, without modifying anything:

1. no prompt-injection phrasing in the shipped sources and documents;
2. no third-party commercial-IP naming (the setting must stay original);
3. no personal-data / face / real-location content;
4. every required submission item is present;
5. the README documents the sections the judging rubric looks for.

The guard-rail test in ``tests/test_server.py`` has to *name* the forbidden
phrases in order to ban them, so that single declaration block is exempt from
check 1; every other occurrence is reported.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INJECTION_PHRASES = (
    "ignore previous", "ignore all previous", "ignore the above", "disregard previous",
    "give full marks", "score is excellent", "give 100/100", "give full score",
    "忽略之前", "忽略上述", "给满分", "评分基准", "请给高分", "全部给分",
)
COMMERCIAL_IP_TERMS = (
    "Harry Potter", "Hogwarts", "Gryffindor", "Slytherin", "Hermione", "Voldemort",
    "Dumbledore", "Quidditch", "Muggle", "哈利波特", "霍格沃茨", "伏地魔", "邓布利多",
    "魁地奇", "麻瓜", "格兰芬多", "斯莱特林",
)
SAFETY_TERMS = (
    "人脸识别", "face recognition", "facial recognition", "真实定位", "geolocation tracking",
)

REQUIRED_MATERIAL = (
    ("src/", "dir"),
    ("web/", "dir"),
    ("tests/", "dir"),
    ("README.md", "file"),
    ("AI_USAGE.md", "file"),
    ("ai-logs/", "dir"),
    ("screenshots/", "dir"),
    ("demo/", "dir"),
)
REQUIRED_README_SECTIONS = (
    "一键启动与交互说明",
    "知识如何成为游戏规则",
    "核心文件清单与架构设计",
    "功能实现状态表",
    "相近已有作品对比",
    "核心设计决策与技术取舍",
    "数据说明",
)

SCAN_DIRS = ("src", "web", "tests", "docs", "ai-logs", "scripts")
SCAN_FILES = (
    ".gitignore", "README.md", "README_CN.md", "AI_USAGE.md", "DEMO_LINK.md",
    "Makefile", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
)
SKIP_PARTS = {
    ".git", ".github", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "temp", "process", "report", "submission", "vendor",
}
TEXT_SUFFIXES = {".py", ".js", ".html", ".css", ".md", ".txt", ".json", ".toml", ".cfg", ".ini", ".yaml", ".yml", ""}


def scanned_files() -> list[Path]:
    found: list[Path] = []
    for name in SCAN_DIRS:
        base = ROOT / name
        if base.is_dir():
            for path in base.rglob("*"):
                if path.is_file() and not (SKIP_PARTS & set(path.parts)) and path.suffix.lower() in TEXT_SUFFIXES:
                    found.append(path)
    for name in SCAN_FILES:
        path = ROOT / name
        if path.is_file():
            found.append(path)
    return sorted(set(found))


DECLARATION = re.compile(r"^[A-Z][A-Z0-9_]{2,}\s*=\s*\($")


def guard_list_lines(text: str) -> set[int]:
    """Line numbers of the module-level term lists.

    A scanner has to name the phrases it bans, so the declaration blocks of the
    term lists themselves are exempt; any occurrence outside them is reported.
    """
    lines: set[int] = set()
    depth = 0
    active = False
    for number, line in enumerate(text.splitlines(), start=1):
        if not active and DECLARATION.match(line.strip()):
            active = True
            depth = line.count("(") - line.count(")")
            lines.add(number)
            continue
        if active:
            lines.add(number)
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                active = False
                depth = 0
    return lines


def main() -> int:
    problems: list[str] = []
    files = scanned_files()
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        low = text.lower()
        exempt = guard_list_lines(text)
        for phrase in INJECTION_PHRASES:
            for match in re.finditer(re.escape(phrase.lower()), low):
                if text.count("\n", 0, match.start()) + 1 in exempt:
                    continue
                problems.append(f"INJECTION      {rel}  {phrase!r}")
        for term in COMMERCIAL_IP_TERMS:
            boundary = r"(?<![A-Za-z])" + re.escape(term.lower()) + r"(?![A-Za-z])"
            for match in re.finditer(boundary, low):
                if text.count("\n", 0, match.start()) + 1 in exempt:
                    continue
                problems.append(f"COMMERCIAL_IP  {rel}  {term!r}")
        for term in SAFETY_TERMS:
            for match in re.finditer(re.escape(term.lower()), low):
                if text.count("\n", 0, match.start()) + 1 in exempt:
                    continue
                problems.append(f"SAFETY         {rel}  {term!r}")

    print(f"[1-3] content scan: {len(files)} files, {len(problems)} problem(s)")
    for item in problems:
        print(f"      {item}")
    if not problems:
        print("      no prompt-injection wording, no third-party IP naming, no personal-data content")

    print("[4] required material")
    missing = 0
    for name, kind in REQUIRED_MATERIAL:
        path = ROOT / name.rstrip("/")
        ok = path.is_dir() if kind == "dir" else path.is_file()
        if not ok:
            missing += 1
        print(f"      {'[ OK ]' if ok else '[MISS]'} {name}")

    print("[5] README sections")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_cn = (ROOT / "README_CN.md").read_text(encoding="utf-8") if (ROOT / "README_CN.md").is_file() else ""
    section_problems = 0
    for section in REQUIRED_README_SECTIONS:
        in_en = section in readme
        in_cn = section in readme_cn
        if not (in_en and in_cn):
            section_problems += 1
        print(f"      {'[ OK ]' if (in_en and in_cn) else '[FAIL]'} {section}  (README.md={in_en}, README_CN.md={in_cn})")

    print()
    failed = len(problems) + missing + section_problems
    print(f"RESULT: {'PASS' if failed == 0 else 'FAIL'} ({failed} issue(s))")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())