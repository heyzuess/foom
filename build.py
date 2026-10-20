#!/usr/bin/env python3
"""Build foom.pk3: a GZDoom mod that swaps Doom sprites for photos of your friends.

Usage:  .venv/bin/python build.py [foom.toml]

Every replacement is a "billboard" (rotation 0), so a friend always faces the
player, and is derived from a single photo: pain frames get a red flash, death
frames tip over and flatten, gib frames shrink into a red smear, and so on.
"""
import io
import math
import struct
import sys
import tomllib
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent

# Sprite prefix plus which frame letters play which role. Any frame not listed
# is treated as "walk". Letters come from the IWAD itself, so this only needs
# to classify them.
MONSTERS = {
    "ZombieMan":        dict(sprite="POSS", attack="E", fire="F", pain="G", death="HIJKL", gib="MNOPQRSTU"),
    "ShotgunGuy":       dict(sprite="SPOS", attack="E", fire="F", pain="G", death="HIJKL", gib="MNOPQRSTU"),
    "ChaingunGuy":      dict(sprite="CPOS", attack="E", fire="F", pain="G", death="HIJKLMN", gib="OPQRST"),
    "Imp":              dict(sprite="TROO", attack="EFG", pain="H", death="IJKLM", gib="NOPQRSTU"),
    "Demon":            dict(sprite="SARG", attack="EFG", pain="H", death="IJKLMN"),  # also Spectre
    "LostSoul":         dict(sprite="SKUL", attack="CD", pain="E", death="FGHIJK"),
    "Cacodemon":        dict(sprite="HEAD", attack="BCD", pain="EF", death="GHIJKL"),
    "HellKnight":       dict(sprite="BOS2", attack="EFG", pain="H", death="IJKLMNO"),
    "BaronOfHell":      dict(sprite="BOSS", attack="EFG", pain="H", death="IJKLMNO"),
    "Arachnotron":      dict(sprite="BSPI", attack="G", fire="H", pain="I", death="JKLMNOP"),
    "PainElemental":    dict(sprite="PAIN", attack="DEF", pain="G", death="HIJKLM"),
    "Revenant":         dict(sprite="SKEL", attack="GHIJK", pain="L", death="MNOPQ"),
    "Mancubus":         dict(sprite="FATT", attack="GH", fire="I", pain="J", death="KLMNOPQRST"),
    "Archvile":         dict(sprite="VILE", attack="GHIJKLMNOP", fire="[\\]", pain="Q", death="RSTUVWXYZ"),
    "SpiderMastermind": dict(sprite="SPID", attack="G", fire="H", pain="I", death="JKLMNOPQRS"),
    "Cyberdemon":       dict(sprite="CYBR", attack="E", fire="F", pain="G", death="HIJKLMNOP"),
    "WolfensteinSS":    dict(sprite="SSWV", attack="E", fire="FG", pain="H", death="IJKLM", gib="NOPQRSTUV"),
    "Player":           dict(sprite="PLAY", attack="E", fire="F", pain="G", death="HIJKLMN", gib="OPQRSTUVW"),
}

ITEMS = {
    # health / armor
    "Stimpack": "STIM", "Medikit": "MEDI", "HealthBonus": "BON1", "ArmorBonus": "BON2",
    "GreenArmor": "ARM1", "BlueArmor": "ARM2", "Soulsphere": "SOUL", "Megasphere": "MEGA",
    "Berserk": "PSTR",
    # weapon pickups
    "Chainsaw": "CSAW", "Shotgun": "SHOT", "SuperShotgun": "SGN2", "Chaingun": "MGUN",
    "RocketLauncher": "LAUN", "PlasmaRifle": "PLAS", "BFG9000": "BFUG",
    # ammo
    "Clip": "CLIP", "ClipBox": "AMMO", "Shell": "SHEL", "ShellBox": "SBOX",
    "RocketAmmo": "ROCK", "RocketBox": "BROK", "Cell": "CELL", "CellPack": "CELP", "Backpack": "BPAK",
    # powerups
    "Invulnerability": "PINV", "BlurSphere": "PINS", "RadSuit": "SUIT", "Allmap": "PMAP", "Infrared": "PVIS",
}


