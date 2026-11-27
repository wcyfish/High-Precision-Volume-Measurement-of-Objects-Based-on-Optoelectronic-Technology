# -*- coding: utf-8 -*-
"""双目双剪影 + 平面扫描：几何与图像工具。

坐标约定
--------
* 标定板/台面坐标：z=0 在台面（玻璃上表面），z 向上，单位 mm。
* 相机坐标：OpenCV 约定，x 右、y 下、z 朝物体。
* stereoCalibrate 得到 X2 = R @ X1 + T（左相机 -> 右相机）。
* 台面位姿 solvePnP 得到 X1 = R0 @ X_stage + t0。
  台面法向 n = R0[:, 2]，平面方程 n·X1 = d0，d0 = n·t0。
  高度 H 的平面：n·X1 = d0 + H。
"""
import numpy as np
import cv2


def as_K(K):
    return np.asarray(K, dtype=np.float64).reshape(3, 3)


def plane_homography(K1, K2, R, T, n, d):
    """左图 -> 右图，针对 n·X1 = d 的平面（X2 = R X1 + T）。"""
    K1 = as_K(K1)
    K2 = as_K(K2)
    R = np.asarray(R, dtype=np.float64).reshape(3, 3)
    T = np.asarray(T, dtype=np.float64).reshape(3, 1)
    n = np.asarray(n, dtype=np.float64).reshape(3, 1)
    A = R + (T @ n.T) / float(d)
    return K2 @ A @ np.linalg.inv(K1)


def stage_homography(K, R0, t0, H):
    """左图 -> 台面平面 z=H 的 mm 坐标（图像点 -> (x,y) mm）。"""
    K = as_K(K)
    R0 = np.asarray(R0, dtype=np.float64).reshape(3, 3)
    t0 = np.asarray(t0, dtype=np.float64).reshape(3)
    M = np.column_stack([R0[:, 0], R0[:, 1], t0 + float(H) * R0[:, 2]])
    return np.linalg.inv(K @ M)


def backproject_contour(cnt, H_img2stage):
    """轮廓像素 -> 台面 mm 坐标。"""
    pts = np.asarray(cnt, dtype=np.float64).reshape(-1, 1, 2)
    out = cv2.perspectiveTransform(pts, H_img2stage)
    return out.reshape(-1, 2)


def project_stage(pts_xy, H, K, R0, t0, R=None, T=None):
    """台面 (x,y,H) -> 像素；给出 R,T 时投到右相机。"""
    pts_xy = np.asarray(pts_xy, dtype=np.float64).reshape(-1, 2)
    P = np.column_stack([pts_xy, np.full(len(pts_xy), float(H))])
    X = (np.asarray(R0) @ P.T).T + np.asarray(t0).reshape(3)
    if R is not None:
        X = (np.asarray(R) @ X.T).T + np.asarray(T).reshape(3)
    uvw = (as_K(K) @ X.T).T
    return uvw[:, :2] / uvw[:, 2:3]


def polygon_area(pts):
    """鞋带公式，mm^2。"""
    p = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def fit_circle(pts):
    """代数圆拟合，返回 (cx, cy, r, rms)。"""
    p = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    x, y = p[:, 0], p[:, 1]
    A = np.column_stack([2 * x, 2 * y, np.ones(len(x))])
    b = x * x + y * y
    c, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = c[0], c[1]
    r = np.sqrt(max(c[2] + cx * cx + cy * cy, 1e-12))
    rms = float(np.sqrt(np.mean((np.hypot(x - cx, y - cy) - r) ** 2)))
    return float(cx), float(cy), float(r), rms


def make_mask(gray, thr=0.5, ref=None):
    """背光剪影：物体暗、背景亮。返回 (mask 0/255, ref)。"""
    g = np.asarray(gray, dtype=np.float64)
    if ref is None:
        border = np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]])
        ref = float(np.median(border))
    mask = (g < float(thr) * ref).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return mask, ref


def largest_contour(mask):
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None, None, None
    idx = int(np.argmax([cv2.contourArea(c) for c in cnts]))
    return cnts[idx], cnts, hier


def warp_mask(mask, H, size, scale=1.0):
    """把左 mask warp 到右图；scale 用于降采样加速。"""
    if scale == 1.0:
        return cv2.warpPerspective(mask, H, size, flags=cv2.INTER_NEAREST)
    h, w = size[1], size[0]
    small = cv2.resize(mask, (int(round(w * scale)), int(round(h * scale))),
                       interpolation=cv2.INTER_NEAREST)
    S = np.diag([scale, scale, 1.0])
    Hs = S @ H @ np.linalg.inv(S)
    out = cv2.warpPerspective(small, Hs,
                              (int(round(w * scale)), int(round(h * scale))),
                              flags=cv2.INTER_NEAREST)
    return out


def iou(a, b):
    inter = np.count_nonzero(np.logical_and(a > 0, b > 0))
    union = np.count_nonzero(np.logical_or(a > 0, b > 0))
    return float(inter) / float(union) if union else 0.0


def parabola_refine(hs, vals):
    """三点抛物线插值，返回 (h*, v*)。"""
    hs = np.asarray(hs, dtype=np.float64)
    vals = np.asarray(vals, dtype=np.float64)
    i = int(np.argmax(vals))
    if i == 0 or i == len(vals) - 1:
        return float(hs[i]), float(vals[i])
    h0, h1, h2 = hs[i - 1], hs[i], hs[i + 1]
    v0, v1, v2 = vals[i - 1], vals[i], vals[i + 1]
    den = (v0 - 2 * v1 + v2)
    if abs(den) < 1e-12:
        return float(h1), float(v1)
    dh = 0.5 * (v0 - v2) / den
    return float(h1 + dh), float(v1 - 0.25 * (v0 - v2) * dh)


def sweep_height(mask1, mask2, K1, K2, R, T, n, d0,
                 hmin=0.0, hmax=150.0, step=0.5, scale=0.5):
    """平面扫描：找使左右剪影重合最好的 H。"""
    h, w = mask2.shape[:2]
    m1 = cv2.resize(mask1, (int(round(w * scale)), int(round(h * scale))),
                    interpolation=cv2.INTER_NEAREST)
    m2 = cv2.resize(mask2, (int(round(w * scale)), int(round(h * scale))),
                    interpolation=cv2.INTER_NEAREST)
    S = np.diag([scale, scale, 1.0])
    K1s, K2s = S @ as_K(K1), S @ as_K(K2)
    hs, vals = [], []
    for H in np.arange(hmin, hmax + 0.5 * step, step):
        Hm = plane_homography(K1s, K2s, R, T, n, d0 + H)
        wm = cv2.warpPerspective(m1, Hm, (m1.shape[1], m1.shape[0]),
                                 flags=cv2.INTER_NEAREST)
        hs.append(float(H))
        vals.append(iou(wm, m2))
    H, v = parabola_refine(hs, vals)
    return H, v, np.array(hs), np.array(vals)


def load_npz(path):
    d = np.load(path)
    return {k: d[k] for k in d.files}


def stage_plane_from_board(K, dist, R0, t0, board_thickness=0.0):
    """把标定板平面平移到玻璃上表面：z=0 在玻璃。返回 n, d0。"""
    R0 = np.asarray(R0, dtype=np.float64).reshape(3, 3)
    t0 = np.asarray(t0, dtype=np.float64).reshape(3)
    n = R0[:, 2].copy()
    d0 = float(n @ t0) - float(board_thickness)
    return n, d0