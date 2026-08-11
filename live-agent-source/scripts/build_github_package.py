"""Build a GitHub-safe source archive for the livestream analysis Agent."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ZIP = ROOT / "dist" / "live-agent-github-source.zip"
SOURCE_FILES = (
    ".gitignore",
    "agent.py",
    "agent_loop.py",
    "analyzer.py",
    "api.py",
    "COZE_DEPLOY.md",
    "dify_formatter.py",
    "dify_openapi.yaml",
    "DIFY_SETUP.md",
    "evals/real_data_eval.py",
    "GITHUB_UPLOAD.md",
    "history_retriever.py",
    "llm_client.py",
    "models.py",
    "observability.py",
    "rag.py",
    "README.md",
    "requirements.scf.txt",
    "requirements.txt",
    "run.bat",
    "scf_bootstrap",
    "SCF_DEPLOY.md",
    "start.sh",
    "thresholds.py",
    "tools.py",
)
SOURCE_DIRECTORIES = ("config", "knowledge", "prompts", "scripts", "tests")
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".yaml", ".txt", ".sh", ".bat"}
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache"}
SERVER_URL_PATTERN = re.compile(rb"(?m)^(\s*-\s*url:\s*)https://[^\s]+")
EXAMPLE_SERVER_URL = b"https://your-live-agent.example.com"


def _include_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES and not any(
        part in EXCLUDED_PARTS for part in path.parts
    )


def _safe_content(path: Path) -> bytes:
    content = path.read_bytes()
    if path.name == "dify_openapi.yaml":
        return SERVER_URL_PATTERN.sub(lambda match: match.group(1) + EXAMPLE_SERVER_URL, content)
    return content


def main() -> None:
    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    archived = []
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in SOURCE_FILES:
            path = ROOT / name
            if not path.exists():
                raise FileNotFoundError(f"Required source file is missing: {path}")
            archive.writestr(name, _safe_content(path))
            archived.append(name)

        for directory in SOURCE_DIRECTORIES:
            root = ROOT / directory
            for path in sorted(root.rglob("*")):
                if not _include_file(path):
                    continue
                arcname = path.relative_to(ROOT).as_posix()
                archive.writestr(arcname, _safe_content(path))
                archived.append(arcname)

        archive.writestr("output/.gitkeep", "")

    print(f"Created: {OUTPUT_ZIP}")
    print(f"Files: {len(archived) + 1}")
    print(f"Compressed size: {OUTPUT_ZIP.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
