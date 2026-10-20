#!/usr/bin/env python3
"""Point-and-click editor for the photo mappings in foom.toml.

Usage:  python mapper.py [--port 8666] [--no-browser]

Opens a page in your browser: pick a monster, item or the HUD face on the
left, then click a photo from friends/ on the right to assign it. Changes are
written straight to foom.toml (comments and formatting are kept).
"""
import argparse
import io
import json
import re
import subprocess
import sys
import tomllib
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageOps

from build import ITEMS, MONSTERS, ROOT

CONFIG = ROOT / "foom.toml"
FRIENDS = ROOT / "friends"
PLACEHOLDERS = FRIENDS / "placeholders"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
SECTIONS = {"monsters": list(MONSTERS), "items": list(ITEMS), "hud": ["face"]}


# ------------------------------------------------------------- toml editing

def current_mappings():
    cfg = tomllib.loads(CONFIG.read_text())
    result = {}
    for section, keys in SECTIONS.items():
        table = cfg.get(section, {})
        result[section] = []
        for key in keys:
            value = table.get(key)
            photo = value.get("photo") if isinstance(value, dict) else value
            result[section].append({"key": key, "photo": photo, "options": isinstance(value, dict)})
    return result


def set_mapping(section, key, photo):
    """Set section.key to photo (None removes the line) by editing foom.toml text in place."""
    lines = CONFIG.read_text().splitlines(keepends=True)
    header = re.compile(rf"^\s*\[{re.escape(section)}\]\s*$")
    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        if photo is None:
            return
        lines += ["\n" if lines and lines[-1].strip() else "", f"[{section}]\n"]
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))

    entry = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)(.*)$")
    found = next((i for i in range(start + 1, end) if entry.match(lines[i])), None)
    value = json.dumps(photo)  # a JSON string is a valid TOML basic string

    if photo is None:
        if found is not None:
            del lines[found]
    elif found is not None:
        prefix, rest = entry.match(lines[found].rstrip("\n")).groups()
        if rest.lstrip().startswith("{"):
            # Keep crop/background options, swap only the photo
            rest = re.sub(r'photo\s*=\s*"(?:[^"\\]|\\.)*"', lambda _: f"photo = {value}", rest)
            lines[found] = prefix + rest + "\n"
        else:
            lines[found] = prefix + value + "\n"
    else:
        # Insert in the usual asset order, with "=" aligned like its neighbours
        entries = {m.group(1): i for i in range(start + 1, end) if (m := re.match(r"^\s*(\w+)\s*=", lines[i]))}
        later = SECTIONS[section][SECTIONS[section].index(key) + 1:]
        before = next((entries[k] for k in later if k in entries), None)
        if before is None:
            before = max(entries.values(), default=start) + 1
        pad = max((len(lines[i].split("=")[0]) for i in entries.values()), default=len(key) + 1)
        lines.insert(before, f"{key:<{pad - 1}} = {value}\n")

    text = "".join(lines)
    tomllib.loads(text)  # never write a broken config
    CONFIG.write_text(text)


# ------------------------------------------------------------------ photos

def list_photos():
    photos = [p for p in FRIENDS.rglob("*") if p.suffix.lower() in IMAGE_EXTS and p.is_file()]
    rel = lambda p: p.relative_to(ROOT).as_posix()
    friends = sorted(rel(p) for p in photos if PLACEHOLDERS not in p.parents)
    placeholders = sorted(rel(p) for p in photos if PLACEHOLDERS in p.parents)
    return {"friends": friends, "placeholders": placeholders}


_thumbs = {}


