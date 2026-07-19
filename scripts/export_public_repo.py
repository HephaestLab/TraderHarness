"""Export a secret-scanned, clean-history public repository tree."""

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = [
    ".dockerignore",
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "README_en.md",
    "SECURITY.md",
    "compose.yml",
    "llms-full.txt",
    "llms.txt",
    "mkdocs.yml",
    "pyproject.toml",
]
DIRECTORIES = [".github", "docs", "examples", "pixel-office", "tests", "traderharness", "webui"]
PUBLIC_SCRIPTS = [
    "audit_entity_leakage.py",
    "build_entity_templates.py",
    "build_hf_release.py",
    "build_llms_full.py",
    "build_readme_gif.py",
    "build_social_preview.py",
    "clean_announcements_a_share.py",
    "data_doctor.py",
    "generate_pixel_office_assets.py",
    "update_hf_card.py",
    "upload_hf_release.py",
]
EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "test-results",
    "playwright-report",
    "demo-frames",
    "market_data",
}
EXCLUDED_FILES = {"v0.1.0-plan.md", "pixel-trader-scene.md"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".parquet", ".rar", ".zip", ".tsbuildinfo", ".docx"}
EXCLUDED_PREFIXES = ("_tmp_",)
SECRET_PATTERNS = [
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"hf_[A-Za-z0-9]{20,}"),
    re.compile(rb"sk-[A-Za-z0-9]{20,}"),
]


def excluded(path: Path) -> bool:
    return (
        bool(EXCLUDED_PARTS.intersection(path.parts))
        or path.name in EXCLUDED_FILES
        or path.suffix.lower() in EXCLUDED_SUFFIXES
        or path.name.startswith(EXCLUDED_PREFIXES)
    )


def copy_tree(source: Path, target: Path) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if excluded(relative):
            continue
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def scan_secrets(target: Path) -> None:
    findings = []
    for path in target.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        payload = path.read_bytes()
        if any(pattern.search(payload) for pattern in SECRET_PATTERNS):
            findings.append(path.relative_to(target).as_posix())
    if findings:
        raise RuntimeError(f"Potential credentials in public export: {', '.join(findings)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    target = args.target.resolve()
    if ROOT == target or ROOT in target.parents:
        raise SystemExit("Target must be outside the private workspace")
    target.mkdir(parents=True, exist_ok=True)
    for path in target.iterdir():
        if path.name == ".git":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    for filename in ROOT_FILES:
        shutil.copy2(ROOT / filename, target / filename)
    for directory in DIRECTORIES:
        copy_tree(ROOT / directory, target / directory)
    scripts_target = target / "scripts"
    scripts_target.mkdir()
    for filename in PUBLIC_SCRIPTS:
        shutil.copy2(ROOT / "scripts" / filename, scripts_target / filename)

    scan_secrets(target)
    files = [path for path in target.rglob("*") if path.is_file() and ".git" not in path.parts]
    print(f"Exported {len(files)} files ({sum(path.stat().st_size for path in files):,} bytes) to {target}")


if __name__ == "__main__":
    main()
