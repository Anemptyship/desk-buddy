"""Desk perception with Gemini 4 Argon.

Argon looks at a few frames of the desk take and returns the objects a 4 cm character
could use, with image points for each object's footprint and what it affords
(climb, sit, stand, lean). Points are raycast onto the fitted desk plane with the
tracked cameras and averaged across frames, then turned into the place graph the
player walks on (player/public/scene/objects.json).

    desk-buddy perceive [--scene player/public/scene] [--times 1.5 6.5 13 15.5]

Needs GEMINI_API_KEY. The raw Argon response is saved next to the output so every
object in the map can be traced back to what the model actually said.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import numpy as np

MODEL = os.environ.get("ARGON_MODEL", "gemini-4-argon")
KINDS = ["cup", "bottle_cap", "wallet", "water_bottle", "laptop", "phone", "book", "other"]
AFFORDS = ["climb", "sit", "stand", "lean", "avoid"]

PROMPT = """These are {n} frames of the same real desk, filmed with a moving phone.
A 4 cm tall toy character will live on this desk and use the objects on it.

List every object on the desk surface the character could interact with (ignore the background and other desks).
For each object give:
- id: short lowercase id (use the kind name, add a number only if there are several)
- kind: one of {kinds}
- label: short English name
- footprint: for EACH frame index where it is visible, the image point at the CENTER OF ITS FOOTPRINT on the desk,
  as [y, x] normalized to 0-1000
- size_cm: {{"width": ..., "depth": ..., "height": ...}} best physical estimate (cylinders: width = depth = diameter)
- rotation_deg: rotation of the footprint around the vertical axis relative to the laptop's front edge (boxes only, else 0)
- affordances: which of {affords} make sense for a 4 cm character (a tall cup: climb; a low lid or cap: sit;
  a flat item 0.5-2 cm high: stand; a tall bottle: lean; anything fragile or dangerous: avoid)
- why: one short sentence

The laptop is already calibrated; include it with kind "laptop" but its size is known."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "objects": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "kind": {"type": "STRING", "enum": KINDS},
                    "label": {"type": "STRING"},
                    "footprint": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                        "frame": {"type": "INTEGER"}, "point": {"type": "ARRAY", "items": {"type": "NUMBER"}}},
                        "required": ["frame", "point"]}},
                    "size_cm": {"type": "OBJECT", "properties": {"width": {"type": "NUMBER"}, "depth": {"type": "NUMBER"}, "height": {"type": "NUMBER"}},
                                "required": ["width", "depth", "height"]},
                    "rotation_deg": {"type": "NUMBER"},
                    "affordances": {"type": "ARRAY", "items": {"type": "STRING", "enum": AFFORDS}},
                    "why": {"type": "STRING"},
                },
                "required": ["id", "kind", "label", "footprint", "size_cm", "affordances"],
            },
        }
    },
    "required": ["objects"],
}


def _frames(video: Path, times: list[float], out: Path) -> list[Path]:
    paths = []
    for i, t in enumerate(times):
        p = out / f"frame_{i}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(p)], check=True)
        paths.append(p)
    return paths


def ask_argon(images: list[Path], key: str) -> dict:
    parts = [{"text": PROMPT.format(n=len(images), kinds=KINDS, affords=AFFORDS)}]
    for i, p in enumerate(images):
        parts += [{"text": f"Frame index {i}:"}, {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(p.read_bytes()).decode()}}]
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "thinkingConfig": {"thinkingLevel": "high"}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
                                 data=json.dumps(body).encode(), headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


class Cameras:
    def __init__(self, path: Path, plane: tuple[np.ndarray, float]):
        self.frames = json.loads(path.read_text())["frames"]
        self.normal, self.offset = plane

    def ray_to_desk(self, t: float, u: float, v: float) -> np.ndarray:
        f = min(self.frames, key=lambda f: abs(f["t"] - t))
        K, c2w = np.array(f["K"]), np.array(f["c2w"])
        d = c2w[:3, :3] @ np.linalg.inv(K) @ np.array([u, v, 1.0])
        o = c2w[:3, 3]
        s = -(self.normal @ o + self.offset) / (self.normal @ d)
        return o + s * d


def desk_z(normal: np.ndarray, offset: float, x: float, y: float) -> float:
    return float(-(normal[0] * x + normal[1] * y + offset) / normal[2])


