"""Build an application for the current Mac architecture; no publishing."""

import platform
import subprocess
import sys
from pathlib import Path

if platform.system() != "Darwin":
    raise SystemExit("macOS application builds must run on macOS")

root = Path(__file__).resolve().parents[1]
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "NeuroSpike",
        "--osx-bundle-identifier",
        "org.neurospike.desktop",
        "--collect-all",
        "pyabf",
        "--copy-metadata",
        "pyabf",
        "--copy-metadata",
        "numpy",
        "--copy-metadata",
        "scipy",
        "--exclude-module",
        "PySide6.QtWebEngineCore",
        "--exclude-module",
        "IPython",
        str(root / "scripts" / "app_entry.py"),
    ],
    cwd=root,
    check=True,
)
executable = root / "dist" / "NeuroSpike.app" / "Contents" / "MacOS" / "NeuroSpike"
subprocess.run([str(executable), "--smoke-test"], cwd=root, check=True)
print("Built and smoke-tested:", executable.parent.parent.parent, platform.machine())
