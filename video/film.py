"""Desk Buddy demo film: shot list, rendering and compositing.

    python film.py render     # simulate + render Bricki for every shot (headless Chrome)
    python film.py compose    # composite plate + Bricki + graphics, mix audio, encode MP4

Requires the built player served at $PLAYER_URL (pnpm build && pnpm preview --port 4173)
and a 60 fps interpolated plate in WORK/plate60 (see README in this folder).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import graphics as g
from scene import SCENE, Track, desk_z, load_objects, outline, place_points

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("WORK", "/tmp/work/film"))
PLATE60 = Path(os.environ.get("PLATE60", "/tmp/work/plate60"))
FPS = 30
W, H = 1920, 1080
# Inside the plate, away from the warped black borders left by lens undistortion.
SAFE = (26, 18, 934, 522)

OBJECTS = load_objects()
# When the desk map was produced by Gemini 4 Argon (pipeline: desk-buddy perceive), the film says so.
ARGON = OBJECTS.get("source") == "gemini-4-argon"


# ---- plate timing -------------------------------------------------------------------------------

def pingpong(a: float, b: float, start: float, speed: float):
    """Plate time bouncing between a and b; reversing a near-still handheld take reads as one long take."""
    span = b - a

    def f(t: float) -> float:
        x = (start - a) + t * speed
        x = x % (2 * span)
        return a + (x if x <= span else 2 * span - x)

    return f


def linear(a: float, speed: float):
    return lambda t: a + t * speed


WIDE_E = (12.0, 16.75)   # most stable stretch of the take
WIDE_C = (5.9, 7.6)
WIDE_A = (0.95, 2.3)


# ---- shots --------------------------------------------------------------------------------------

@dataclass
class Shot:
    id: str
    dur: float
    plate: object = None                 # callable t -> plate time, or None for graphics-only shots
    sim: dict | None = None              # {start, actions, preroll}
    zoom: object = 2.4                   # float, or [(t, zoom), ...]
    frame_y: float = 0.64                # where Bricki sits vertically in frame
    frame_x: float = 0.5
    fixed: tuple | None = None           # fixed crop center (plate px) instead of following Bricki
    cards: list = field(default_factory=list)
    chips: list = field(default_factory=list)
    titles: list = field(default_factory=list)
    keys: list = field(default_factory=list)
    overlay: str | None = None           # "map", "grid", "laptop", "graph"
    cold_open: bool = False
    dim: float = 0.0                     # darken the plate (for titles)
    blur: float = 0.0
    sfx: list = field(default_factory=list)


def goto(place, run=False):
    return {"kind": "goto", "place": place, "run": run}


def gesture(name, duration, bounce=False):
    return {"kind": "gesture", "gesture": name, "duration": duration, "bounce": bounce}


def card(t0, t1, tier, source, title, line, **kw):
    return {"t0": t0, "t1": t1, "tier": tier, "source": source, "title": title, "line": line, **kw}


NEEDS_ACTIONS = [
    {"t": 0.0, "cmd": [gesture("look", 0.9)]},
    {"t": 1.0, "cmd": [goto("palmRest"), gesture("raise", -1)]},
]
NEEDS_PRESS = 8.6   # sim time the user presses Enter
NEEDS_ACTIONS.append({"t": NEEDS_PRESS, "cmd": [gesture("celebrate", 2.2, True)], "interrupt": True})


def build_shots() -> list[Shot]:
    desk_line = "Gemini 4 Argon maps your desk" if ARGON else "It knows your desk"
    S: list[Shot] = []

    # 1 · Cold open: notifications pile up over a blurred desk.
    S.append(Shot("open", 4.6, plate=pingpong(*WIDE_E, 13.0, 0.4), fixed=(480, 270), zoom=1.06, cold_open=True, blur=9, dim=0.35))
    S.append(Shot("line1", 2.3, titles=[{"t0": 0.15, "t1": 2.3, "text": "Your AI agents never stop asking.", "size": 72}]))
    S.append(Shot("line2", 2.4, titles=[{"t0": 0.15, "t1": 2.4, "text": "What if they had to walk over?", "size": 72, "color": (185, 240, 201)}]))

    # 2 · Meet Bricki, on a real camera push-in.
    S.append(Shot("meet", 5.2, plate=linear(2.45, 0.42), zoom=[(0, 1.5), (5.2, 2.55)], frame_y=0.6,
                  sim={"start": "capSeat", "actions": [{"t": 0.6, "cmd": [gesture("wave", 2.8)]}, {"t": 3.6, "cmd": [gesture("look", 3)]}]},
                  titles=[{"t0": 1.0, "t1": 5.2, "text": "Meet Bricki.", "size": 84, "pos": (W / 2, 190), "sub": "4 cm tall. Lives on your actual desk.", "sub_size": 36}]))

    # 3 · The desk map.
    S.append(Shot("map", 4.6, plate=pingpong(*WIDE_E, 14.2, 0.45), fixed=(482, 300), zoom=1.12, overlay="map", dim=0.12,
                  titles=[{"t0": 0.2, "t1": 4.6, "text": desk_line + ".", "size": 64, "pos": (W / 2, 120),
                           "sub": "Every object becomes something to use.", "sub_size": 32}]))

    # 4 · Object montage — the core: Bricki uses real things.
    S.append(Shot("cup", 7.6, plate=pingpong(*WIDE_E, 12.4, 0.5), zoom=2.5, frame_y=0.62,
                  sim={"start": "capSide", "actions": [{"t": 0.25, "cmd": [goto("cupRim"), gesture("look", 3)]}]},
                  chips=[{"t0": 0.4, "t1": 7.4, "name": "Coffee cup", "verb": "climb it, sit on the rim"}]))
    S.append(Shot("laptop", 4.6, plate=pingpong(*WIDE_C, 6.2, 0.5), zoom=2.7, frame_y=0.6,
                  sim={"start": "edgeFront", "actions": [{"t": 0.35, "cmd": [goto("edgeSeat"), gesture("wave", 2.5)]}]},
                  chips=[{"t0": 0.3, "t1": 4.4, "name": "MacBook", "verb": "a bench"}]))
    S.append(Shot("cap", 4.6, plate=pingpong(*WIDE_A, 1.2, 0.45), zoom=2.7, frame_y=0.6,
                  sim={"start": "capFront", "actions": [{"t": 0.3, "cmd": [goto("capSeat"), gesture("tap", 3)]}]},
                  chips=[{"t0": 0.3, "t1": 4.4, "name": "Bottle cap", "verb": "a stool"}],
                  sfx=[(1.25, "drum")]))
    S.append(Shot("wallet", 4.6, plate=pingpong(*WIDE_E, 15.0, 0.45), zoom=2.6, frame_y=0.62,
                  sim={"start": "walletFront", "actions": [{"t": 0.3, "cmd": [goto("walletTop"), gesture("celebrate", 2.4, True)]}]},
                  chips=[{"t0": 0.3, "t1": 4.4, "name": "Wallet", "verb": "a stage"}]))
    S.append(Shot("bottle", 4.2, plate=pingpong(*WIDE_C, 7.0, 0.45), zoom=2.6, frame_y=0.62,
                  sim={"start": "capFront", "actions": [{"t": 0.2, "cmd": [goto("bottleSide"), gesture("point", 3)]}]},
                  chips=[{"t0": 0.3, "t1": 4.0, "name": "Water bottle", "verb": "a reminder spot"}]))

    # 5 · Agent events: urgency decides where Bricki goes.
    S.append(Shot("fyi", 5.6, plate=pingpong(*WIDE_E, 13.4, 0.45), zoom=2.3, frame_y=0.7,
                  sim={"start": "cupRim", "actions": [{"t": 1.0, "cmd": [gesture("wave", 2.6)]}]},
                  titles=[{"t0": 0.0, "t1": 1.6, "text": "It knows what matters.", "size": 68, "pos": (W / 2, H / 2), "fin": 0.3}],
                  cards=[card(1.0, 5.4, "fyi", "Coding agent", "Build finished. 214 tests passed.", "Done! No rush.")],
                  chips=[{"t0": 1.3, "t1": 5.4, "name": "FYI", "verb": "stays on the cup, waves"}]))
    S.append(Shot("needs1", 3.4, plate=pingpong(*WIDE_C, 6.0, 0.45), zoom=1.9, frame_y=0.66,
                  sim={"start": "edgeSeat", "actions": NEEDS_ACTIONS},
                  cards=[card(0.15, 3.4, "needs_you", "Email agent", "Send the weekly recap to the team?", "Can I go ahead?")],
                  chips=[{"t0": 0.6, "t1": 3.4, "name": "Needs you", "verb": "comes to your hands"}]))
    S.append(Shot("needs2", 7.2, plate=pingpong(*WIDE_E, 14.0, 0.45), zoom=2.35, frame_y=0.74,
                  sim={"start": "edgeSeat", "actions": NEEDS_ACTIONS, "preroll": 3.4},
                  cards=[card(0.0, 7.0, "needs_you", "Email agent", "Send the weekly recap to the team?", "Can I go ahead?",
                              buttons=True, press=NEEDS_PRESS - 3.4, after="Sending it now!")],
                  keys=[{"t0": NEEDS_PRESS - 3.4 - 1.1, "t1": 7.0, "press": NEEDS_PRESS - 3.4}]))
    S.append(Shot("urgent", 6.2, plate=pingpong(*WIDE_E, 12.6, 0.45), zoom=2.2, frame_y=0.7,
                  sim={"start": "palmRest", "actions": [{"t": 0.6, "cmd": [goto("walletTop", True), gesture("wave", 3.4, True)]}]},
                  cards=[card(0.5, 6.0, "urgent", "Calendar", "Standup starts in 1 minute.", "This one can’t wait!")],
                  chips=[{"t0": 0.9, "t1": 6.0, "name": "Urgent", "verb": "runs to the stage"}]))
    S.append(Shot("well", 5.2, plate=pingpong(*WIDE_C, 6.6, 0.45), zoom=2.5, frame_y=0.7,
                  sim={"start": "capSeat", "actions": [{"t": 0.7, "cmd": [goto("bottleSide"), gesture("point", 3)]}]},
                  cards=[card(0.6, 5.0, "wellbeing", "Wellbeing", "No water in 2 hours.", "Water break?")],
                  chips=[{"t0": 1.0, "t1": 5.0, "name": "Wellbeing", "verb": "points at your bottle"}]))

    # 6 · How it works.
    S.append(Shot("tech1", 2.4, plate=pingpong(*WIDE_E, 15.5, 0.5), fixed=(480, 300), zoom=1.12, overlay="grid", dim=0.15,
                  titles=[{"t0": 0.1, "t1": 2.4, "text": "506 tracked camera poses", "size": 58, "pos": (W / 2, 120), "fin": 0.2, "fout": 0.15}]))
    S.append(Shot("tech2", 2.4, plate=pingpong(*WIDE_C, 6.8, 0.5), fixed=(500, 330), zoom=1.45, overlay="laptop", dim=0.15,
                  titles=[{"t0": 0.1, "t1": 2.4, "text": "Metric scale from a 14″ MacBook", "size": 58, "pos": (W / 2, 120), "fin": 0.2, "fout": 0.15}]))
    S.append(Shot("tech3", 2.6, plate=pingpong(*WIDE_E, 13.0, 0.5), fixed=(470, 330), zoom=1.3, overlay="graph", dim=0.18,
                  titles=[{"t0": 0.1, "t1": 2.6, "text": "Objects → places & paths", "size": 58, "pos": (W / 2, 120), "fin": 0.2, "fout": 0.15,
                           "sub": ("Gemini 4 Argon picks where to go" if ARGON else "Urgency picks where to go"), "sub_size": 30}]))

    # 7 · End card.
    S.append(Shot("end", 6.4, plate=pingpong(*WIDE_E, 14.6, 0.4), zoom=[(0, 2.4), (6.4, 1.9)], frame_y=0.72,
                  sim={"start": "cupRim", "actions": [{"t": 0.3, "cmd": [gesture("wave", 3.0)]}]},
                  titles=[{"t0": 1.4, "t1": 6.4, "text": "Desk Buddy", "size": 104, "weight": "Bold", "pos": (W / 2, 250),
                           "sub": "Your AI agents, on your actual desk.", "sub_size": 40, "fout": 0.01},
                          {"t0": 2.4, "t1": 6.4, "text": "Google DeepMind Hackathon  ·  Team pico banana", "size": 28, "weight": "Medium",
                           "color": (210, 225, 215), "pos": (W / 2, H - 80), "fout": 0.01}],
                  dim=0.0))
    return S


# ---- framing ------------------------------------------------------------------------------------

def zoom_at(z, t: float) -> float:
    if isinstance(z, (int, float)):
        return float(z)
    for (t0, z0), (t1, z1) in zip(z, z[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0)
            u = u * u * (3 - 2 * u)
            return z0 + (z1 - z0) * u
    return float(z[-1][1])


def clamp_crop(cx: float, cy: float, w: float) -> dict:
    h = w * 9 / 16
    x0, y0, x1, y1 = SAFE
    w = min(w, x1 - x0)
    h = min(h, y1 - y0)
    x = float(np.clip(cx - w / 2, x0, x1 - w))
    y = float(np.clip(cy - h / 2, y0, y1 - h))
    return {"x": x, "y": y, "width": w, "height": h}


def smooth(series: np.ndarray, sigma_frames: float) -> np.ndarray:
    if sigma_frames <= 0:
        return series
    r = int(sigma_frames * 3)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_frames) ** 2)
    k /= k.sum()
    pad = np.pad(series, ((r, r),) + ((0, 0),) * (series.ndim - 1), mode="edge")
    return np.stack([np.convolve(pad[:, i], k, mode="valid") for i in range(series.shape[1])], 1)


def crops_for(shot: Shot, meta: list | None, n: int) -> list[dict]:
    ts = np.arange(n) / FPS
    if shot.fixed or not meta:
        cx, cy = shot.fixed or (480, 270)
        return [clamp_crop(cx, cy, 960 / zoom_at(shot.zoom, t)) for t in ts]
    pts = np.array([[(m["feet"]["x"] + m["head"]["x"]) / 2, (m["feet"]["y"] + m["head"]["y"]) / 2] for m in meta])
    pts = smooth(pts, FPS * 0.45)
    out = []
    for t, (px, py) in zip(ts, pts):
        w = 960 / zoom_at(shot.zoom, t)
        h = w * 9 / 16
        out.append(clamp_crop(px + (0.5 - shot.frame_x) * w, py + (0.5 - shot.frame_y) * h, w))
    return out


# ---- rendering ----------------------------------------------------------------------------------

def node(*args: str) -> None:
    subprocess.run(["node", str(HERE / "render.mjs"), *args], check=True)


def render_shot(shot: Shot) -> None:
    d = WORK / shot.id
    d.mkdir(parents=True, exist_ok=True)
    n = round(shot.dur * FPS)
    plate_times = [shot.plate(i / FPS) for i in range(n)] if shot.plate else [13.0] * n
    meta = None
    if shot.sim:
        spec = {"start": shot.sim["start"], "fps": FPS, "plateTimes": plate_times,
                "actions": shot.sim["actions"], "preroll": shot.sim.get("preroll", 0)}
        (d / "spec.json").write_text(json.dumps(spec))
        node("simulate", str(d / "spec.json"), str(d / "meta.json"))
        meta = json.loads((d / "meta.json").read_text())
    crops = crops_for(shot, meta, n)
    (d / "crops.json").write_text(json.dumps(crops))
    (d / "plate_times.json").write_text(json.dumps(plate_times))
    if shot.sim:
        node("render", str(d / "spec.json"), str(d / "crops.json"), str(d / "bricki"))


def render_all(only: list[str] | None = None) -> None:
    shots = [s for s in build_shots() if not only or s.id in only]
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(render_shot, shots))


# ---- compositing --------------------------------------------------------------------------------

TRACK = Track()
_rng = np.random.default_rng(7)
GRAIN = [(_rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32)) for _ in range(6)]
yy, xx = np.mgrid[0:H, 0:W]
VIGNETTE = (1 - 0.2 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) ** 1.4).clip(0.7, 1)[..., None].astype(np.float32)
DRINK = np.array([0.448, 0.055])   # bottle with a non-English label, kept out of focus
PLATE_FRAMES = len(os.listdir(PLATE60)) if PLATE60.exists() else 0


def plate_frame(t: float, crop: dict) -> Image.Image:
    i = min(max(int(round(t * 60)), 0), PLATE_FRAMES - 1)
    im =Image.open(PLATE60 / f"{i:05d}.png").convert("RGB")
    box = (crop["x"], crop["y"], crop["x"] + crop["width"], crop["y"] + crop["height"])
    return im.resize((W, H), Image.LANCZOS, box=box)


def to_out(p, crop) -> tuple[float, float]:
    s = W / crop["width"]
    return ((p[0] - crop["x"]) * s, (p[1] - crop["y"]) * s)


def grade(img: Image.Image) -> np.ndarray:
    a = np.asarray(img).astype(np.float32) / 255
    a = a ** 0.96
    a = a + 0.06 * (a - a * a) * 2 - 0.015            # gentle S-curve
    a *= np.array([1.02, 1.0, 0.965], np.float32)     # a touch warmer
    lum = a.mean(2, keepdims=True)
    a = lum + (a - lum) * 1.06
    return a


def blur_label(img: Image.Image, t: float, crop: dict) -> None:
    """Defocus only the printed label band of that bottle, following its silhouette."""
    z0 = desk_z(*DRINK)
    ang = np.linspace(0, 2 * np.pi, 24)
    pts = [(DRINK[0] + 0.03 * math.cos(a), DRINK[1] + 0.03 * math.sin(a), z) for a in ang for z in (z0 + 0.012, z0 + 0.11)]
    out = np.array([to_out(p, crop) for p in TRACK.project(t, pts)])
    x0, y0 = out.min(0)
    x1, y1 = out.max(0)
    if x1 < 0 or x0 > W or y1 < 0 or y0 > H:
        return
    s = W / crop["width"]
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon([tuple(p) for p in _hull(out)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(6 * s))
    blurred = img.filter(ImageFilter.GaussianBlur(9 * s))
    img.paste(blurred, (0, 0), mask)


def _hull(points: np.ndarray) -> list:
    pts = sorted(map(tuple, points))
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def bricki_layer(path: Path) -> Image.Image:
    """Soften the CG slightly and match it to the plate's softness and warmth."""
    im = Image.open(path).convert("RGBA")
    pm = im.convert("RGBa").filter(ImageFilter.GaussianBlur(1.1)).convert("RGBA")
    a = np.asarray(pm).astype(np.float32)
    a[..., :3] *= np.array([1.0, 0.98, 0.94], np.float32)
    lum = a[..., :3].mean(2, keepdims=True)
    a[..., :3] = lum + (a[..., :3] - lum) * 0.9
    return Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA")