# ---------------------------------------------------------------- WAD reading

class Wad:
    """Just enough WAD parsing to list sprite frames and read patch headers."""

    def __init__(self, path):
        self.data = Path(path).read_bytes()
        magic, count, offset = struct.unpack_from("<4sii", self.data, 0)
        if magic not in (b"IWAD", b"PWAD"):
            raise SystemExit(f"{path} is not a WAD file")
        self.lumps = {}
        self.sprites = []
        in_sprites = False
        for i in range(count):
            pos, size, raw = struct.unpack_from("<ii8s", self.data, offset + 16 * i)
            name = raw.rstrip(b"\0").decode("ascii", "replace").upper()
            if name in ("S_START", "SS_START"):
                in_sprites = True
            elif name in ("S_END", "SS_END"):
                in_sprites = False
            elif in_sprites:
                self.sprites.append(name)
            self.lumps.setdefault(name, (pos, size))

    def frames(self, prefix):
        """Frame letters the IWAD defines for a sprite prefix, e.g. 'POSS' -> 'ABC...'."""
        letters = set()
        for name in self.sprites:
            if name.startswith(prefix):
                letters.add(name[4])
                if len(name) >= 8:
                    letters.add(name[6])
        return "".join(sorted(letters))

    def patch_header(self, name):
        """(width, height, left offset, top offset) of a patch lump, or None."""
        if name not in self.lumps:
            return None
        pos, size = self.lumps[name]
        if size < 8:
            return None
        return struct.unpack_from("<hhhh", self.data, pos)

    def sprite_header(self, prefix, frame):
        for name in self.sprites:
            if name.startswith(prefix + frame):
                return self.patch_header(name)
        return None


# ------------------------------------------------------------ photo handling

def load_photo(entry, background):
    if isinstance(entry, str):
        entry = {"photo": entry}
    path = ROOT / entry["photo"]
    if not path.exists():
        raise SystemExit(f"Missing photo: {path}")
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
    if "crop" in entry:
        x, y, w, h = entry["crop"]
        img = img.crop((x, y, x + w, y + h))
    background = entry.get("background", background)
    if background == "remove":
        try:
            from rembg import remove
        except ImportError:
            raise SystemExit("background = 'remove' needs rembg: .venv/bin/pip install rembg")
        img = remove(img)
        bbox = img.getchannel("A").getbbox()
        if bbox:
            img = img.crop(bbox)
    elif background == "oval":
        img = oval_cutout(img)
    return img


