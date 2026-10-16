from __future__ import annotations

import cv2
import numpy as np


def transform(points, matrix):
    return np.asarray(points) @ matrix[:3, :3].T + matrix[:3, 3]


def unproject(depth, K):
    y, x = np.indices(depth.shape)
    rays = np.stack([x, y, np.ones_like(x)], axis=-1) @ np.linalg.inv(K).T
    return rays * depth[..., None]


def fit_plane(points, up=np.array([0., 0., 1.]), threshold=.008, iterations=500, seed=17):
    points = np.asarray(points)
    points = points[np.all(np.isfinite(points), axis=1)]
    if len(points) < 30:
        raise ValueError("Insufficient valid points for RANSAC")
    rng = np.random.default_rng(seed)
    if len(points) > 8000:
        points = points[rng.choice(len(points), 8000, replace=False)]
    best = np.zeros(len(points), bool)
    for _ in range(iterations):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        normal = np.cross(b-a, c-a)
        length = np.linalg.norm(normal)
        if length < 1e-9:
            continue
        normal /= length
        if abs(normal @ up) < .90:
            continue
        hit = np.abs((points-a) @ normal) < threshold
        if hit.sum() > best.sum():
            best = hit
    if best.sum() < 30 or best.mean() < .25:
        raise ValueError("No sufficiently supported horizontal plane")
    center = points[best].mean(axis=0)
    _, _, vt = np.linalg.svd(points[best]-center, full_matrices=False)
    normal = vt[-1]
    if normal @ up < 0:
        normal = -normal
    if normal @ up < .90:
        raise ValueError("Refined plane is inconsistent with the horizontal-surface constraint")
    d = -normal @ center
    residuals = np.abs(points @ normal + d)
    return {"normal": normal.tolist(), "offset": float(d), "center": center.tolist(),
            "inlier_ratio": float(np.mean(residuals < threshold)),
            "inlier_rms_m": float(np.sqrt(np.mean(residuals[residuals < threshold]**2))),
            "ransac_threshold_m": threshold}


def project(points, K, w2c, distortion=None):
    rvec = cv2.Rodrigues(w2c[:3, :3])[0]
    uv = cv2.projectPoints(np.asarray(points, np.float64), rvec, w2c[:3, 3], K, distortion)[0].reshape(-1, 2)
    return uv, transform(points, w2c)[:, 2]


def stabilize_depth(current, previous, K, previous_K, w2c, previous_w2c, rgb, previous_rgb):
    """Pose-reprojected history with z-buffer, disocclusion and color rejection.

    Never fill unknown pixels with a background estimate. Motion/edges reject
    history rather than dragging foreground silhouettes into neighboring pixels.
    """
    if previous is None:
        return current.copy(), 0
    h, w = current.shape
    points = unproject(previous, previous_K).reshape(-1, 3)
    moved = transform(points, w2c @ np.linalg.inv(previous_w2c))
    q = moved @ K.T
    valid = (previous.ravel() > 0) & (moved[:, 2] > .01) & np.all(np.isfinite(q), axis=1)
    uv = np.zeros((len(q), 2), np.int32)
    uv[valid] = np.rint(q[valid, :2]/q[valid, 2:3]).astype(np.int32)
    valid &= (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    ids = np.flatnonzero(valid)
    # Nearest z wins; stable ordering makes the operation deterministic.
    order = ids[np.argsort(moved[ids, 2], kind="stable")]
    flat = uv[order, 1]*w+uv[order, 0]
    _, first = np.unique(flat, return_index=True)
    ids = order[first]
    flat = flat[first]
    history = np.zeros(h*w, np.float32)
    history[flat] = moved[ids, 2]
    history = history.reshape(h, w)
    colors = np.zeros_like(rgb).reshape(-1, 3)
    colors[flat] = previous_rgb.reshape(-1, 3)[ids]
    colors = colors.reshape(rgb.shape)
    color_ok = np.max(np.abs(colors.astype(float)-rgb.astype(float)), axis=-1) < 24
    use = (current > 0) & (history > 0) & (np.abs(history-current) < .008+.015*current) & color_ok
    result = current.copy()
    result[use] = current[use]*.65+history[use]*.35
    return result, int(use.sum())
