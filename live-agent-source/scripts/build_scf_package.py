"""Build a Tencent Cloud SCF Web Function ZIP with Linux Python 3.9 wheels."""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "dist" / "scf-build"
OUTPUT_ZIP = ROOT / "dist" / "live-agent-scf.zip"
RUNTIME_FILES = (
    "api.py",
    "agent_loop.py",
    "analyzer.py",
    "dify_formatter.py",
    "history_retriever.py",
    "llm_client.py",
    "models.py",
    "observability.py",
    "rag.py",
    "thresholds.py",
    "tools.py",
    "scf_bootstrap",
)
RUNTIME_DIRECTORIES = ("config", "knowledge", "output")


def _copy_runtime_sources() -> None:
    for name in RUNTIME_FILES:
        shutil.copy2(ROOT / name, BUILD_DIR / name)
    for name in RUNTIME_DIRECTORIES:
        source = ROOT / name
        if source.exists():
            shutil.copytree(source, BUILD_DIR / name, dirs_exist_ok=True)


def _install_linux_dependencies() -> None:
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(BUILD_DIR),
        "--platform",
        "manylinux2014_x86_64",
        "--implementation",
        "cp",
        "--python-version",
        "39",
        "--abi",
        "cp39",
        "--only-binary=:all:",
        "-r",
        str(ROOT / "requirements.scf.txt"),
    ]
    subprocess.run(command, check=True)


def _write_zip() -> None:
    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(BUILD_DIR.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            arcname = path.relative_to(BUILD_DIR).as_posix()
            info = zipfile.ZipInfo.from_file(path, arcname)
            if arcname == "scf_bootstrap":
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o755) << 16
            with path.open("rb") as source:
                archive.writestr(info, source.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)
    _copy_runtime_sources()
    _install_linux_dependencies()
    _write_zip()
    size_mb = OUTPUT_ZIP.stat().st_size / 1024 / 1024
    print(f"Created: {OUTPUT_ZIP}")
    print(f"Compressed size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
