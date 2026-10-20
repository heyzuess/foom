#!/bin/sh
# Rebuild the mod and launch it. Extra args go to GZDoom, e.g. ./play.sh -warp 1 -skill 3
set -e
cd "$(dirname "$0")"
.venv/bin/python build.py
IWAD=$(.venv/bin/python -c "import tomllib; print(tomllib.load(open('foom.toml','rb'))['iwad'])")
exec /Applications/GZDoom.app/Contents/MacOS/gzdoom -iwad "$IWAD" -file build/foom.pk3 "$@"
