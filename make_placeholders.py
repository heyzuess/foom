#!/usr/bin/env python3
"""Generate a labelled placeholder image for every monster, item and the HUD face.

Usage:  .venv/bin/python make_placeholders.py

Writes friends/placeholders/<Name>.png. Monsters are colour-coded faces and
items are labelled boxes, so it's obvious in-game which sprite is which.
"""
import colorsys
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from build import ITEMS, MONSTERS, ROOT

OUT = ROOT / "friends" / "placeholders"


def colour(i, n, sat=0.65, val=0.9):
    r, g, b = colorsys.hsv_to_rgb(i / n, sat, val)
    return round(r * 255), round(g * 255), round(b * 255)


# Long single words shrink to unreadable sizes, so split them up
LABELS = {
    "Arachnotron": "ARACH NOTRON", "Cacodemon": "CACO DEMON", "Cyberdemon": "CYBER DEMON",
    "WolfensteinSS": "WOLF SS", "Invulnerability": "INVUL NERABLE", "Soulsphere": "SOUL SPHERE",
    "Megasphere": "MEGA SPHERE", "BFG9000": "BFG 9000",
}


def label_lines(name):
    """'SpiderMastermind' -> ['SPIDER', 'MASTERMIND']"""
    if name in LABELS:
        return LABELS[name].split()
    return [w.upper() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|\d+", name)]


def draw_label(draw, name, box, fill):
    """Draw the name as large as fits inside box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    lines = label_lines(name)
    for size in range(120, 10, -4):
        font = ImageFont.load_default(size)
        widths = [draw.textlength(line, font=font) for line in lines]
        height = size * 1.1 * len(lines)
        if max(widths) <= x1 - x0 and height <= y1 - y0:
            break
    y = y0 + ((y1 - y0) - height) / 2
    for line, w in zip(lines, widths):
        draw.text((x0 + ((x1 - x0) - w) / 2, y), line, font=font, fill=fill,
                  stroke_width=max(2, size // 12), stroke_fill="black")
        y += size * 1.1


def monster(name, rgb):
    img = Image.new("RGB", (400, 500), (30, 30, 30))
    d = ImageDraw.Draw(img)
    d.ellipse((40, 30, 360, 470), fill=rgb, outline="black", width=8)
    # Angry eyes and a frown
    d.ellipse((115, 120, 175, 180), fill="white")
    d.ellipse((225, 120, 285, 180), fill="white")
    d.ellipse((132, 137, 158, 163), fill="black")
    d.ellipse((242, 137, 268, 163), fill="black")
    d.line((105, 105, 180, 130), fill="black", width=12)
    d.line((295, 105, 220, 130), fill="black", width=12)
    d.arc((140, 200, 260, 270), 200, 340, fill="black", width=10)
    draw_label(d, name, (85, 285, 315, 420), "white")
    return img


def item(name, rgb):
    img = Image.new("RGB", (400, 400), (30, 30, 30))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, 360, 360), radius=50, fill=rgb, outline="white", width=10)
    draw_label(d, name, (85, 90, 315, 310), "white")
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(MONSTERS):
        monster(name, colour(i, len(MONSTERS))).save(OUT / f"{name}.png")
    for i, name in enumerate(ITEMS):
        item(name, colour(i, len(ITEMS), sat=0.8, val=0.6)).save(OUT / f"{name}.png")
    monster("You", (230, 190, 150)).save(OUT / "HudFace.png")
    print(f"Wrote {len(MONSTERS) + len(ITEMS) + 1} placeholders to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
