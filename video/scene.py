"""Scene geometry for the video tools: interpolated plate camera, desk plane, object outlines.

Mirrors player/src/scene/camera-track.ts so overlays drawn here line up with Bricki.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SCENE = ROOT / "player" / "public" / "scene"
NORMAL = np.array([-0.0168397825, -0.0671243837, 0.9976024954])
OFFSET = 0.0084577321


def desk_z(x: float, y: float) -> float:
    return -(NORMAL[0] * x + NORMAL[1] * y + OFFSET) / NORMAL[2]


def _quat(m: np.ndarray) -> np.ndarray:
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        return np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s])
    i = int(np.argmax(np.diag(m)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = np.sqrt(1.0 + m[i, i] - m[j, j] - m[k, k]) * 2
    q = np.zeros(4)
    q[i] = 0.25 * s
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    q[3] = (m[k, j] - m[j, k]) / s
    return q


def _slerp(a: np.ndarray, b: np.ndarray, u: float) -> np.ndarray:
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + u * (b - a)
        return q / np.linalg.norm(q)
    th = np.arccos(d)
    return (np.sin((1 - u) * th) * a + np.sin(u * th) * b) / np.sin(th)


def _rot(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


class Track:
    def __init__(self, path: Path = SCENE / "cameras.json"):
        frames = json.loads(path.read_text())["frames"]
        self.t = np.array([f["t"] for f in frames])
        c2w = [np.array(f["c2w"]) for f in frames]
        self.pos = [m[:3, 3] for m in c2w]
        self.q = [_quat(m[:3, :3]) for m in c2w]
        self.K = [np.array(f["K"]) for f in frames]

    @property
    def duration(self) -> float:
        return float(self.t[-1])

    def sample(self, time: float) -> tuple[np.ndarray, np.ndarray]:
        """Returns (K, world-to-camera 4x4) at a plate time."""
        time = float(np.clip(time, self.t[0], self.t[-1]))
        i = int(np.searchsorted(self.t, time, side="right") - 1)
        j = min(i + 1, len(self.t) - 1)
        u = 0.0 if self.t[j] == self.t[i] else (time - self.t[i]) / (self.t[j] - self.t[i])
        R = _rot(_slerp(self.q[i], self.q[j], u))
        p = self.pos[i] + (self.pos[j] - self.pos[i]) * u
        K = self.K[i] + (self.K[j] - self.K[i]) * u
        c2w = np.eye(4)
        c2w[:3, :3], c2w[:3, 3] = R, p
        return K, np.linalg.inv(c2w)

    def project(self, time: float, pts) -> np.ndarray:
        K, w2c = self.sample(time)
        pts = np.atleast_2d(np.asarray(pts, float))
        c = (w2c[:3, :3] @ pts.T).T + w2c[:3, 3]
        uv = (K @ c.T).T
        return uv[:, :2] / uv[:, 2:3]


def load_objects() -> dict:
    return json.loads((SCENE / "objects.json").read_text())


def outline(o: dict, n: int = 48) -> list[np.ndarray]:
    """3D polylines (top and base rings, verticals) describing an object proxy."""
    if o["shape"] == "box":
        top = o.get("top", desk_z(o["x"], o["y"]) + o["height"])
        base = top - o["height"]
        a = np.radians(o.get("rotation", 0))
        hw, hd = o["width"] / 2, o["depth"] / 2
        corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd), (-hw, -hd)]
        xy = [(o["x"] + cx * np.cos(a) - cy * np.sin(a), o["y"] + cx * np.sin(a) + cy * np.cos(a)) for cx, cy in corners]
        rings = [np.array([(x, y, z) for x, y in xy]) for z in (base, top)]
        verts = [np.array([(x, y, base), (x, y, top)]) for x, y in xy[:4]]
        return rings + verts
    if o["shape"] == "cup":
        base, top = o["base"], o["base"] + o["height"]
        rb, rt = o["bottomRadius"], o["radius"]
    else:
        base = desk_z(o["x"], o["y"])
        top = base + o["height"]
        rb = rt = o["radius"]
    ang = np.linspace(0, 2 * np.pi, n + 1)
    ring = lambda r, z: np.stack([o["x"] + r * np.cos(ang), o["y"] + r * np.sin(ang), np.full_like(ang, z)], 1)
    return [ring(rb, base), ring(rt, top)]


def place_points() -> dict[str, np.ndarray]:
    data = load_objects()
    objs = {o["id"]: o for o in data["objects"]}
    out = {}
    for p in data["places"]:
        if p["on"] == "desk":
            z = desk_z(p["x"], p["y"])
        else:
            o = objs[p["on"]]
            if o["shape"] == "cup":
                z = o["base"] + o["height"]
            elif o["shape"] == "box":
                z = o.get("top", desk_z(o["x"], o["y"]) + o["height"])
            else:
                z = desk_z(o["x"], o["y"]) + o["height"]
        out[p["id"]] = np.array([p["x"], p["y"], z])
    return out
