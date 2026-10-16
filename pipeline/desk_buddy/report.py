from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from .media import write_json


def summarize(scene: Path):
    frames = json.loads((scene / "frames.json").read_text())
    cameras = json.loads((scene / "cameras.json").read_text())["frames"]
    tracking = json.loads((scene / "tracking_report.json").read_text())
    calibration = json.loads((scene / "calibration_report.json").read_text())
    depth = json.loads((scene / "depth/manifest.json").read_text()) if (scene / "depth/manifest.json").exists() else None
    photometry = []
    previous_camera = previous_time = None
    for f, c in zip(frames, cameras):
        rgb = cv2.imread(str(scene / f["rgb"]))
        gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY).astype(float)
        residual = gray-cv2.GaussianBlur(gray, (3,3), .7)
        edges = cv2.Laplacian(gray, cv2.CV_64F)
        flat = np.abs(edges) < 3
        noise = float(1.4826*np.median(np.abs(residual[flat]-np.median(residual[flat])))) if flat.sum() > 100 else None
        velocity = angular = None
        if c["valid"]:
            camera = np.float64(c["camera_to_world"])
            if previous_camera is not None:
                dt = f["timestamp_s"]-previous_time
                velocity = float(np.linalg.norm(camera[:3,3]-previous_camera[:3,3])/dt)
                angular = float(Rotation.from_matrix(previous_camera[:3,:3].T @ camera[:3,:3]).magnitude()/dt)
            previous_camera, previous_time = camera, f["timestamp_s"]
        photometry.append({"index": f["index"], "timestamp_s": f["timestamp_s"],
             "sdr_luminance_p05_p50_p95": np.percentile(gray,[5,50,95]).tolist(),
             "flat_region_noise_proxy_8bit": noise,
             "focus_laplacian_variance_proxy": float(edges.var()),
             "exposure_ev": None, "shutter_s": None, "focus_distance_m": None,
             "camera_translation_speed_m_s": velocity, "camera_angular_speed_rad_s": angular,
             "motion_blur_pixels": None})
    write_json(scene / "photometry.json", {"measurements": photometry,
          "limitations": "SDR viewing-transform statistics. Texture/compression confound noise; Laplacian measures sharpness, not physical focus distance. Exposure/shutter unavailable; motion speed is not measured motion blur."})
    write_json(scene / "lighting.json", {"status": "incomplete", "key_direction_world": None,
          "color_temperature_k": None, "ambient_intensity": None, "environment_map": None,
          "observations": "Broad indoor illumination visible; no calibrated light probe, scan panorama, or Argon validation available.",
          "provenance": "manual visual review; not an AI result"})
    inventory = [
        ("laptop", "맥북 프로 14인치", "laptop", "알루미늄 몸체 / 유리 화면", True),
        ("paper_cup", "뚜껑 있는 종이컵", "cup", "종이 / 플라스틱 뚜껑", False),
        ("water_bottle", "투명 물병", "bottle", "투명 플라스틱으로 보임", False),
        ("brown_bottle", "갈색 음료병", "bottle", "갈색 유리로 보임", False),
        ("lunch_box", "종이 도시락 상자", "box", "종이 / 골판지", False),
        ("card_holder", "카드 지갑", "wallet", "가죽 또는 합성 소재로 보임", True),
        ("bottle_cap", "작은 병뚜껑", "cap", "플라스틱", False),
    ]
    objects = []
    for oid, name, kind, material, walkable in inventory:
        objects.append({"object_id": oid, "name_ko": name, "type": kind, "material_observation": material,
             "walkable_top_candidate": walkable, "walkable_top": False,
             "sit_spots": [], "climb_points": [], "lean_spots": [], "hide_spots": [], "peek_spots": [],
             "proxy_geometry": None, "tracked_masks": None,
             "status": "manual_inventory_only; geometry and affordances not validated"})
    write_json(scene / "objects.json", {"provenance": "manual fallback, reviewed from real reference frame; Gemini unavailable", "objects": objects})
    reasons = ["Dense occlusion boundaries remain low resolution; SAM video masks not computed",
               "Metric depth is anchored to a manually annotated laptop; no independent metric accuracy check",
               "Desk plane requires visual and physical validation; zero drift is not established",
               "Object proxies and action locations are not reconstructed",
               "Lighting direction, temperature, and environment map are unavailable",
               "Gemini model discovery/Argon validation unavailable without configured API key",
               "Camera refinement uses a planar target; full-scene bundle adjustment is not implemented"]
    if not depth:
        reasons.insert(0, "Full-frame dense depth computation has not finished")
    quality = {"stage": 1, "status": "needs_review", "advance_to_stage_2": False,
        "tracking": tracking, "calibration": calibration,
        "depth": {"frames": len(depth["frames"]), "resolution": depth["resolution"],
            "median_anchor_abs_error_m": float(np.median([f["anchor_median_abs_depth_error_m"] for f in depth["frames"]])),
            "metric_accuracy_verified": False} if depth else None,
        "unmet_requirements": reasons, "api_calls": {"gemini": 0, "video_generation": 0}}
    write_json(scene / "report.json", quality)
    print(json.dumps(quality, ensure_ascii=False, indent=2), flush=True)
