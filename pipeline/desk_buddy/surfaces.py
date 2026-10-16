from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .geometry import fit_plane, project, transform
from .media import write_json


def reconstruct_desk(scene: Path):
    """Triangulate actual tabletop texture, independent of monocular depth.

    The laptop supplies the metric camera anchor. Only positive-depth points
    observed with sufficient camera parallax and subpixel residuals are kept.
    """
    cv2.setNumThreads(1)
    frames = json.loads((scene / "frames.json").read_text())
    cameras = json.loads((scene / "cameras.json").read_text())["frames"]
    annotation = json.loads((scene / "annotations.json").read_text())
    ref = annotation["reference_frame"]
    gray = cv2.imread(str(scene / frames[ref]["rgb"]), 0)
    mask = np.zeros_like(gray)
    cv2.fillConvexPoly(mask, np.int32([[280,409],[745,407],[778,474],[249,466]]), 255)
    detector = cv2.SIFT_create(nfeatures=5000, contrastThreshold=.008, edgeThreshold=15)
    kp0, desc0 = detector.detectAndCompute(gray, mask)
    uv0 = np.float64([k.pt for k in kp0])
    c0 = cameras[ref]
    K0, d0, P0 = np.float64(c0["intrinsics"]), np.float64(c0["distortion"]), np.float64(c0["world_to_camera"])
    center0 = np.linalg.inv(P0)[:3,3]
    cloud, errors, observation_count = [], [], 0
    for i in np.unique(np.linspace(0,len(frames)-1,48).astype(int)):
        c = cameras[i]
        if not c["valid"]:
            continue
        P = np.float64(c["world_to_camera"])
        center = np.linalg.inv(P)[:3,3]
        if np.linalg.norm(center-center0) < .025:
            continue
        current = cv2.imread(str(scene / frames[i]["rgb"]), 0)
        kp, desc = detector.detectAndCompute(current, None)
        if desc is None or desc0 is None:
            continue
        pairs = cv2.BFMatcher().knnMatch(desc0, desc, k=2)
        matches = [a for pair in pairs if len(pair)==2 for a,b in [pair] if a.distance < .68*b.distance]
        if len(matches) < 6:
            continue
        first = np.float64([uv0[m.queryIdx] for m in matches])
        second = np.float64([kp[m.trainIdx].pt for m in matches])
        K, dist = np.float64(c["intrinsics"]), np.float64(c["distortion"])
        a = cv2.undistortPoints(first[:,None],K0,d0).reshape(-1,2)
        b = cv2.undistortPoints(second[:,None],K,dist).reshape(-1,2)
        hom = cv2.triangulatePoints(P0[:3],P[:3],a.T,b.T)
        xyz = (hom[:3]/hom[3:]).T
        q0,z0 = project(xyz,K0,P0,d0)
        q,z = project(xyz,K,P,dist)
        residual = np.maximum(np.linalg.norm(q0-first,axis=1),np.linalg.norm(q-second,axis=1))
        ray0,ray = xyz-center0,xyz-center
        cosine = np.sum(ray0*ray,axis=1)/(np.linalg.norm(ray0,axis=1)*np.linalg.norm(ray,axis=1))
        parallax = np.arccos(np.clip(cosine,-1,1))
        keep = (z0 > .05) & (z > .05) & (residual < 1.0) & (parallax > np.deg2rad(2)) & (np.abs(xyz[:,2]) < .08)
        cloud.extend(xyz[keep])
        errors.extend(residual[keep])
        observation_count += int(keep.sum())
    report = {"method": "SIFT tabletop texture triangulation with laptop-calibrated cameras; RANSAC",
              "reference_frame": ref, "reference_features": len(kp0), "triangulated_observations": observation_count,
              "units": "meters", "metric_accuracy_verified": False}
    try:
        plane = fit_plane(np.array(cloud), threshold=.004)
        tilt = float(np.degrees(np.arccos(np.clip(plane["normal"][2],-1,1))))
        height = -plane["offset"]/plane["normal"][2]
        accepted = tilt < 8 and -.04 < height < -.001
        report.update(plane, tilt_from_laptop_degrees=tilt, height_at_origin_m=height,
                      reprojection_median_px=float(np.median(errors)),
                      status="estimated_candidate_requires_visual_review" if accepted else "failed_physical_consistency",
                      physical_consistency_pass=accepted)
        if not accepted:
            report["reason"] = "Desk should be nearly parallel to and slightly below the laptop base"
        np.savez_compressed(scene / "desk_points.npz", points=np.array(cloud), reprojection_error=np.array(errors))
    except ValueError as error:
        report.update(status="failed", reason=str(error), physical_consistency_pass=False)
    write_json(scene / "surfaces.json", {"desk": report})
    print(json.dumps(report, indent=2), flush=True)