def draw_overlay(base: Image.Image, kind: str, t: float, pt: float, crop: dict) -> None:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    proj = lambda pts: np.array([to_out(p, crop) for p in TRACK.project(pt, pts)])
    teal = (126, 224, 192)
    objs = {o["id"]: o for o in OBJECTS["objects"]}
    if kind == "map":
        order = [("laptop", "MacBook", "sit · stand"), ("cup", "Coffee cup", "climb · sit"), ("cap", "Bottle cap", "sit"),
                 ("bottle", "Water bottle", "lean"), ("wallet", "Wallet", "stand")]
        for k, (oid, name, verb) in enumerate(order):
            p = g.ease((t - 0.5 - k * 0.45) / 0.7)
            if p <= 0:
                continue
            for line in outline(objs[oid]):
                g.draw_polyline(d, proj(line), teal + (int(255 * p),), 4, p)
            o = objs[oid]
            top = o.get("top", None)
            z = (o["base"] + o["height"]) if o["shape"] == "cup" else (top if top is not None else desk_z(o["x"], o["y"]) + o["height"])
            lx, ly = proj([(o["x"], o["y"], z)])[0]
            g.label_tag(d, lx, ly - 48, name, verb, g.ease((t - 0.8 - k * 0.45) / 0.4))
    elif kind == "grid":
        p = g.ease(t / 1.4)
        for v in np.arange(-0.2, 0.55, 0.05):
            a = int(150 * p * (1 - abs(v - 0.15) / 0.5))
            if a <= 0:
                continue
            g.draw_polyline(d, proj([(v, y, desk_z(v, y)) for y in np.linspace(-0.12, 0.3, 30)]), teal + (a,), 2, p)
        for v in np.arange(-0.12, 0.32, 0.05):
            a = int(150 * p)
            g.draw_polyline(d, proj([(x, v, desk_z(x, v)) for x in np.linspace(-0.2, 0.5, 40)]), teal + (a,), 2, p)
    elif kind == "laptop":
        p = g.ease(t / 0.9)
        lap = objs["laptop"]
        g.draw_polyline(d, proj(outline(lap)[1]), (255, 210, 120, 255), 5, p)
        a = g.ease((t - 0.7) / 0.4)
        x0, x1 = proj([(0, -0.02, desk_z(0, -0.02)), (lap["width"], -0.02, desk_z(lap["width"], -0.02))])
        d.line([tuple(x0), tuple(x1)], fill=(255, 210, 120, int(255 * a)), width=3)
        m = (x0 + x1) / 2
        g.label_tag(d, m[0], m[1] + 40, "31.26 cm", "known width", a)
    elif kind == "graph":
        places = place_points()
        data = OBJECTS
        pr = {k: proj([v])[0] for k, v in places.items()}
        p = g.ease(t / 1.2)
        for k, (a_, b_, kind_) in enumerate(data["paths"]):
            q = g.ease((t - k * 0.05) / 0.5)
            col = (255, 210, 120) if kind_ in ("hop", "climb") else teal
            g.draw_polyline(d, np.array([pr[a_], pr[b_]]), col + (int(230 * q),), 4, q)
        for k, (pid, (x, y)) in enumerate(pr.items()):
            q = g.ease((t - 0.2 - k * 0.04) / 0.3)
            seat = any(pl["id"] == pid and pl.get("seat") for pl in data["places"])
            r = 9 if seat else 7
            d.ellipse((x - r, y - r, x + r, y + r), fill=((255, 200, 110) if seat else teal) + (int(255 * q),), outline=(255, 255, 255, int(200 * q)), width=2)
        _ = p
    base.alpha_composite(layer)