def build_map(argon: list[dict], cams: Cameras, times: list[float], size: tuple[int, int], normal, offset) -> dict:
    W, H = size
    objects = [{"id": "laptop", "label": "MacBook", "shape": "box", "x": 0.1563, "y": 0.1106, "width": 0.3126, "depth": 0.2212, "height": 0.009, "top": 0}]
    places = [
        {"id": "home", "x": 0.15, "y": -0.045, "on": "desk"},
        {"id": "leftFront", "x": -0.015, "y": -0.04, "on": "desk"},
        {"id": "edgeFront", "x": 0.06, "y": -0.032, "on": "desk"},
        {"id": "edgeSeat", "x": 0.06, "y": -0.004, "on": "laptop", "seat": True},
        {"id": "palmFront", "x": 0.268, "y": -0.018, "on": "desk"},
        {"id": "palmRest", "x": 0.268, "y": 0.024, "on": "laptop"},
        {"id": "rightFront", "x": 0.33, "y": -0.03, "on": "desk"},
    ]
    paths = [["home", "edgeFront", "walk"], ["home", "palmFront", "walk"], ["home", "leftFront", "walk"], ["edgeFront", "leftFront", "walk"],
             ["edgeFront", "edgeSeat", "hop"], ["palmFront", "palmRest", "hop"], ["palmFront", "rightFront", "walk"]]
    hubs = {p["id"]: np.array([p["x"], p["y"]]) for p in places if p["on"] == "desk"}
    names = {"cup": ("cup", "Rim"), "bottle_cap": ("cap", "Seat"), "wallet": ("wallet", "Top"), "water_bottle": ("bottle", "Side")}

    for o in argon:
        if o["kind"] == "laptop" or "avoid" in o["affordances"]:
            continue
        pts = [cams.ray_to_desk(times[f["frame"]], f["point"][1] / 1000 * W, f["point"][0] / 1000 * H)
               for f in o["footprint"] if 0 <= f["frame"] < len(times)]
        if not pts:
            continue
        x, y = np.median(np.array(pts)[:, :2], axis=0)
        s = o["size_cm"]
        oid = names.get(o["kind"], (o["id"], ""))[0]
        r = max(s["width"], s["depth"]) / 200
        h = s["height"] / 100
        # Keep a clear lane for walking: the object's front, toward the camera (−y).
        front = np.array([x, y - r - 0.02])
        if o["kind"] == "cup" or ("climb" in o["affordances"] and h > 0.06):
            base = desk_z(normal, offset, x, y)
            objects.append({"id": oid, "label": o["label"], "shape": "cup", "x": x, "y": y, "radius": r, "bottomRadius": r * 0.78, "base": base, "height": h})
            places += [{"id": f"{oid}Front", "x": x, "y": y - r - 0.031, "on": "desk"},
                       {"id": f"{oid}Rim", "x": x, "y": y - r - 0.001, "on": oid, "seat": True}]
            paths.append([f"{oid}Front", f"{oid}Rim", "climb"])
            anchor = f"{oid}Front"
            front = np.array([x, y - r - 0.031])
        elif "sit" in o["affordances"] and h < 0.03:
            objects.append({"id": oid, "label": o["label"], "shape": "cylinder", "x": x, "y": y, "radius": r, "height": h})
            places += [{"id": f"{oid}Front", "x": x, "y": y - r - 0.024, "on": "desk"},
                       {"id": f"{oid}Seat", "x": x + 0.005, "y": y - r + 0.006, "on": oid, "seat": True}]
            paths.append([f"{oid}Front", f"{oid}Seat", "hop"])
            anchor = f"{oid}Front"
            front = np.array([x, y - r - 0.024])
        elif "stand" in o["affordances"]:
            objects.append({"id": oid, "label": o["label"], "shape": "box", "x": x, "y": y, "width": s["width"] / 100, "depth": s["depth"] / 100,
                            "height": h, "rotation": o.get("rotation_deg", 0)})
            places += [{"id": f"{oid}Front", "x": x - 0.01, "y": y - s["depth"] / 200 - 0.025, "on": "desk"},
                       {"id": f"{oid}Top", "x": x, "y": y - s["depth"] / 200 + 0.025, "on": oid}]
            paths.append([f"{oid}Front", f"{oid}Top", "hop"])
            anchor = f"{oid}Front"
            front = np.array([x - 0.01, y - s["depth"] / 200 - 0.025])
        else:  # lean against it
            objects.append({"id": oid, "label": o["label"], "shape": "cylinder", "x": x, "y": y, "radius": r, "height": h})
            places.append({"id": f"{oid}Side", "x": x + r + 0.012, "y": y - 0.02, "on": "desk", "face": -0.55})
            anchor = f"{oid}Side"
            front = np.array([x + r + 0.012, y - 0.02])
        nearest = sorted(hubs, key=lambda k: np.linalg.norm(hubs[k] - front))[:2]
        paths += [[anchor, k, "walk"] for k in nearest]
        hubs[anchor] = front

    return {"source": MODEL, "units": "meters, world frame of cameras.json", "note": "Generated by desk-buddy perceive from Gemini 4 Argon output; laptop is the metric anchor.",
            "objects": [{k: (float(v) if isinstance(v, (np.floating, float)) else v) for k, v in o.items()} for o in objects], "places": [
                {k: (float(v) if isinstance(v, (np.floating, float)) else v) for k, v in p.items()} for p in places], "paths": paths}


def perceive(scene: Path, times: list[float], output: Path | None = None) -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY is unset; Argon perception cannot run. The hand-placed map stays in use.")
    surfaces = json.loads((scene / "surfaces.json").read_text())["desk"]
    normal, offset = np.array(surfaces["normal"]), float(surfaces["offset"])
    cams = Cameras(scene / "cameras.json", (normal, offset))
    with tempfile.TemporaryDirectory() as tmp:
        images = _frames(scene / "desk.mp4", times, Path(tmp))
        from PIL import Image
        size = Image.open(images[0]).size
        raw = ask_argon(images, key)
    text = "".join(p.get("text", "") for c in raw.get("candidates", []) for p in c.get("content", {}).get("parts", []) if not p.get("thought"))
    found = json.loads(text)["objects"]
    out = output or scene / "objects.json"
    (out.parent / "argon_perception.json").write_text(json.dumps({"model": MODEL, "times": times, "objects": found, "usage": raw.get("usageMetadata")}, indent=2))
    desk_map = build_map(found, cams, times, size, normal, offset)
    out.write_text(json.dumps(desk_map, indent=2))
    return {"objects": [o["id"] for o in desk_map["objects"]], "places": len(desk_map["places"]), "written": str(out)}
