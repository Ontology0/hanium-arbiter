#!/usr/bin/env python3
"""Build auditable download archives from explicit public source allowlists.

Only Python's standard library is required. This does not publish a release,
contact a model, or include runtime databases, credentials, reports, or images.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "README.md", "LICENSE", "pyproject.toml", "uv.lock", "Dockerfile", "railway.json",
    ".dockerignore", ".railwayignore", ".gitignore", "slack-app-manifest.json",
    "start-macos.sh", "start-windows.ps1", "scripts/package_downloads.py",
)
FRONTEND_FILES = (
    "frontend/index.html", "frontend/landing.html", "frontend/app.js",
    "frontend/styles.css", "frontend/landing.css", "frontend/download.html",
    "frontend/download.js", "frontend/downloads.html", "frontend/downloads.js",
)
DOCUMENT_FILES = ("docs/install.md", "docs/railway-deployment.md")
INTEGRATION_FILES = ("integrations/openclaw/openclaw.skills.example.json",
                     "integrations/openclaw/openclaw.mcp.example.json")
REQUIRED_FILES = (
    "README.md", "LICENSE", "pyproject.toml", "uv.lock", "backend/arbiter/app.py",
    "frontend/index.html", "frontend/app.js", "frontend/styles.css", "start-macos.sh",
    "start-windows.ps1", "docs/install.md", "skills/arbiter-coordination/SKILL.md",
    "skills/arbiter-coordination/scripts/arbiter_client.py",
)
FORBIDDEN_PARTS = {".runtime", ".git", ".venv", "__pycache__", "node_modules", "assets", "video", "videos", "diagrams", "screenshots", "submission", "templates", "downloads"}
ALLOWED_SKILL_SUFFIXES = {".md", ".py", ".json", ".toml", ".yaml", ".yml", ".txt"}
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def checked_file(path: Path) -> Path:
    relative = path.relative_to(ROOT)
    if (any(part in FORBIDDEN_PARTS for part in relative.parts)
            or any(part.startswith(".env") for part in relative.parts)
            or path.suffix.lower() in {".zip", ".sqlite", ".sqlite3", ".db", ".pyc", ".docx", ".pdf", ".png", ".jpg", ".svg", ".mp4"}):
        raise ValueError(f"Non-public asset rejected: {relative}")
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != ROOT and ROOT in parent.parents):
        raise ValueError(f"Symbolic links are not packaged: {relative}")
    if not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f"Source outside package root: {relative}")
    return path


def skill_files() -> list[Path]:
    directory = ROOT / "skills" / "arbiter-coordination"
    return sorted(checked_file(path) for path in directory.rglob("*")
                  if path.is_file() and path.suffix.lower() in ALLOWED_SKILL_SUFFIXES
                  and "__pycache__" not in path.parts)


def source_files() -> list[Path]:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            raise FileNotFoundError(f"Required source file missing: {relative}")
    paths = {ROOT / relative for relative in (*ROOT_FILES, *FRONTEND_FILES, *DOCUMENT_FILES)
             if (ROOT / relative).is_file()}
    paths.update((ROOT / "backend").rglob("*.py"))
    paths.update((ROOT / "tests").rglob("*.py"))
    paths.update((ROOT / "docs").glob("*-connection.md"))
    paths.update(skill_files())
    # Only named reviewed templates, never a user's other integration settings.
    paths.update(ROOT / relative for relative in INTEGRATION_FILES if (ROOT / relative).is_file())
    paths.update(ROOT / relative for relative in ("experiments/run_comparison.py", "experiments/README.md")
                 if (ROOT / relative).is_file())
    # These two directories contain reviewed public controlled/synthetic data.
    # New experiment directories are intentionally not included automatically.
    for name in ("latest", "briefing-smoke"):
        directory = ROOT / "experiments" / "results" / name
        paths.update(path for path in directory.rglob("*") if path.is_file()
                     and path.suffix.lower() in {".json", ".csv", ".md"})
    return sorted(checked_file(path) for path in paths)


def build_archive(target: Path, files: list[Path], *, archive_root: str, base: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    records = []
    descriptor, temporary = tempfile.mkstemp(prefix=target.stem + "-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path in files:
                    payload = path.read_bytes()
                    relative = Path("LICENSE") if path == ROOT / "LICENSE" else path.relative_to(base)
                    name = archive_root + "/" + relative.as_posix()
                    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    mode = 0o755 if path.name == "start-macos.sh" else 0o644
                    info.external_attr = (stat.S_IFREG | mode) << 16
                    archive.writestr(info, payload)
                    records.append({"source": path.relative_to(ROOT).as_posix(), "archive_path": name,
                                    "bytes": len(payload), "sha256": sha256(payload).hexdigest()})
        with zipfile.ZipFile(temporary) as archive:
            corrupted = archive.testzip()
            if corrupted:
                raise ValueError(f"Archive integrity check failed: {corrupted}")
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise ValueError("Duplicate archive paths")
        os.replace(temporary, target)
        target.chmod(0o644)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"file": target.relative_to(ROOT).as_posix(), "archive_root": archive_root,
            "bytes": target.stat().st_size, "sha256": sha256(target.read_bytes()).hexdigest(),
            "file_count": len(records), "files": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-only", action="store_true", help="Print allowed files without writing archives")
    args = parser.parse_args()
    sources, skill = source_files(), [checked_file(ROOT / "LICENSE"), *skill_files()]
    if args.list_only:
        print(json.dumps({"source": [str(p.relative_to(ROOT)) for p in sources],
                          "skill": [str(p.relative_to(ROOT)) for p in skill]}, ensure_ascii=False, indent=2))
        return
    output = ROOT / "frontend" / "downloads"
    archives = [build_archive(output / "culture-fit-source.zip", sources, archive_root="culture-fit", base=ROOT),
                build_archive(output / "culture-fit-skill.zip", skill, archive_root="arbiter-coordination",
                              base=ROOT / "skills" / "arbiter-coordination")]
    manifest = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "policy": "Explicit public-source allowlist; excludes runtime state, credentials, reports, video, images, logos and nested downloads.",
                "archives": archives}
    manifest_path = ROOT / ".runtime" / "download-package-manifest.json"
    manifest_path.parent.mkdir(exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archives": [{key: value for key, value in archive.items() if key != "files"}
                                   for archive in archives],
                      "manifest": str(manifest_path.relative_to(ROOT))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
