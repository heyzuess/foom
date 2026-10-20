#!/usr/bin/env python3
"""Rebuild the mod and launch it in GZDoom on macOS, Linux or Windows.

Usage:  python play.py [gzdoom args...]      e.g. python play.py -warp 1 -skill 3

Set the GZDOOM environment variable to the engine executable if it isn't found.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import build

FLATPAK_ID = "org.zdoom.GZDoom"


def find_engine():
    """Return the command prefix that runs GZDoom, or None."""
    if os.environ.get("GZDOOM"):
        return [os.environ["GZDOOM"]]
    for name in ("gzdoom", "uzdoom"):
        if found := shutil.which(name):
            return [found]
    candidates = [
        Path("/Applications/GZDoom.app/Contents/MacOS/gzdoom"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "GZDoom" / "gzdoom.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "GZDoom" / "gzdoom.exe",
        build.ROOT / "gzdoom" / "gzdoom.exe",
    ]
    for path in candidates:
        if path.is_file():
            return [str(path)]
    if shutil.which("flatpak"):
        installed = subprocess.run(["flatpak", "info", FLATPAK_ID], capture_output=True).returncode == 0
        if installed:
            # The sandbox needs explicit access to this folder to read the WAD and pk3
            return ["flatpak", "run", f"--filesystem={build.ROOT}", FLATPAK_ID]
    return None


def main():
    pk3, iwad = build.main()
    engine = find_engine()
    if not engine:
        sys.exit("GZDoom not found. Install it (see README) or set GZDOOM to the executable's path.")
    sys.exit(subprocess.call(engine + ["-iwad", str(iwad), "-file", str(pk3)] + sys.argv[1:]))


if __name__ == "__main__":
    main()
