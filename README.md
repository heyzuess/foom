# FOOM

Doom, but the monsters, pickups and status-bar face are your friends.

`build.py` turns photos into `build/foom.pk3`, a GZDoom mod that replaces the
original sprites. Each friend becomes a billboard that always faces you. From a
single photo it generates walk bob, attack lunge, muzzle-flash glow, red pain
flash, a topple-over death and a gib smear.

## Requirements

- **Python 3.11+** with Pillow
- **GZDoom** (or its fork UZDoom), the engine that runs the mod
- **An IWAD** (the base game data): Freedoom is free; `DOOM2.WAD` / `DOOM.WAD` work if you own Doom

## Install

### macOS

```sh
brew install --cask gzdoom
python3 -m venv .venv
.venv/bin/pip install pillow
```

### Linux

```sh
# GZDoom: Flatpak works on every distro (some distros also package it as "gzdoom")
flatpak install flathub org.zdoom.GZDoom

# Python (Debian/Ubuntu may need: sudo apt install python3-venv)
python3 -m venv .venv
.venv/bin/pip install pillow
```

### Windows (PowerShell)

1. Install Python 3.11+ from [python.org](https://www.python.org/downloads/) or with
   `winget install Python.Python.3.12`.
2. Download GZDoom for Windows from [zdoom.org/downloads](https://zdoom.org/downloads)
   and unzip it to `C:\Program Files\GZDoom\`, or to a `gzdoom\` folder inside this project.
3. Set up Python:
   ```powershell
   py -m venv .venv
   .venv\Scripts\pip install pillow
   ```

`play.py` looks for GZDoom on your `PATH`, in the usual install locations, and
as a Flatpak. If it can't find it, point it at the executable:

```sh
export GZDOOM=/path/to/gzdoom                  # macOS / Linux
$env:GZDOOM = "D:\Games\GZDoom\gzdoom.exe"     # Windows PowerShell
```

### Get an IWAD

Download Freedoom from [freedoom.github.io](https://freedoom.github.io/download.html),
unzip it, and copy `freedoom2.wad` into `iwads/`. If you own Doom, copy `DOOM2.WAD` or
`DOOM.WAD` there instead and change `iwad` in `foom.toml` to match.

## Run

| | Command |
|---|---|
| macOS / Linux | `.venv/bin/python play.py` |
| Windows | `.venv\Scripts\python play.py` |

This rebuilds the mod and launches the game. Any extra arguments go to GZDoom.
For example, `play.py -warp 1 -skill 3` jumps straight to MAP01 on Hurt Me Plenty.

To build the mod without launching the game, run `build.py` the same way. You
can then load `build/foom.pk3` in any GZDoom launcher or drag it onto the
GZDoom executable.

## Adding friends

1. Put photos in `friends/`. Head-and-shoulders shots, cropped close, work best.
2. Map them with the point-and-click mapper:

   | | Command |
   |---|---|
   | macOS / Linux | `.venv/bin/python mapper.py` |
   | Windows | `.venv\Scripts\python mapper.py` |

   This opens a page in your browser:
   - Pick a monster, item or the HUD face on the left.
   - Click a photo on the right to assign it.
   - **Use placeholder** and **Use original Doom sprite** reset the selected asset.
   - **Build & Play** launches the game.

   Changes save straight to `foom.toml`, and comments plus any `crop` options are kept.
   If you add photos while it's open, click **Refresh photos**.

   You can also edit `foom.toml` by hand:
   ```toml
   [monsters]
   Imp = "friends/sam.jpg"
   Cyberdemon = { photo = "friends/boss.jpg", crop = [120, 40, 600, 700] }

   [items]
   Medikit = "friends/mike.jpg"

   [hud]
   face = "friends/me.jpg"
   ```
3. Run `play.py` again.

`foom.toml` starts out mapping every monster and item to a labelled placeholder
in `friends/placeholders/`, so you can tell in-game which sprite is which. Replace
them one at a time with real photos. Run `make_placeholders.py` to regenerate them.

### Background options
- `oval` (default): a soft oval cutout, the classic "face on a stick" look.
- `none`: keeps the full rectangle.
- `remove`: AI background removal for a proper cutout of the person.
  Needs `pip install rembg` in the venv.

## Ideas for next steps
See `notes/notes.txt` under `[future]`.
