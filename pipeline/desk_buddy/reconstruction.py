from __future__ import annotations

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np

from .media import write_json


def reconstruct(scene: Path, device: str, count: int, resolution: int):
    import torch
    from depth_anything_3.api import DepthAnything3

    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("Apple MPS unavailable in this process. Use an authorized native process or --device cpu; no silent device substitution.")
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA unavailable. Run this same command on a CUDA host or use --device mps.")
    model_id = os.getenv("DA3_MODEL")
    if not model_id:
        raise ValueError("Set DA3_MODEL in .env; no model ID is selected silently")
    frames = json.loads((scene / "frames.json").read_text())
    ids = np.unique(np.linspace(0, len(frames)-1, min(count, len(frames))).round().astype(int))
    destination = scene / "reconstruction" / f"keyframes_{len(ids)}_{resolution}"
    if destination.exists():
        raise FileExistsError(f"Reconstruction already exists: {destination}")
    destination.mkdir(parents=True)
    print(f"Loading {model_id} on {device}; {len(ids)} views at {resolution}px", flush=True)
    started = time.monotonic()
    model = DepthAnything3.from_pretrained(model_id).to(device=device)
    prediction = model.inference([str(scene / frames[i]["rgb"]) for i in ids], process_res=resolution,
                                 ref_view_strategy="middle", use_ray_pose=True)
    for key in ("depth", "extrinsics", "intrinsics"):
        values = np.asarray(getattr(prediction, key))
        if not np.all(np.isfinite(values)):
            raise ValueError(f"Model emitted nonfinite {key}; refusing to export")
    np.savez_compressed(destination / "prediction.npz", frame_ids=ids, depth=prediction.depth,
                        confidence=prediction.conf, intrinsics=prediction.intrinsics,
                        world_to_camera=prediction.extrinsics, rgb=prediction.processed_images)
    meta = {"model": model_id, "device": device, "torch": torch.__version__, "frames": ids.tolist(),
            "resolution": resolution, "elapsed_s": time.monotonic()-started,
            "scale_status": "relative; must calibrate using user-confirmed object dimensions",
            "pose_convention": "OpenCV world-to-camera; +x right +y down +z forward",
            "distortion": "not estimated by DA3; do not assume calibrated zero distortion",
            "full_frame_coverage": len(ids) == len(frames), "bundle_adjustment": False}
    write_json(destination / "provenance.json", meta)
    preview = []
    for j in np.linspace(0, len(ids)-1, min(6, len(ids))).astype(int):
        depth = prediction.depth[j]
        lo, hi = np.percentile(depth[depth > 0], [3, 97])
        color = cv2.applyColorMap(np.uint8(np.clip((depth-lo)/(hi-lo+1e-6), 0, 1)*255), cv2.COLORMAP_TURBO)
        rgb = cv2.cvtColor(prediction.processed_images[j], cv2.COLOR_RGB2BGR)
        preview.append(np.concatenate([rgb, color], axis=1))
    cv2.imwrite(str(destination / "depth_preview.jpg"), np.concatenate(preview, axis=0))
    print(json.dumps(meta, indent=2), flush=True)
