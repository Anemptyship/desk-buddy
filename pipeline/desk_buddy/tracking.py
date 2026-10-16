from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import cv2
import numpy as np

from .media import write_json


def warp(points, homography):
    return cv2.perspectiveTransform(np.asarray(points, np.float64).reshape(-1, 1, 2), homography).reshape(-1, 2)


def robust_homography(reference, current, threshold=1.5):
    reference, current = np.asarray(reference), np.asarray(current)
    if len(reference) < 12:
        raise ValueError("Too few correspondences")
    # A deterministic held-out set is never used to estimate the homography.
    test = np.arange(len(reference)) % 5 == 0
    H, mask = cv2.findHomography(reference[~test], current[~test], cv2.RANSAC, threshold,
                               maxIters=5000, confidence=.999)
    if H is None or mask.sum() < 10 or not np.all(np.isfinite(H)):
        raise ValueError("Homography RANSAC failed")
    errors = np.linalg.norm(warp(reference[test], H)-current[test], axis=1)
    inliers = mask[:, 0].astype(bool)
    return H / H[2, 2], ~test, inliers, errors


def track(scene: Path, annotations: Path):
    cv2.setNumThreads(1)
    annotation = json.loads(annotations.read_text())
    frames = json.loads((scene / "frames.json").read_text())
    ref_id = annotation["reference_frame"]
    reference = cv2.imread(str(scene / frames[ref_id]["rgb"]), cv2.IMREAD_GRAYSCALE)
    if list(reference.shape[::-1]) != annotation["analysis_image_size"]:
        raise ValueError("Annotation image size differs from decoded RGB. Re-annotate at the selected analysis resolution.")
    mask = np.zeros_like(reference)
    cv2.fillConvexPoly(mask, np.int32(annotation["laptop_corners_px"]), 255)
    # Exclude the silver edge so subpixel feature positions remain inside the rigid base.
    mask = cv2.erode(mask, np.ones((7, 7), np.uint8))
    sift = cv2.SIFT_create(nfeatures=3500, contrastThreshold=.015)
    keypoints, descriptors = sift.detectAndCompute(reference, mask)
    ref_uv = np.float64([k.pt for k in keypoints])
    if len(ref_uv) < 30:
        raise ValueError("Reference laptop plane has too few features")

    def process(f):
        image = cv2.imread(str(scene / f["rgb"]), cv2.IMREAD_GRAYSCALE)
        detector = cv2.SIFT_create(nfeatures=5000, contrastThreshold=.015)
        points, desc = detector.detectAndCompute(image, None)
        if desc is None:
            return f["index"], None
        pairs = cv2.BFMatcher().knnMatch(descriptors, desc, k=2)
        matches = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .72*p[1].distance]
        # Enforce unique destination points to avoid repeated keycap matches.
        matches = sorted(matches, key=lambda m: m.distance)
        unique, used = [], set()
        for m in matches:
            if m.trainIdx not in used:
                unique.append(m)
                used.add(m.trainIdx)
        matches = unique[:400]
        src = np.float64([ref_uv[m.queryIdx] for m in matches])
        dst = np.float64([points[m.trainIdx].pt for m in matches])
        try:
            H, train, inliers, heldout = robust_homography(src, dst)
        except ValueError:
            return f["index"], None
        accepted = heldout[heldout < 3.0]
        data = {"homography": H.tolist(), "reference_uv": src[train][inliers].tolist(),
                "observed_uv": dst[train][inliers].tolist(), "matches": len(matches),
                "inliers": int(inliers.sum()), "heldout_count": len(heldout),
                "heldout_inlier_count": len(accepted),
                "heldout_median_px": float(np.median(heldout)) if len(heldout) else None,
                "heldout_inlier_rms_px": float(np.sqrt(np.mean(accepted**2))) if len(accepted) else None}
        return f["index"], data

    results = [None] * len(frames)
    with ThreadPoolExecutor(max_workers=4) as executor:
        for i, result in executor.map(process, frames):
            results[i] = result
            if i % 50 == 0:
                print(f"Tracked {i}/{len(frames)}", flush=True)
    direct = [i for i, value in enumerate(results) if value is not None]
    failed = [i for i, value in enumerate(results) if value is None]
    # One hop through a directly registered reference. Never integrate a chain
    # of frame-to-frame transforms or treat a held previous pose as a measurement.
    for i in failed:
        for anchor in sorted(direct, key=lambda j: abs(j-i))[:8]:
            image = cv2.imread(str(scene / frames[anchor]["rgb"]), cv2.IMREAD_GRAYSCALE)
            H_anchor = np.float64(results[anchor]["homography"])
            local_mask = cv2.warpPerspective(mask, H_anchor, (image.shape[1], image.shape[0]))
            keypoints, descriptors = sift.detectAndCompute(image, local_mask)
            if descriptors is None:
                continue
            ref_uv = warp(np.float64([k.pt for k in keypoints]), np.linalg.inv(H_anchor))
            _, recovered = process(frames[i])
            if recovered and recovered["inliers"] >= 12 and recovered["heldout_median_px"] < 1.5:
                recovered["anchor_frame"] = anchor
                recovered["anchor_heldout_error_px"] = results[anchor]["heldout_median_px"]
                results[i] = recovered
                break
    # Failed frames stay failed: do not fill them with a previous pose and call it tracking.
    write_json(scene / "tracks.json", {"reference_frame": ref_id, "method": "SIFT; absolute reference homography; held-out validation", "frames": results})
    stats = {"frames": len(results), "tracked": sum(f is not None for f in results),
             "recovered_via_direct_anchor": sum(f is not None and "anchor_frame" in f for f in results),
             "failed_frame_ids": [i for i, f in enumerate(results) if f is None],
             "median_heldout_error_px": float(np.median([f["heldout_median_px"] for f in results if f]))}
    write_json(scene / "tracking_report.json", stats)
    write_json(scene / "annotations.json", annotation)
    print(json.dumps(stats, indent=2), flush=True)