def cold_open(base: Image.Image, t: float, events: list) -> None:
    items = [("Coding agent", "Build finished"), ("Email agent", "Approve sending the recap?"), ("Calendar", "Standup in 5 minutes"),
             ("Slack", "12 new messages"), ("Coding agent", "3 tests failing"), ("Research agent", "Report ready to review"),
             ("Email agent", "Draft reply needs a look"), ("Calendar", "Room changed"), ("Coding agent", "Need permission to run"),
             ("Slack", "@you in #launch"), ("Finance agent", "Invoice needs approval"), ("Travel agent", "Confirm the hotel?"),
             ("Coding agent", "Deploy paused"), ("Email agent", "5 replies waiting")]
    rng = np.random.default_rng(3)
    times = np.cumsum([0.55] + [max(0.11, 0.42 * 0.82 ** k) for k in range(len(items) - 1)])
    for k, (src, title) in enumerate(items):
        t0 = times[k]
        if t < t0:
            break
        x = W / 2 + rng.uniform(-620, 620) * min(1, k / 3)
        y = 160 + (k * 137) % 760 + rng.uniform(-30, 30)
        a = g.ease((t - t0) / 0.18)
        g.paste_center(base, g.notification_stack_image(k, src, title), x, y + (1 - a) * -40, 0.9 + 0.1 * a, a)
    if not events:
        events.extend(float(x) for x in times)


