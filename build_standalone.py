# Axiom - build_standalone.py
# Copyright (C) 2026 The Axiom Contributors
#
# Build a standalone Axiom Node binary (and optional macOS DMG).
# From project root:  uv run python build_standalone.py

import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

APP_NAME = "AxiomNode"
MAIN_SCRIPT = "node.py"
PROJECT_ROOT = Path(__file__).resolve().parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def have_uv() -> bool:
    return shutil.which("uv") is not None


def get_version() -> str:
    """Read version from pyproject.toml."""
    if not PYPROJECT.exists():
        return "0.2.1-beta.1"
    with open(PYPROJECT, "rb") as f:
        data = tomllib.load(f)
    return data.get("project", {}).get("version", "0.2.1-beta.1")


def check_requirements():
    print("--- [1/5] Checking Requirements ---")
    if have_uv():
        print("Using uv for environment.")
        sync = subprocess.run(
            ["uv", "sync", "--no-dev"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if sync.returncode != 0:
            print(f"Error: uv sync failed:\n{sync.stderr or sync.stdout}")
            sys.exit(1)
    else:
        try:
            import PyInstaller  # noqa: F401
        except ImportError:
            print(
                "Error: PyInstaller not found. Run: pip install pyinstaller",
            )
            print("Or install uv and run from project root: uv sync")
            sys.exit(1)

    if platform.system() == "Darwin":
        if shutil.which("create-dmg") is None:
            print(
                "Warning: 'create-dmg' not found. DMG shortcut will be skipped.",
            )
            print("Fix: brew install create-dmg")


def get_spacy_data():
    """Locates the actual data folder for en_core_web_sm."""
    import en_core_web_sm

    path = os.path.dirname(en_core_web_sm.__file__)
    sep = ";" if os.name == "nt" else ":"

    return f"{path}{sep}en_core_web_sm"


def build_binary():
    print(
        f"--- [2/5] Compiling Binary (Python {platform.python_version()}) ---",
    )

    sep = ";" if os.name == "nt" else ":"
    main_script_path = PROJECT_ROOT / "src" / MAIN_SCRIPT
    if not main_script_path.exists():
        print(f"Error: Entry point not found: {main_script_path}")
        sys.exit(1)

    cmd = [
        *(["uv", "run", "python"] if have_uv() else [sys.executable]),
        "-m",
        "PyInstaller",
        str(main_script_path),
        "--name",
        APP_NAME,
        "--onefile",
        "--clean",
        "--noconfirm",
        "--add-data",
        get_spacy_data(),
        "--hidden-import",
        "spacy",
        "--hidden-import",
        "en_core_web_sm",
        "--hidden-import",
        "flask",
        "--hidden-import",
        "flask_cors",
        "--hidden-import",
        "requests",
        "--hidden-import",
        "feedparser",
        "--hidden-import",
        "trafilatura",
        "--hidden-import",
        "lxml._elementpath",
        "--hidden-import",
        "networkx",
        "--hidden-import",
        "pyvis",
        "--hidden-import",
        "sqlite3",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "matplotlib",
    ]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(
            f"\n\033[91mBuild failed with exit code {result.returncode}\033[0m",
        )
        sys.exit(result.returncode)


def create_dmg():
    """Creates a professional DMG for macOS."""
    if platform.system() != "Darwin" or shutil.which("create-dmg") is None:
        return

    print("--- [3/5] Packaging Professional DMG for macOS ---")
    arch = platform.machine()
    version = get_version()
    dmg_name = f"Axiom_Node_v{version}_{arch}.dmg"
    dist_dir = PROJECT_ROOT / "dist"
    binary_path = dist_dir / APP_NAME
    dmg_path = dist_dir / dmg_name

    if dmg_path.exists():
        dmg_path.unlink()

    staging = dist_dir / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copy(binary_path, staging)

    cmd = [
        "create-dmg",
        "--volname",
        "Axiom Node Installer",
        "--window-size",
        "600",
        "400",
        "--icon-size",
        "100",
        "--icon",
        APP_NAME,
        "150",
        "190",
        "--app-drop-link",
        "450",
        "190",
        "--hide-extension",
        APP_NAME,
        str(dmg_path),
        str(staging),
    ]

    subprocess.run(cmd)
    shutil.rmtree(staging)
    print(
        f"\033[92mSUCCESS: macOS Installer created at dist/{dmg_name}\033[0m",
    )


def create_win_exe_shortcut():
    """Placeholder for creating a Windows-friendly shortcut/installer if needed."""
    if platform.system() == "Windows":
        print(
            "--- [3/5] Windows packaging steps skipped (Inno Setup required for full EXE installer). ---",
        )
    else:
        print(
            "--- [3/5] Platform check: Not macOS, skipping DMG creation. ---",
        )


def cleanup():
    print("--- [4/5] Cleaning Build Artifacts ---")
    build_dir = PROJECT_ROOT / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    spec_file = PROJECT_ROOT / f"{APP_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink()


def main():
    check_requirements()
    build_binary()

    if platform.system() == "Darwin":
        create_dmg()
    elif platform.system() == "Windows":
        create_win_exe_shortcut()

    cleanup()
    print("\n\033[96m[5/5] AXIOM BUILD COMPLETE\033[0m\n")

    exe_path = f"./dist/{APP_NAME}"
    if platform.system() == "Windows":
        exe_path += ".exe"

    print("To run the standalone node:")
    print("   cd dist/")
    print(f"   {exe_path}")


if __name__ == "__main__":
    main()