def oval_cutout(img):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    inset = max(1, min(w, h) // 40)
    ImageDraw.Draw(mask).ellipse((inset, inset, w - inset, h - inset), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(inset))
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
    return img


def fit(img, max_w, max_h):
    scale = min(max_w / img.width, max_h / img.height)
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def tint(img, rgb, amount):
    alpha = img.getchannel("A")
    solid = Image.new("RGBA", img.size, rgb + (255,))
    out = Image.blend(img, solid, amount)
    out.putalpha(alpha)
    return out


def brighten(img, factor):
    alpha = img.getchannel("A")
    out = ImageEnhance.Brightness(img.convert("RGB")).enhance(factor).convert("RGBA")
    out.putalpha(alpha)
    return out


def on_canvas(img, w, h, dx=0, dy=0):
    """Place img bottom-centred on a transparent w x h canvas."""
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((w - img.width) // 2 + dx, h - img.height + dy))
    return canvas


# ------------------------------------------------------------- frame effects

def monster_frames(face, letters, roles, w, h):
    """Yield (letter, image) for every frame letter of a monster."""
    death, gib = roles.get("death", ""), roles.get("gib", "")
    for i, letter in enumerate(letters):
        if letter in death:
            t = (death.index(letter) + 1) / len(death)
            yield letter, dying(face, t, w, h)
        elif letter in gib:
            t = (gib.index(letter) + 1) / len(gib)
            yield letter, gibbing(face, t, w, h)
        elif letter in roles.get("pain", ""):
            yield letter, on_canvas(tint(face, (255, 0, 0), 0.45), w, h, dx=2)
        elif letter in roles.get("fire", ""):
            yield letter, on_canvas(brighten(fit(face, w * 1.1, h * 1.1), 1.6), w, h)
        elif letter in roles.get("attack", ""):
            yield letter, on_canvas(fit(face, w * 1.08, h * 1.08), w, h)
        else:
            # Walk cycle: a little bob so they don't glide around
            bob = (0, -2, 0, -1)[i % 4] * max(1, h // 56)
            yield letter, on_canvas(face, w, h, dy=bob)


def dying(face, t, w, h):
    """t in (0, 1]: topple over, darken, and flatten into a corpse."""
    img = brighten(face, 1 - 0.45 * t)
    img = img.rotate(-90 * min(1, t * 1.4), expand=True, resample=Image.BICUBIC)
    squash = 1 - 0.6 * t
    img = img.resize((img.width, max(1, round(img.height * squash))), Image.LANCZOS)
    return on_canvas(fit(img, w * 1.4, h), w * 2, h)


def gibbing(face, t, w, h):
    """t in (0, 1]: burst into a shrinking red smear."""
    img = tint(face, (150, 0, 0), 0.3 + 0.6 * t)
    img = img.filter(ImageFilter.GaussianBlur(t * 2))
    img = img.resize((max(1, round(img.width * (1 + t))), max(1, round(img.height * (1 - 0.8 * t)))), Image.LANCZOS)
    return on_canvas(fit(img, w * 1.2, h), w * 2, h)


def item_frames(face, letters, w, h):
    for i, letter in enumerate(letters):
        pulse = 1 + 0.25 * math.sin(i / max(1, len(letters)) * 2 * math.pi)
        yield letter, on_canvas(brighten(face, pulse), w, h)


def hud_faces(face, wad, scale):
    """Status-bar face: STFST<pain><dir>, look left/right, ouch, evil grin, rampage, god, dead."""
    def size_of(name):
        hdr = wad.patch_header(name) or (24, 29, 0, 0)
        return hdr
    for pain in range(5):
        hurt = lambda img: tint(img, (170, 0, 0), 0.12 * pain)
        for name, fx in [
            (f"STFST{pain}0", lambda i: i.transform(i.size, Image.AFFINE, (1, 0, 1, 0, 1, 0))),
            (f"STFST{pain}1", lambda i: i),
            (f"STFST{pain}2", lambda i: i.transform(i.size, Image.AFFINE, (1, 0, -1, 0, 1, 0))),
            (f"STFTL{pain}0", lambda i: i.rotate(12, resample=Image.BICUBIC)),
            (f"STFTR{pain}0", lambda i: i.rotate(-12, resample=Image.BICUBIC)),
            (f"STFOUCH{pain}", lambda i: tint(i, (255, 0, 0), 0.5)),
            (f"STFEVL{pain}", lambda i: brighten(i, 1.35)),
            (f"STFKILL{pain}", lambda i: tint(brighten(i, 1.2), (255, 60, 0), 0.3)),
        ]:
            yield name, size_of(name), fx(hurt(face))
    yield "STFGOD0", size_of("STFGOD0"), tint(brighten(face, 1.3), (255, 210, 0), 0.4)
    yield "STFDEAD0", size_of("STFDEAD0"), tint(ImageOps.grayscale(face.convert("RGB")).convert("RGBA").rotate(90, expand=True), (120, 0, 0), 0.3)


# ---------------------------------------------------------------- pk3 output

class Pk3:
    def __init__(self, scale):
        self.scale = scale
        self.files = {}
        self.textures = []

    def add_sprite(self, name, img, ox, oy):
        self._add("Sprite", name, img, ox, oy)

    def add_graphic(self, name, img, ox, oy):
        self._add("Graphic", name, img, ox, oy)

    def _add(self, kind, name, img, ox, oy):
        """Store a hi-res PNG and a TEXTURES entry that scales it to Doom size."""
        path = f"foomgfx/{kind.lower()}/{name.replace(chr(92), '^').lower()}.png"
        buf = io.BytesIO()
        img.save(buf, "PNG")
        self.files[path] = buf.getvalue()
        quoted = name.replace("\\", "\\\\")
        self.textures.append(
            f'{kind} "{quoted}", {img.width}, {img.height}\n'
            f"{{\n\tXScale {self.scale}\n\tYScale {self.scale}\n\tOffset {ox}, {oy}\n"
            f'\tPatch "{path}", 0, 0\n}}\n'
        )

    def write(self, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("TEXTURES.foom", "\n".join(self.textures))
            for path, data in sorted(self.files.items()):
                z.writestr(path, data)


def main(config="foom.toml"):
    """Build the pk3 described by config and return (pk3 path, iwad path)."""
    cfg = tomllib.loads((ROOT / config).read_text())
    wad = Wad(ROOT / cfg["iwad"])
    scale = cfg.get("scale", 2)
    background = cfg.get("background", "oval")
    pk3 = Pk3(scale)

    for actor, entry in cfg.get("monsters", {}).items():
        if actor not in MONSTERS:
            raise SystemExit(f"Unknown monster '{actor}'. Choose from: {', '.join(MONSTERS)}")
        roles = MONSTERS[actor]
        prefix = roles["sprite"]
        letters = wad.frames(prefix)
        _, oh, _, _ = wad.sprite_header(prefix, "A") or (40, 56, 20, 52)
        face = fit(load_photo(entry, background), oh * scale, oh * scale)
        w, h = face.width, face.height
        for letter, img in monster_frames(face, letters, roles, w, h):
            pk3.add_sprite(f"{prefix}{letter}0", img, img.width // 2, img.height - 2 * scale)
        print(f"  {actor:<17} -> {prefix} ({len(letters)} frames)")

    for item, entry in cfg.get("items", {}).items():
        if item not in ITEMS:
            raise SystemExit(f"Unknown item '{item}'. Choose from: {', '.join(ITEMS)}")
        prefix = ITEMS[item]
        letters = wad.frames(prefix)
        ow, oh, _, _ = wad.sprite_header(prefix, "A") or (20, 20, 10, 18)
        # Items are tiny in Doom; let them be a bit bigger so faces are recognisable
        size = max(ow, oh, 24) * scale * cfg.get("item_size", 1.4)
        face = fit(load_photo(entry, background), size, size)
        for letter, img in item_frames(face, letters, face.width, face.height):
            pk3.add_sprite(f"{prefix}{letter}0", img, img.width // 2, img.height)
        print(f"  {item:<17} -> {prefix}")

    if "face" in cfg.get("hud", {}):
        photo = load_photo(cfg["hud"]["face"], background)
        for name, (w, h, ox, oy), img in hud_faces(photo, wad, scale):
            img = img if img.size == (w * scale, h * scale) else fit(img, w * scale, h * scale)
            pk3.add_graphic(name, on_canvas(img, w * scale, h * scale), ox * scale, oy * scale)
        print("  HUD face         -> STF*")

    out = ROOT / cfg.get("output", "build/foom.pk3")
    pk3.write(out)
    print(f"Wrote {out.relative_to(ROOT)}")
    return out, ROOT / cfg["iwad"]


if __name__ == "__main__":
    main(*sys.argv[1:2])