def compose_shot(shot: Shot, writer, audio_events: list, t_offset: float) -> None:
    d = WORK / shot.id
    n = round(shot.dur * FPS)
    crops = json.loads((d / "crops.json").read_text()) if (d / "crops.json").exists() else None
    pts = json.loads((d / "plate_times.json").read_text()) if (d / "plate_times.json").exists() else None
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else None
    stack_times: list = []
    for i in range(n):
        t = i / FPS
        if shot.plate:
            crop, pt = crops[i], pts[i]
            img = plate_frame(pt, crop)
            blur_label(img, pt, crop)
            if shot.blur:
                img = img.filter(ImageFilter.GaussianBlur(shot.blur))
            rgb = grade(img)
            if shot.dim:
                rgb *= 1 - shot.dim
            frame = Image.fromarray((rgb.clip(0, 1) * 255).astype(np.uint8)).convert("RGBA")
            if shot.sim:
                frame.alpha_composite(bricki_layer(d / "bricki" / f"{i:05d}.png"))
        else:
            frame = Image.new("RGBA", (W, H), (8, 12, 10, 255))
        if shot.overlay:
            draw_overlay(frame, shot.overlay, t, pt, crop)
        if shot.cold_open:
            cold_open(frame, t, stack_times)
        head = None
        if meta:
            head = to_out((meta[i]["head"]["x"], meta[i]["head"]["y"]), crop)
        for c in shot.cards:
            if head:
                g.draw_card(frame, c, t, head)
        for c in shot.chips:
            g.draw_chip(frame, c, t)
        for k in shot.keys:
            g.draw_key(frame, k, t)
        for ti in shot.titles:
            g.draw_title(frame, ti, t)

        # finishing: grain + vignette over everything that is "filmed"
        a = np.asarray(frame.convert("RGB")).astype(np.float32) / 255
        if shot.plate:
            gr = GRAIN[(i + int(t_offset * FPS)) % len(GRAIN)]
            gr = np.repeat(np.repeat(gr, 2, 0), 2, 1)[..., None]
            a = a * VIGNETTE + gr * 0.022
        # shot-level fades: fade from black at film start, to black at the end
        writer.stdin.write((a.clip(0, 1) * 255).astype(np.uint8).tobytes())

    # audio cues
    for c in shot.cards:
        audio_events.append((t_offset + c["t0"], "card_" + c["tier"]))
        if c.get("press") is not None:
            audio_events.append((t_offset + c["press"], "key"))
    for c in shot.chips:
        audio_events.append((t_offset + c["t0"], "chip"))
    for ti in shot.titles:
        audio_events.append((t_offset + ti["t0"], "title"))
    for tt in stack_times:
        audio_events.append((t_offset + tt, "ding"))
    for tt, name in shot.sfx:
        audio_events.append((t_offset + tt, name))
    if meta:
        audio_events.extend((t_offset + tt, name) for tt, name in body_sounds(meta))
    if shot.overlay:
        audio_events.append((t_offset + 0.3, "scan"))


