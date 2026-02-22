#!/usr/bin/env python3
"""
Axiom Engine - Build System V0.1.0 (Hardened for Python 3.13)
Generates standalone executables and professional macOS DMG installers.

FEATURES:
- Drag-to-Applications: Professional macOS installation.
- Web UI Bundling: Includes index.html for mobile/web terminal access.
- Hardened for Python 3.13: Fixes lxml segfaults.
"""

import os
import sys
import shutil
import subprocess
import platform

APP_NAME = "AxiomNode"
MAIN_SCRIPT = "node.py"

def check_requirements():
    print("--- [1/5] Checking Requirements ---")
    try:
        import PyInstaller
    except ImportError:
        print("Error: PyInstaller not found. Run: pip install pyinstaller")
        sys.exit(1)

    if platform.system() == "Darwin":
        if shutil.which("create-dmg") is None:
            print("Warning: 'create-dmg' not found. DMG will be missing Application shortcut.")
            print("Fix: brew install create-dmg")

def get_spacy_data():
    """Locates the actual data folder for en_core_web_sm."""
    import en_core_web_sm
    path = os.path.dirname(en_core_web_sm.__file__)
    sep = ";" if os.name == "nt" else ":"
    
    subfolders = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f)) and f.startswith("en_core_web_sm")]
    if subfolders:
        actual_data_path = os.path.join(path, subfolders[0])
        return f"{actual_data_path}{sep}en_core_web_sm"
    
    return f"{path}{sep}en_core_web_sm"

def build_binary():
    print(f"--- [2/5] Compiling Binary (Python {platform.python_version()}) ---")
    
    # Separator for --add-data
    sep = ";" if os.name == "nt" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        MAIN_SCRIPT,
        "--name", APP_NAME,
        "--onefile",
        "--clean",
        "--noconfirm",
        # 1. Bundle SpaCy AI Model
        "--add-data", get_spacy_data(),
        # 2. Bundle Web Interface (Critical for node.py @app.route('/'))
        "--add-data", f"index.html{sep}.",
        
        # Manually specify hidden imports to avoid the crashing crawler
        "--hidden-import", "spacy",
        "--hidden-import", "en_core_web_sm",
        "--hidden-import", "flask",
        "--hidden-import", "flask_cors", # NEW
        "--hidden-import", "requests",
        "--hidden-import", "feedparser",
        "--hidden-import", "trafilatura",
        "--hidden-import", "lxml._elementpath",
        "--hidden-import", "networkx",
        "--hidden-import", "pyvis",
        "--hidden-import", "sqlite3",
        
        # Exclude heavy but unused modules
        "--exclude-module", "tkinter", 
        "--exclude-module", "matplotlib"
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n\033[91mBuild failed with exit code {result.returncode}\033[0m")
        sys.exit(result.returncode)

def create_dmg():
    """Creates a professional DMG with 'Drag to Applications' shortcut."""
    if platform.system() != "Darwin" or shutil.which("create-dmg") is None:
        return

    print("--- [3/5] Packaging Professional DMG for macOS ---")
    arch = platform.machine()
    dmg_name = f"Axiom_Node_v0.1.0_{arch}.dmg"
    dist_dir = os.path.join(os.getcwd(), "dist")
    binary_path = os.path.join(dist_dir, APP_NAME)
    dmg_path = os.path.join(dist_dir, dmg_name)

    if os.path.exists(dmg_path):
        os.remove(dmg_path)

    # Temporary staging folder
    staging = os.path.join(dist_dir, "staging")
    if os.path.exists(staging): shutil.rmtree(staging)
    os.makedirs(staging)
    shutil.copy(binary_path, staging)

    # DMG Command with Application Shortcut
    cmd = [
        "create-dmg",
        "--volname", f"Axiom Node Installer",
        "--window-size", "600", "400",
        "--icon-size", "100",
        "--icon", APP_NAME, "150", "190",
        "--app-drop-link", "450", "190", # THE DRAG-TO-APPLICATIONS MAGIC
        "--hide-extension", APP_NAME,
        dmg_path,
        staging
    ]
    
    subprocess.run(cmd)
    shutil.rmtree(staging)
    print(f"\033[92mSUCCESS: Installer created at dist/{dmg_name}\033[0m")

def cleanup():
    print("--- [4/5] Cleaning Build Artifacts ---")
    for folder in ["build"]:
        if os.path.exists(folder): shutil.rmtree(folder)
    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file): os.remove(spec_file)

if __name__ == "__main__":
    check_requirements()
    build_binary()
    create_dmg()
    cleanup()
    print("\n\033[96m[5/5] AXIOM BUILD COMPLETE\033[0m\n")