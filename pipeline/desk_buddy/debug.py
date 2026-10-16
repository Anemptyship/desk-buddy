from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .geometry import project
from .media import encode_vfr, write_json


def plane_z(xy, plane):
    n = np.float64(plane["normal"])
    return -(xy @ n[:2]+plane["offset"])/n[2]


def render_debug(scene: Path):
    frames = json.loads((scene / "frames.json").read_text())
    cameras = json.loads((scene / "cameras.json").read_text())["frames"]
    depth_manifest = json.loads((scene / "depth/manifest.json").read_text())
    plane = json.loads((scene / "surfaces.json").read_text())["desk"]
    if "normal" not in plane:
        raise ValueError("No RANSAC desk plane available; cannot render a pretend surface")
    normal = np.float64(plane["normal"])
    output = scene / "debug_frames"
    output.mkdir(exist_ok=True)
    segments, cubes = [], []
    for x in np.arange(-.14, .47, .01):
        segments.append(np.array([[x, -.12], [x, .31]]))
    for y in np.arange(-.12, .32, .01):
        segments.append(np.array([[-.14, y], [.46, y]]))
    for x, y in [(-.065, .005), (.080, -.07), (.335, -.06)]:
        base = np.array([[x, y], [x+.025, y], [x+.025, y+.025], [x, y+.025]])
        bottom = np.c_[base, plane_z(base, plane)]
        cubes.append(np.r_[bottom, bottom+normal*.025])
    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    for i, (f, c, d) in enumerate(zip(frames, cameras, depth_manifest["frames"])):
        source = cv2.imread(str(scene / f["rgb"]))
        K = np.float64(c["intrinsics"])
        image = cv2.undistort(source, K, np.float64(c["distortion"]), None, K)
        w2c = np.float64(c["world_to_camera"])
        depth = cv2.imread(str(scene / "depth" / d["stabilized"]), cv2.IMREAD_UNCHANGED).astype(float)*.001
        h, w = image.shape[:2]
        dh, dw = depth.shape

        def line(points, color, thickness):
            # Subdivide lines before testing scene depth so an entire long grid
            # line is not hidden or revealed based on one depth sample.
            p = np.linspace(points[0], points[1], 25)
            uv, z = project(p, K, w2c)
            visible = (z > .01) & (uv[:,0] >= 0) & (uv[:,0] < w) & (uv[:,1] >= 0) & (uv[:,1] < h)
            xy = np.int32(np.clip(uv * [dw/w, dh/h], [0,0], [dw-1, dh-1]))
            scene_z = depth[xy[:,1], xy[:,0]]
            visible &= (scene_z == 0) | (z <= scene_z+.012)
            for j in range(len(p)-1):
                if visible[j] and visible[j+1]:
                    cv2.line(image, tuple(np.int32(uv[j])), tuple(np.int32(uv[j+1])), color, thickness, cv2.LINE_AA)

        if c["valid"]:
            overlay = image.copy()
            for xy in segments:
                line(np.c_[xy, plane_z(xy, plane)], (115, 188, 140), 1)
            image = cv2.addWeighted(image, .50, overlay, .50, 0)
            for cube in cubes:
                for a, b in edges:
                    line(cube[[a,b]], (64, 64, 255), 2)
        cv2.rectangle(image, (0,0), (w,62), (23,27,28), -1)
        cv2.putText(image, "DESK BUDDY / STAGE 1 - ESTIMATED GEOMETRY", (18,25), cv2.FONT_HERSHEY_SIMPLEX, .57, (230,240,233), 1, cv2.LINE_AA)
        label = f"{f['timestamp_s']:05.2f}s | frame {i:03d} | 1 cm grid / 2.5 cm cubes | PnP {c.get('reprojection_rms_px',0):.2f}px"
        cv2.putText(image, label, (18,48), cv2.FONT_HERSHEY_SIMPLEX, .45, (154,198,174), 1, cv2.LINE_AA)
        cv2.rectangle(image, (0,h-29), (w,h), (23,27,28), -1)
        cv2.putText(image, "PROVISIONAL: monocular depth / manually anchored scale / occlusion edges unverified", (18,h-10), cv2.FONT_HERSHEY_SIMPLEX, .43, (151,191,243), 1, cv2.LINE_AA)
        cv2.imwrite(str(output / f"{i:06d}.png"), image)
        if i in (30, 150, 315, 450):
            cv2.imwrite(str(scene / f"debug_{i:06d}.jpg"), image)
        if i % 100 == 0:
            print(f"Rendered {i}/{len(frames)}", flush=True)
    encode_vfr(scene, output, scene / "debug_track.mp4")
    write_json(scene / "debug_render.json", {"source_frames": len(frames), "encoded_frames": len(frames)+1, "terminal_frame": "one identical final hold frame preserves the original final sample duration", "timestamp_source": "original presentation timestamps", "rgb_domain": "rectified SDR RGB", "grid_spacing_m": .01, "cube_size_m": .025, "plane": plane, "quality_approved": False})