def thumbnail(path, size):
    """PNG bytes of a photo thumbnail, or None if path isn't an image inside friends/."""
    file = (ROOT / path).resolve()
    if FRIENDS.resolve() not in file.parents or not file.is_file():
        return None
    cache_key = (file, file.stat().st_mtime, size)
    if cache_key not in _thumbs:
        img = ImageOps.exif_transpose(Image.open(file)).convert("RGBA")
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        _thumbs[cache_key] = buf.getvalue()
    return _thumbs[cache_key]


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, content_type="application/json", status=200):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def state(self):
        return {"mappings": current_mappings(), "photos": list_photos()}

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self.send(PAGE, "text/html; charset=utf-8")
        elif url.path == "/api/state":
            self.send(self.state())
        elif url.path == "/thumb":
            q = parse_qs(url.query)
            data = thumbnail(q.get("path", [""])[0], int(q.get("size", ["160"])[0]))
            if data:
                self.send(data, "image/png")
            else:
                self.send({"error": "not found"}, status=404)
        else:
            self.send({"error": "not found"}, status=404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        try:
            if self.path == "/api/set":
                if body["section"] not in SECTIONS or body["key"] not in SECTIONS[body["section"]]:
                    raise ValueError("unknown asset")
                photo = body.get("photo")
                if photo is not None and photo not in sum(list_photos().values(), []):
                    raise ValueError("unknown photo")
                set_mapping(body["section"], body["key"], photo)
                self.send(self.state())
            elif self.path == "/api/play":
                subprocess.Popen([sys.executable, str(ROOT / "play.py"), "-warp", "1"], cwd=ROOT)
                self.send({"ok": True})
            else:
                self.send({"error": "not found"}, status=404)
        except Exception as e:
            self.send({"error": str(e)}, status=400)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FOOM Mapper</title>
<style>
  :root { --bg:#16161a; --panel:#202026; --line:#33333b; --text:#e8e8ec; --dim:#9a9aa6; --accent:#e5482d; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:14px/1.4 system-ui, sans-serif; height:100vh; display:flex; flex-direction:column; }
  header { display:flex; gap:12px; align-items:center; padding:10px 16px; border-bottom:1px solid var(--line); }
  header h1 { font-size:18px; margin:0 12px 0 0; letter-spacing:2px; color:var(--accent); }
  #status { color:var(--dim); margin-left:auto; }
  button { background:var(--panel); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 12px; cursor:pointer; font:inherit; }
  button:hover { border-color:var(--accent); }
  button.primary { background:var(--accent); border-color:var(--accent); color:white; }
  main { flex:1; display:grid; grid-template-columns:minmax(280px, 380px) 1fr; min-height:0; }
  #assets { overflow-y:auto; border-right:1px solid var(--line); }
  #assets h2, #photos h2 { font-size:12px; text-transform:uppercase; letter-spacing:1px; color:var(--dim); margin:16px 16px 6px; }
  .asset { display:flex; align-items:center; gap:10px; padding:6px 16px; cursor:pointer; border-left:3px solid transparent; }
  .asset:hover { background:var(--panel); }
  .asset.sel { background:var(--panel); border-left-color:var(--accent); }
  .asset img, .asset .none { width:40px; height:40px; object-fit:contain; border-radius:4px; background:#0003; flex:none; }
  .asset .none { display:grid; place-items:center; font-size:10px; color:var(--dim); }
  .asset .name { font-weight:600; }
  .asset .path { color:var(--dim); font-size:12px; word-break:break-all; }
  #right { overflow-y:auto; padding-bottom:24px; }
  #detail { padding:16px; border-bottom:1px solid var(--line); display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  #detail .title { font-size:16px; font-weight:600; margin-right:auto; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(120px, 1fr)); gap:10px; padding:0 16px; }
  .photo { background:var(--panel); border:2px solid transparent; border-radius:8px; padding:6px; cursor:pointer; text-align:center; }
  .photo:hover { border-color:var(--line); }
  .photo.cur { border-color:var(--accent); }
  .photo img { width:100%; height:110px; object-fit:contain; }
  .photo div { font-size:11px; color:var(--dim); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .empty { color:var(--dim); padding:0 16px; }
  @media (max-width:700px) { main { grid-template-columns:1fr; } #assets { max-height:40vh; border-right:0; border-bottom:1px solid var(--line); } }
</style></head>
<body>
<header>
  <h1>FOOM</h1>
  <button id="refresh">Refresh photos</button>
  <button id="play" class="primary">Build &amp; Play</button>
  <span id="status"></span>
</header>
<main>
  <div id="assets"></div>
  <div id="right">
    <div id="detail"></div>
    <h2>Your photos <span style="text-transform:none">(add files to the friends/ folder, then Refresh)</span></h2>
    <div id="friends" class="grid"></div>
    <h2>Placeholders</h2>
    <div id="placeholders" class="grid"></div>
  </div>
</main>
<script>
const LABELS = { monsters: "Monsters", items: "Items", hud: "Status bar" };
let state = null, sel = { section: "monsters", key: "ZombieMan" };
const $ = id => document.getElementById(id);
const thumb = (p, s = 160) => `/thumb?size=${s}&path=${encodeURIComponent(p)}`;
const label = (section, key) => section === "hud" ? "HUD face" : key.replace(/([a-z])([A-Z0-9])/g, "$1 $2");
const status = (msg) => { $("status").textContent = msg; };

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", body: JSON.stringify(body) } : {});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error);
  return data;
}

function current() {
  return state.mappings[sel.section].find(a => a.key === sel.key);
}

function render() {
  const assets = $("assets");
  assets.innerHTML = "";
  for (const [section, list] of Object.entries(state.mappings)) {
    assets.insertAdjacentHTML("beforeend", `<h2>${LABELS[section]}</h2>`);
    for (const a of list) {
      const el = document.createElement("div");
      el.className = "asset" + (section === sel.section && a.key === sel.key ? " sel" : "");
      el.innerHTML = (a.photo ? `<img src="${thumb(a.photo, 80)}">` : `<span class="none">DOOM</span>`) +
        `<div><div class="name">${label(section, a.key)}</div><div class="path">${a.photo || "original sprite"}</div></div>`;
      el.onclick = () => { sel = { section, key: a.key }; render(); };
      assets.append(el);
    }
  }

  const cur = current();
  $("detail").innerHTML = `<span class="title">${label(sel.section, sel.key)}${cur.options ? " <small style='color:var(--dim)'>(has crop/options)</small>" : ""}</span>`;
  const placeholder = state.photos.placeholders.find(p => p.endsWith("/" + (sel.section === "hud" ? "HudFace" : sel.key) + ".png"));
  if (placeholder) $("detail").append(button("Use placeholder", () => assign(placeholder)));
  $("detail").append(button("Use original Doom sprite", () => assign(null)));

  for (const group of ["friends", "placeholders"]) {
    const grid = $(group);
    grid.innerHTML = state.photos[group].length ? "" : `<p class="empty">No photos yet.</p>`;
    for (const p of state.photos[group]) {
      const el = document.createElement("div");
      el.className = "photo" + (cur.photo === p ? " cur" : "");
      el.title = p;
      el.innerHTML = `<img loading="lazy" src="${thumb(p)}"><div>${p.split("/").pop()}</div>`;
      el.onclick = () => assign(p);
      grid.append(el);
    }
  }
}

function button(text, fn) {
  const b = document.createElement("button");
  b.textContent = text;
  b.onclick = fn;
  return b;
}

async function assign(photo) {
  try {
    state = await api("/api/set", { ...sel, photo });
    status(`Saved: ${label(sel.section, sel.key)} → ${photo || "original sprite"}`);
    render();
  } catch (e) { status("Error: " + e.message); }
}

async function load() {
  try { state = await api("/api/state"); render(); }
  catch (e) { status("Error: " + e.message); }
}

$("refresh").onclick = () => load().then(() => status("Photos refreshed"));
$("play").onclick = async () => {
  try { await api("/api/play", {}); status("Building and launching GZDoom…"); }
  catch (e) { status("Error: " + e.message); }
};
load();
</script>
</body></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8666)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    args = parser.parse_args()
    FRIENDS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"FOOM mapper running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