def body_sounds(meta: list) -> list[tuple[float, str]]:
    """Footsteps, landings, grabs and chirps derived from the simulated body."""
    out, last_step = [], -1.0
    for i, m in enumerate(meta):
        t = i / FPS
        if m["gait"] != "still":
            period = 0.15 if m["gait"] == "run" else 0.224
            if t - last_step >= period:
                out.append((t, "step"))
                last_step = t
        if i:
            p = meta[i - 1]
            if p["lift"] > 0.002 and m["lift"] <= 0.0008 and m["lift"] >= 0:
                out.append((t, "land"))
            if m["hang"] and not p["hang"]:
                out.append((t, "grab"))
            if m["gesture"] != p["gesture"] and m["gesture"] in ("wave", "raise", "celebrate", "point", "look"):
                out.append((t, "chirp_" + m["gesture"]))
            if m["gesture"] == "tap" and p["gesture"] != "tap":
                out.append((t, "drumroll"))
    return out


def compose_all(out: Path) -> None:
    shots = build_shots()
    WORK.mkdir(parents=True, exist_ok=True)
    video = WORK / "video_only.mp4"
    writer = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                               "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", str(video)],
                              stdin=subprocess.PIPE)
    events: list = []
    t = 0.0
    marks = []
    for shot in shots:
        print(f"compose {shot.id} @ {t:.1f}s", flush=True)
        marks.append((t, shot.id))
        compose_shot(shot, writer, events, t)
        t += round(shot.dur * FPS) / FPS
    writer.stdin.close()
    writer.wait()
    (WORK / "events.json").write_text(json.dumps({"events": events, "marks": marks, "duration": t}))
    subprocess.run([sys.executable, str(HERE / "audio.py"), str(WORK / "events.json"), str(WORK / "audio.wav")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(WORK / "audio.wav"),
                    "-vf", f"fade=t=in:st=0:d=0.4,fade=t=out:st={t - 1.0:.2f}:d=1.0",
                    "-af", f"afade=t=out:st={t - 1.2:.2f}:d=1.2",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(out)], check=True)
    print("wrote", out)


class _Grab:
    """Stand-in for the encoder that keeps selected frames, for previews."""

    def __init__(self, keep: set[int]):
        self.keep, self.i, self.frames = keep, 0, {}
        self.stdin = self

    def write(self, data: bytes) -> None:
        if self.i in self.keep:
            self.frames[self.i] = Image.frombytes("RGB", (W, H), data)
        self.i += 1


def stills(shot_id: str, times: list[float], out_dir: Path) -> list[Path]:
    shot = next(s for s in build_shots() if s.id == shot_id)
    grab = _Grab({round(t * FPS) for t in times})
    compose_shot(shot, grab, [], 0.0)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, im in sorted(grab.frames.items()):
        p = out_dir / f"{shot_id}_{i:04d}.jpg"
        im.save(p, quality=90)
        paths.append(p)
    return paths


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "render":
        render_all(sys.argv[2:] or None)
    elif cmd == "compose":
        compose_all(Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "DeskBuddy_Demo.mp4")
    else:
        print(__doc__)
