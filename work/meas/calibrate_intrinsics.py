#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""内参标定：读 calib/images，输出 calib/intrinsics.npz。

用法：
  python calibrate_intrinsics.py --dir calib/images --pattern 9x12 --square 9.96
"""

import argparse
import glob
import os
import sys

import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def parse_pattern(s: str):
    a, b = s.lower().split("x")
    return int(a), int(b)


def find_corners(gray, pattern):
    if hasattr(cv2, "findChessboardCornersSB"):
        ok, corners = cv2.findChessboardCornersSB(
            gray, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE
        )
        if ok:
            return True, corners
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    ok, corners = cv2.findChessboardCorners(gray, pattern, flags)
    if ok:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    return ok, corners


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="calib/images")
    ap.add_argument("--pattern", default="9x12")
    ap.add_argument("--square", type=float, default=10.0, help="实测格距 mm")
    ap.add_argument("--out", default="calib/intrinsics.npz")
    args = ap.parse_args()

    pattern = parse_pattern(args.pattern)
    files = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        files += glob.glob(os.path.join(args.dir, ext))
    files = sorted(files)
    if not files:
        print("没有图片：", args.dir)
        return 2

    # 世界坐标：z=0 平面上的棋盘格，单位 mm
    objp = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2) * args.square

    objpoints, imgpoints, used, size = [], [], [], None
    for fn in files:
        img = cv2.imread(fn)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ok, corners = find_corners(gray, pattern)
        if not ok:
            print("跳过（找不到棋盘）：", os.path.basename(fn))
            continue
        objpoints.append(objp)
        imgpoints.append(corners.reshape(-1, 2))
        used.append(fn)
        size = gray.shape[::-1]
        print("OK  ", os.path.basename(fn), f"{size[0]}x{size[1]}")

    if len(objpoints) < 6:
        print(f"有效图只有 {len(objpoints)} 张，至少 6 张（建议 15–20）")
        return 2

    ret, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, size, None, None
    )
    print("\n---- 内参 ----")
    print("RMS 重投影误差 = %.4f px" % ret)
    print("K =\n", np.array2string(K, precision=3, suppress_small=True))
    print("dist =", np.array2string(dist.ravel(), precision=6, suppress_small=True))

    # 每张图的重投影误差，便于剔除坏图
    print("\n每张图误差：")
    errs = []
    for i, fn in enumerate(used):
        proj, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], K, dist)
        e = np.linalg.norm(proj.reshape(-1, 2) - imgpoints[i], axis=1).mean()
        errs.append(e)
        print(f"  {os.path.basename(fn):16s} {e:.3f} px")
    errs = np.array(errs)
    print(f"平均 {errs.mean():.3f} px，最大 {errs.max():.3f} px")

    fx, fy = K[0, 0], K[1, 1]
    w, h = size
    fov_x = 2 * np.degrees(np.arctan(w / (2 * fx)))
    fov_y = 2 * np.degrees(np.arctan(h / (2 * fy)))
    print(f"视场角：水平 {fov_x:.2f}°，垂直 {fov_y:.2f}°")
    print(f"像素当量（若 WD=250mm）：{250 * (w / fx) / w:.4f} mm/px  "
          f"（视野宽 {250 * w / fx:.1f} mm）")

    if ret > 0.5:
        print("\n[警告] RMS > 0.5 px：棋盘不平、图模糊、姿态单一或格距填错，建议重拍。")
    elif ret > 0.3:
        print("\n[注意] RMS 0.3–0.5 px，可接受但建议补拍。")
    else:
        print("\n[OK] RMS < 0.3 px。")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    np.savez(args.out, K=K, dist=dist, rms=ret, image_size=size,
             square=args.square, pattern=pattern)
    print("已保存", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())