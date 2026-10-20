# FOOM

Doom, but the monsters, pickups and status-bar face are your friends.

`build.py` turns photos into `build/foom.pk3`, a GZDoom mod that replaces the
original sprites. Each friend becomes a billboard that always faces you. From a
single photo it generates walk bob, attack lunge, muzzle-flash glow, red pain
flash, a topple-over death and a gib smear.

## Setup (once)

```sh
brew install --cask gzdoom
python3 -m venv .venv && .venv/bin/pip install pillow
```

`iwads/freedoom2.wad` is Freedoom, a free stand-in for Doom II. If you own
Doom, drop `DOOM2.WAD` or `DOOM.WAD` into `iwads/` and point `iwad` in
`foom.toml` at it.

## Adding friends

1. Put photos in `friends/`. Head-and-shoulders shots, cropped close, work best.
2. Map them in `foom.toml`:
   ```toml
   [monsters]
   Imp = "friends/sam.jpg"
   Cyberdemon = { photo = "friends/boss.jpg", crop = [120, 40, 600, 700] }

   [items]
   Medikit = "friends/mike.jpg"

   [hud]
   face = "friends/me.jpg"
   ```
3. `./play.sh` rebuilds and launches. Use `./play.sh -warp 1` to jump straight to MAP01.

`foom.toml` lists every monster and item name you can use.

### Background options
- `oval` (default): a soft oval cutout, the classic "face on a stick" look.
- `none`: keeps the full rectangle.
- `remove`: AI background removal for a proper cutout of the person.
  Needs `.venv/bin/pip install rembg`.

## Ideas for next steps
- First-person weapon sprites (`PISG`, `SHTG`, ...), e.g. a friend holding the gun
- Sounds: friends' voices for pain, death and sight lines (`sounds/` + `SNDINFO`)
- Custom intro, title screen and level names
