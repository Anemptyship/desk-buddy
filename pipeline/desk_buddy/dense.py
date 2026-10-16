from __future__ import annotations

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np

from .geometry import fit_plane, stabilize_depth, transform, unproject, project
from .media import write_json


def dense(scene: Path, device="mps", resolution=224, batch_size=12, limit=None):
    import torch
    from depth_anything_3.api import DepthAnything3

    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS unavailable")
    model_id = os.environ.get("DA3_MODEL")
    if not model_id:
        raise ValueError("DA3_MODEL is required")
    frames = json.loads((scene / "frames.json").read_text())
    cameras = json.loads((scene / "cameras.json").read_text())["frames"]
    annotation = json.loads((scene / "annotations.json").read_text())
    if any(not c["valid"] for c in cameras):
        raise ValueError("Dense metric inference requires valid measured camera poses for every frame")
    if (scene / "depth/manifest.json").exists():
        raise FileExistsError("Depth manifest exists; select a new output scene for a new run")
    target = scene / ("depth_pilot" if limit else "depth")
    target.mkdir(exist_ok=True)
    (target / "raw").mkdir(exist_ok=True)
    (target / "stabilized").mkdir(exist_ok=True)
    model = DepthAnything3.from_pretrained(model_id).to(device=device)
    if limit:
        frames, cameras = frames[:limit], cameras[:limit]
    previous = previous_rgb = previous_K = previous_w2c = None
    measurements, desk_candidate = [], None
    started = time.monotonic()
    plane_x, plane_y = np.meshgrid(np.linspace(.025, annotation["laptop_width_m"]-.025, 18),
                                  np.linspace(.025, annotation["laptop_depth_m"]-.025, 12))
    plane_points = np.c_[plane_x.ravel(), plane_y.ravel(), np.zeros(plane_x.size)]
    for start in range(0, len(frames), batch_size):
        context_start = min(start, max(0, len(frames)-batch_size))
        block = frames[context_start:context_start+batch_size]
        camera_block = cameras[context_start:context_start+batch_size]
        images, poses, intrinsics = [], [], []
        for f, c in zip(block, camera_block):
            bgr = cv2.imread(str(scene / f["rgb"]))
            K = np.float64(c["intrinsics"])
            bgr = cv2.undistort(bgr, K, np.float64(c["distortion"]), None, K)
            images.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            poses.append(c["world_to_camera"])
            intrinsics.append(K)
        prediction = model.inference(images, extrinsics=np.float32(poses), intrinsics=np.float32(intrinsics),
                 process_res=resolution, ref_view_strategy="middle", align_to_input_ext_scale=True, use_ray_pose=False)
        if not np.all(np.isfinite(prediction.depth)):
            raise ValueError(f"Nonfinite depth in batch starting {start}")
        for j, (frame, camera) in enumerate(zip(block, camera_block)):
            i = frame["index"]
            if i < start:
                continue
            raw = prediction.depth[j].astype(np.float32)
            h, w = raw.shape
            K = np.float64(camera["intrinsics"])
            K[0] *= w/images[j].shape[1]
            K[1] *= h/images[j].shape[0]
            w2c = np.float64(camera["world_to_camera"])
            uv, expected_z = project(plane_points, K, w2c)
            xy = np.rint(uv).astype(int)
            valid = (xy[:, 0] >= 0) & (xy[:, 0] < w) & (xy[:, 1] >= 0) & (xy[:, 1] < h) & (expected_z > 0)
            xy, expected_z = xy[valid], expected_z[valid]
            predicted_z = raw[xy[:, 1], xy[:, 0]]
            ratios = expected_z[predicted_z > 0]/predicted_z[predicted_z > 0]
            if len(ratios) < 30:
                raise ValueError(f"Insufficient metric anchor support in frame {i}")
            scale = float(np.median(ratios))
            raw *= scale
            confidence = prediction.conf[j]
            raw[(raw <= 0) | (raw > 65.534) | (confidence < np.percentile(confidence, 5))] = 0
            rgb = prediction.processed_images[j]
            stable, reused = stabilize_depth(raw, previous, K, previous_K, w2c, previous_w2c, rgb, previous_rgb)
            cv2.imwrite(str(target / "raw" / f"{i:06d}.png"), np.uint16(np.rint(raw*1000)))
            cv2.imwrite(str(target / "stabilized" / f"{i:06d}.png"), np.uint16(np.rint(stable*1000)))
            anchor_residual = np.abs(raw[xy[:, 1], xy[:, 0]]-expected_z)
            anchor_residual = anchor_residual[raw[xy[:, 1], xy[:, 0]] > 0]
            measurements.append({"index": i, "timestamp_s": frame["timestamp_s"], "depth_scale_to_meters": .001,
                  "intrinsics": K.tolist(), "model_to_metric_scale": scale,
                  "anchor_median_abs_depth_error_m": float(np.median(anchor_residual)),
                  "valid_fraction": float((raw > 0).mean()), "history_pixels": reused,
                  "raw": f"raw/{i:06d}.png", "stabilized": f"stabilized/{i:06d}.png"})
            if i == annotation["reference_frame"]:
                world = transform(unproject(stable, K).reshape(-1, 3), np.linalg.inv(w2c))
                desk_mask = np.zeros((h, w), np.uint8)
                poly = np.float64([[280, 409], [745, 407], [778, 474], [249, 466]])
                poly *= [w/960, h/540]
                cv2.fillConvexPoly(desk_mask, np.int32(poly), 1)
                chosen = (desk_mask.ravel() > 0) & (stable.ravel() > 0)
                try:
                    desk_candidate = fit_plane(world[chosen])
                    desk_candidate.update(status="estimated_candidate_requires_visual_review", method="RANSAC on manually selected exposed desk patch", units="meters",
                         limitation="Low-resolution monocular depth; plane is not a measured LiDAR surface")
                except ValueError as error:
                    desk_candidate = {"status": "failed", "reason": str(error)}
                write_json(scene / "monocular_surface_candidate.json", {"desk": desk_candidate})
            previous, previous_rgb, previous_K, previous_w2c = stable, rgb, K, w2c
        completed = min(start+batch_size, len(frames))
        write_json(target / "progress.json", {"completed": completed, "total": len(frames), "elapsed_s": time.monotonic()-started})
        print(f"Depth {completed}/{len(frames)}; {time.monotonic()-started:.1f}s", flush=True)
        if device == "mps":
            torch.mps.empty_cache()
    write_json(target / "manifest.json", {"schema_version": 1, "units": "meters", "png_unit_m": .001,
          "zero": "invalid; never interpreted as an infinitely near occluder", "model": model_id,
          "resolution": [w, h], "coordinate_domain": "rectified RGB camera; undistort RGB with cameras.json before sampling depth",
          "provenance": "DA3 conditioned on laptop-anchored metric poses; per-frame scale anchored to laptop plane",
          "temporal_filter": "pose reprojection + nearest z buffer + depth and color rejection; causal 35% history blend",
          "metric_accuracy": "estimated; requires independent physical validation; anchor residual is not whole-scene error",
          "full_frame_coverage": not limit, "frames": measurements})
