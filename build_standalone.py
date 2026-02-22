# Axiom - build_standalone.py
# Copyright (C) 2026 The Axiom Contributors

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
            print("Warning: 'create-dmg' not found. DMG shortcut will be skipped.")
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
    
    sep = ";" if os.name == "nt" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        MAIN_SCRIPT,
        "--name", APP_NAME,
        "--onefile",
        "--clean",
        "--noconfirm",
        "--add-data", get_spacy_data(),
        "--hidden-import", "spacy",
        "--hidden-import", "en_core_web_sm",
        "--hidden-import", "flask",
        "--hidden-import", "flask_cors",
        "--hidden-import", "requests",
        "--hidden-import", "feedparser",
        "--hidden-import", "trafilatura",
        "--hidden-import", "lxml._elementpath",
        "--hidden-import", "networkx",
        "--hidden-import", "pyvis",
        "--hidden-import", "sqlite3",
        "--exclude-module", "tkinter", 
        "--exclude-module", "matplotlib"
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n\033[91mBuild failed with exit code {result.returncode}\033[0m")
        sys.exit(result.returncode)

def create_dmg():
    """Creates a professional DMG for macOS."""
    if platform.system() != "Darwin" or shutil.which("create-dmg") is None:
        return

    print("--- [3/5] Packaging Professional DMG for macOS ---")
    arch = platform.machine()
    dmg_name = f"Axiom_Node_v0.2.0_{arch}.dmg"
    dist_dir = os.path.join(os.getcwd(), "dist")
    binary_path = os.path.join(dist_dir, APP_NAME)
    dmg_path = os.path.join(dist_dir, dmg_name)

    if os.path.exists(dmg_path): os.remove(dmg_path)

    staging = os.path.join(dist_dir, "staging")
    if os.path.exists(staging): shutil.rmtree(staging)
    os.makedirs(staging)
    shutil.copy(binary_path, staging)

    cmd = [
        "create-dmg",
        "--volname", f"Axiom Node Installer",
        "--window-size", "600", "400",
        "--icon-size", "100",
        "--icon", APP_NAME, "150", "190",
        "--app-drop-link", "450", "190",
        "--hide-extension", APP_NAME,
        dmg_path,
        staging
    ]
    
    subprocess.run(cmd)
    shutil.rmtree(staging)
    print(f"\033[92mSUCCESS: macOS Installer created at dist/{dmg_name}\033[0m")

def create_win_exe_shortcut():
    """Placeholder for creating a Windows-friendly shortcut/installer if needed."""
    if platform.system() == "Windows":
        print("--- [3/5] Windows packaging steps skipped (Inno Setup required for full EXE installer). ---")
    else:
        print("--- [3/5] Platform check: Not macOS, skipping DMG creation. ---")


def cleanup():
    print("--- [4/5] Cleaning Build Artifacts ---")
    if os.path.exists("build"): shutil.rmtree("build")
    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file): os.remove(spec_file)

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
    
    print(f"To run the standalone node:")
    print(f"   cd dist/")
    print(f"   .{os.path.sep}{APP_NAME}")

if __name__ == "__main__":
    main()