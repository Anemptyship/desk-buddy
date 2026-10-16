from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .media import write_json
from .tracking import warp
from .geometry import project


def plane_mapping(annotation):
    width, depth = annotation["laptop_width_m"], annotation["laptop_depth_m"]
    world = np.float32([[0, depth], [width, depth], [width, 0], [0, 0]])
    return cv2.getPerspectiveTransform(np.float32(annotation["laptop_corners_px"]), world)


def calibrate(scene: Path, prediction: Path):
    tracks = json.loads((scene / "tracks.json").read_text())["frames"]
    annotation = json.loads((scene / "annotations.json").read_text())
    frames = json.loads((scene / "frames.json").read_text())
    data = np.load(prediction)
    height, width = cv2.imread(str(scene / frames[0]["rgb"])).shape[:2]
    prior = np.median(data["intrinsics"], axis=0).astype(float)
    dh, dw = data["depth"].shape[1:]
    prior[0] *= width/dw
    prior[1] *= height/dh
    prior[0, 0] = prior[1, 1] = (prior[0, 0]+prior[1, 1])/2
    prior[0, 2], prior[1, 2] = width/2, height/2
    mapping = plane_mapping(annotation)
    ids = np.unique(np.linspace(0, len(frames)-1, 32).astype(int))
    objects, images = [], []
    for i in ids:
        t = tracks[i]
        if t is None:
            continue
        xy = warp(t["reference_uv"], mapping)
        objects.append(np.c_[xy, np.zeros(len(xy))].astype(np.float32))
        images.append(np.float32(t["observed_uv"]))
    # Joint optimization of shared intrinsics and per-view poses on a measured
    # planar target. This is not a full-scene 3D bundle adjustment.
    flags = (cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_ASPECT_RATIO |
             cv2.CALIB_FIX_PRINCIPAL_POINT | cv2.CALIB_ZERO_TANGENT_DIST |
             cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3 | cv2.CALIB_FIX_K4 | cv2.CALIB_FIX_K5 | cv2.CALIB_FIX_K6)
    rms, K, distortion, _, _ = cv2.calibrateCamera(objects, images, (width, height), prior.copy(),
         np.zeros(5), flags=flags, criteria=(cv2.TERM_CRITERIA_COUNT+cv2.TERM_CRITERIA_EPS, 40, 1e-8))
    # The small model's focal estimate can be far from the phone's effective
    # focal length. Reject implausible FOVs, not a large change from an AI prior.
    refined = bool(.28*width < K[0, 0] < 2*width and abs(distortion.ravel()[0]) < .5 and rms < 1.2)
    candidate_K, candidate_distortion = K.copy(), distortion.copy()
    if not refined:
        K, distortion = prior.copy(), np.zeros(5)
    exported, errors = [], []
    for i, (frame, t) in enumerate(zip(frames, tracks)):
        entry = {"index": i, "timestamp_s": frame["timestamp_s"], "intrinsics": K.tolist(),
                 "distortion": distortion.ravel().tolist(), "valid": False}
        if t is not None:
            xy = warp(t["reference_uv"], mapping)
            obj = np.c_[xy, np.zeros(len(xy))].astype(np.float64)
            observed = np.float64(t["observed_uv"])
            ok, rvec, tvec, inliers = cv2.solvePnPRansac(obj, observed, K, distortion,
                 iterationsCount=300, reprojectionError=2, confidence=.999, flags=cv2.SOLVEPNP_ITERATIVE)
            if ok and inliers is not None and len(inliers) >= 6:
                ix = inliers.ravel()
                rvec, tvec = cv2.solvePnPRefineLM(obj[ix], observed[ix], K, distortion, rvec, tvec)
                matrix = np.eye(4)
                matrix[:3, :3] = cv2.Rodrigues(rvec)[0]
                matrix[:3, 3] = tvec.ravel()
                projected, z = project(obj[ix], K, matrix, distortion)
                error = float(np.sqrt(np.mean(np.sum((projected-observed[ix])**2, axis=1))))
                valid = bool(np.all(z > .01) and error < 2)
                entry.update(valid=valid, world_to_camera=matrix.tolist(),
                             camera_to_world=np.linalg.inv(matrix).tolist(), reprojection_rms_px=error)
                errors.append(error)
        exported.append(entry)
    report = {"calibration_source": "DA3 intrinsic prior + measured laptop-plane multi-view calibration",
              "planar_bundle_adjustment": True, "full_scene_bundle_adjustment": False,
              "refined_intrinsics_accepted": refined, "calibration_train_rms_px": float(rms),
              "prior_focal_px": float(prior[0, 0]), "focal_px": float(K[0, 0]),
              "rejected_candidate_focal_px": None if refined else float(candidate_K[0, 0]),
              "rejected_candidate_k1": None if refined else float(candidate_distortion.ravel()[0]),
              "radial_k1": float(distortion.ravel()[0]),
              "pose_reprojection_rms_px": float(np.sqrt(np.mean(np.array(errors)**2))) if errors else None,
              "valid_cameras": sum(c["valid"] for c in exported), "frames": len(frames),
              "world_axes": "meters; origin laptop front-left; +X right; +Y toward hinge; +Z above laptop top",
              "limitations": ["Manually annotated chassis corners and planar approximation introduce systematic error",
                              "Low reprojection error on laptop does not establish desk or object occlusion accuracy",
                              "Lens parameters are inferred, not factory camera calibration"]}
    write_json(scene / "cameras.json", {"schema_version": 1, "convention": "OpenCV +x right +y down +z forward", "world": report["world_axes"], "frames": exported})
    write_json(scene / "calibration_report.json", report)
    print(json.dumps(report, indent=2), flush=True)
