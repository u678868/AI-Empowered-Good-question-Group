r"""Build the submission mirror and the email submission package.

Two different deliverables come out of the same file set:

* ``submission/`` - the mirror that is pushed to the Group repository root.  Only
  files that belong in the submission are copied there; internal notes
  (``AGENTS.md``), process logs (``process/``, ``report/``), scratch files
  (``temp/``) and local environments (``.venv/``) are never mirrored.
* ``submission/TheCurvedWorld_MidnightAcademy_Submission.zip`` - the archive that
  is sent by mail.  It is built from the mirror, so it never contains the mirror
  itself, the intermediate archive, or any internal file.

Usage::

    .\.venv\Scripts\python.exe scripts/package_submission.py            # mirror + zip
    .\.venv\Scripts\python.exe scripts/package_submission.py --mirror   # mirror only
    .\.venv\Scripts\python.exe scripts/package_submission.py --zip      # zip only
    .\.venv\Scripts\python.exe scripts/package_submission.py --check    # verify only
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIRROR = ROOT / "submission"
ARCHIVE_NAME = "TheCurvedWorld_MidnightAcademy_Submission.zip"

# Generated inside submission/ by this script.  They are kept (never removed by the
# mirror sync) and they are not packed into the archive.
EMAIL_NAME = "SUBMISSION_EMAIL.md"
GENERATED_KEEP = (EMAIL_NAME,)

GUIDE = """# The Curved World

**Team:** `<TEAM_NAME>`  (fill this in before sending the mail)
**Work:** The Curved World - The Midnight Academy
**Repository:** https://github.com/u678868/AI-Empowered-Good-question-Group
**Attachment:** `{archive}` ({size} bytes, {count} files)
**Attachment SHA256:** `{sha256}`
**Attachment MD5:** `{md5}`

## Mail

- To: `seproject@yeah.net`
- Subject: `【<TEAM_NAME> + The Midnight Academy】`
- Body:

```text
{dear}

作品：The Curved World（The Midnight Academy 赛题）
队伍：<TEAM_NAME>
仓库：https://github.com/u678868/AI-Empowered-Good-question-Group
附件：{archive}
附件 SHA256：{sha256}

本作是一款以微分几何为唯一解谜机制的探索游戏：玩家只有一枚只能读到"信号强度"的
探测器，和一张无缝滚动的二维局部切空间地图，必须用 Gauss-Bonnet 角盈角亏、
Bertrand-Diquet-Puisseux 测地圆、Levi-Civita 平行移动和乐、抛物奇异分界线与
同伦大圆周游五种真实几何测量集齐印记，出口探测器才会解封。

包内包含：源代码（src/ web/ tests/，269 项自动化测试全绿）、英文与中文 README、
AI 使用记录（AI_USAGE.md + ai-logs/）、运行截图（screenshots/）与演示材料（demo/）。

运行方式：
  python -m venv .venv
  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
  .\\.venv\\Scripts\\python.exe -m src.main --serve --port 8000
  浏览器打开 http://127.0.0.1:8000/
```
"""


def write_email(archive: Path) -> Path:
    data = archive.read_bytes()
    with zipfile.ZipFile(archive) as bundle:
        count = len([name for name in bundle.namelist() if not name.endswith("/")])
    path = MIRROR / EMAIL_NAME
    path.write_text(
        GUIDE.format(
            archive=archive.name,
            size=f"{len(data):,}",
            count=count,
            sha256=hashlib.sha256(data).hexdigest(),
            md5=hashlib.md5(data).hexdigest(),
            dear="您好：",
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"  cover letter: submission/{EMAIL_NAME}")
    return path

# Top level files that belong in the submission (internal ones are deliberately absent).
MIRROR_FILES = (
    ".gitignore",
    "README.md",
    "README_CN.md",
    "AI_USAGE.md",
    "DEMO_LINK.md",
    "Makefile",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
)

# Directories that belong in the submission.
MIRROR_DIRS = (
    "src",
    "web",
    "tests",
    "docs",
    "ai-logs",
    "scripts",
    "screenshots",
    "demo",
)

# Never copied, even if they appear inside a mirrored directory.
EXCLUDE_DIR_NAMES = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "temp",
    "process",
    "report",
    "submission",
}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".zip", ".log")


def mirrored_files() -> list[Path]:
    """Return the source files of the submission, sorted, relative to the project root."""
    found: list[Path] = []
    for name in MIRROR_FILES:
        path = ROOT / name
        if path.is_file():
            found.append(path)
        else:
            print(f"  [warn] missing file: {name}")
    for name in MIRROR_DIRS:
        base = ROOT / name
        if not base.is_dir():
            print(f"  [skip] missing directory: {name}/")
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if EXCLUDE_DIR_NAMES & set(path.parts):
                continue
            if path.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            found.append(path)
    return sorted(set(found))


def mirror_entries() -> list[Path]:
    """Files under submission/ that belong to the mirror.

    ``submission/.git`` is a nested clone that was used earlier to publish the artifact,
    so it is never walked, never pruned and never packed.
    """
    if not MIRROR.is_dir():
        return []
    return [
        path
        for path in sorted(MIRROR.rglob("*"))
        if path.is_file() and not (EXCLUDE_DIR_NAMES & set(path.relative_to(MIRROR).parts))
    ]


def relative_targets() -> dict[Path, Path]:
    return {path.relative_to(ROOT): path for path in mirrored_files()}


def sync_mirror() -> int:
    targets = relative_targets()
    target_names = {item.as_posix() for item in targets}
    if MIRROR.exists():
        for path in sorted(mirror_entries(), key=lambda item: item.relative_to(MIRROR).as_posix(), reverse=True):
            rel = path.relative_to(MIRROR)
            if rel.as_posix() in target_names or rel.name in (ARCHIVE_NAME, *GENERATED_KEEP):
                continue
            # A stale mirror entry would otherwise be pushed again.
            print(f"  [remove] submission/{rel.as_posix()}")
            path.unlink()
        for path in sorted(MIRROR.rglob("*"), reverse=True):
            if path.is_dir() and not (EXCLUDE_DIR_NAMES & set(path.relative_to(MIRROR).parts)) and not any(path.iterdir()):
                path.rmdir()
    else:
        MIRROR.mkdir(parents=True)

    for rel, source in sorted(targets.items()):
        destination = MIRROR / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    print(f"  mirrored files: {len(targets)}")
    return len(targets)


def build_zip() -> Path:
    archive = MIRROR / ARCHIVE_NAME
    if archive.exists():
        archive.unlink()
    count = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in mirror_entries():
            if path.name in (ARCHIVE_NAME, *GENERATED_KEEP):
                continue
            bundle.write(path, path.relative_to(MIRROR).as_posix())
            count += 1
    print(f"  archived files: {count}")
    return archive


def describe(archive: Path) -> None:
    data = archive.read_bytes()
    print()
    print(f"archive : {archive.relative_to(ROOT).as_posix()}")
    print(f"size    : {len(data):,} bytes ({len(data) / 1024 / 1024:.2f} MiB)")
    print(f"md5     : {hashlib.md5(data).hexdigest()}")
    print(f"sha256  : {hashlib.sha256(data).hexdigest()}")
    print()
    print("package contents (file count per top-level entry):")
    tops: dict[str, int] = {}
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            root = name.split("/")[0]
            tops[root] = tops.get(root, 0) + 1
    for name in sorted(tops):
        print(f"  {name:<30} {tops[name]:>3} file(s)")


def check() -> int:
    targets = relative_targets()
    problems = []
    if not MIRROR.is_dir():
        problems.append("submission/ does not exist yet - run without --check first")
    else:
        for rel in sorted(targets):
            if not (MIRROR / rel).is_file():
                problems.append(f"missing in mirror: {rel.as_posix()}")
        for path in mirror_entries():
            rel = path.relative_to(MIRROR).as_posix()
            if rel in (ARCHIVE_NAME, *GENERATED_KEEP):
                continue
            if rel not in {item.as_posix() for item in targets}:
                problems.append(f"unexpected in mirror: {rel}")
        for name in ("AGENTS.md", "env.txt"):
            if (MIRROR / name).exists():
                problems.append(f"internal file must not be mirrored: {name}")
    for item in problems:
        print(f"  [FAIL] {item}")
    if not problems:
        print(f"  mirror is clean: {len(targets)} files")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the submission mirror and email package.")
    parser.add_argument("--mirror", action="store_true", help="sync submission/ only")
    parser.add_argument("--zip", action="store_true", help="build the zip only")
    parser.add_argument("--check", action="store_true", help="verify the mirror without writing")
    args = parser.parse_args(argv)

    if args.check:
        return check()
    do_mirror = args.mirror or not (args.mirror or args.zip)
    do_zip = args.zip or not (args.mirror or args.zip)

    print("submission mirror")
    if do_mirror:
        sync_mirror()
    else:
        print("  skipped (--zip)")
    print("email package")
    if do_zip:
        archive = build_zip()
        describe(archive)
        print()
        write_email(archive)
    else:
        print("  skipped (--mirror)")
    print()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())