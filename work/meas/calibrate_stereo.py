# -*- coding: utf-8 -*-
"""双目标定：各自内参 + stereoCalibrate + 台面位姿。

用法：
  python calibrate_stereo.py --left calib/stereo/left --right calib/stereo/right \
      --pattern 11x8 --square 20.01 --out calib/stereo.npz

  # 台面位姿（棋盘平放在玻璃上，左右各拍一张）
  python calibrate_stereo.py ... --stage-left calib/stage_left.png --stage-right calib/stage_right.png

输出：
  calib/stereo.npz   K1,D1,K2,D2,R,T,rms,baseline
  calib/stage.npz    R0,t0,n,d0（左相机系，z=0 在玻璃上表面）
"""
import argparse
import glob
import os
import sys

import cv2
import numpy as np

from stereo_common import stage_plane_from_board

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def parse_pattern(s):
    a, b = s.lower().split("x")
    return int(a), int(b)


def find_corners(gray, pattern):
    if hasattr(cv2, "findChessboardCornersSB"):
        try:
            ok, corners = cv2.findChessboardCornersSB(
                gray, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
            if ok:
                return True, corners.astype(np.float32)
        except Exception:
            pass
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    ok, corners = cv2.findChessboardCorners(gray, pattern, flags)
    if ok:
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), crit)
    return ok, corners


def calibrate_one(objp, pts, size):
    ret, K, D, rvecs, tvecs = cv2.calibrateCamera(objp, pts, size, None, None)
    return ret, K, D, rvecs, tvecs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", default="calib/stereo/left")
    ap.add_argument("--right", default="calib/stereo/right")
    ap.add_argument("--pattern", default="11x8")
    ap.add_argument("--square", type=float, default=20.01)
    ap.add_argument("--refine", action="store_true", help="stereoCalibrate 同时优化内参")
    ap.add_argument("--stage-left", default="")
    ap.add_argument("--stage-right", default="")
    ap.add_argument("--board-thickness", type=float, default=0.0,
                    help="标定板厚度 mm（板面到玻璃的距离）")
    ap.add_argument("--out", default="calib/stereo.npz")
    args = ap.parse_args()

    pattern = parse_pattern(args.pattern)
    objp = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2) * args.square

    pairs = []
    for fn in sorted(glob.glob(os.path.join(args.left, "*"))):
        base = os.path.basename(fn)
        fr = os.path.join(args.right, base)
        if os.path.exists(fr) and base.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
            pairs.append((fn, fr))
    if not pairs:
        print("没有成对图片：", args.left, args.right)
        return 2

    obj_pts, pts1, pts2, used, size = [], [], [], [], None
    for fl, fr in pairs:
        a = cv2.imread(fl, cv2.IMREAD_GRAYSCALE)
        b = cv2.imread(fr, cv2.IMREAD_GRAYSCALE)
        if a is None or b is None:
            continue
        ok1, c1 = find_corners(a, pattern)
        ok2, c2 = find_corners(b, pattern)
        if not (ok1 and ok2):
            print("跳过（角点不全）：", os.path.basename(fl))
            continue
        obj_pts.append(objp)
        pts1.append(c1.reshape(-1, 2))
        pts2.append(c2.reshape(-1, 2))
        used.append(os.path.basename(fl))
        size = a.shape[::-1]
        print(f"OK  {os.path.basename(fl)}  {size[0]}x{size[1]}")

    if len(obj_pts) < 6:
        print(f"有效对只有 {len(obj_pts)} 对，至少 6 对（建议 15–20 对）")
        return 2

    print("\n---- 左相机内参 ----")
    rms1, K1, D1, rvecs1, tvecs1 = calibrate_one(obj_pts, pts1, size)
    print(f"RMS={rms1:.4f}px\nK1=\n{K1}")
    print("\n---- 右相机内参 ----")
    rms2, K2, D2, rvecs2, tvecs2 = calibrate_one(obj_pts, pts2, size)
    print(f"RMS={rms2:.4f}px\nK2=\n{K2}")

    flags = 0 if args.refine else cv2.CALIB_FIX_INTRINSIC
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6)
    rms, K1, D1, K2, D2, R, T, E, F = cv2.stereoCalibrate(
        obj_pts, pts1, pts2, K1, D1, K2, D2, size,
        flags=flags, criteria=crit)

    print("\n---- 双目 ----")
    print(f"stereo RMS = {rms:.4f} px")
    print("R =\n", np.array2string(R, precision=5, suppress_small=True))
    print("T =", np.array2string(T.ravel(), precision=4))
    print(f"基线 = {np.linalg.norm(T):.3f} mm")
    print("每对重投影误差（左 / 右，px）：")
    for i, name in enumerate(used):
        p1, _ = cv2.projectPoints(obj_pts[i], rvecs1[i], tvecs1[i], K1, D1)
        p2, _ = cv2.projectPoints(obj_pts[i], rvecs2[i], tvecs2[i], K2, D2)
        e1 = np.linalg.norm(p1.reshape(-1, 2) - pts1[i], axis=1).mean()
        e2 = np.linalg.norm(p2.reshape(-1, 2) - pts2[i], axis=1).mean()
        print(f"  {name:20s} {e1:.3f} / {e2:.3f}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    np.savez(args.out, K1=K1, D1=D1, K2=K2, D2=D2, R=R, T=T, rms=rms,
             image_size=size, baseline=float(np.linalg.norm(T)))
    print("已保存", args.out)

    if args.stage_left and args.stage_right:
        a = cv2.imread(args.stage_left, cv2.IMREAD_GRAYSCALE)
        b = cv2.imread(args.stage_right, cv2.IMREAD_GRAYSCALE)
        ok1, c1 = find_corners(a, pattern)
        ok2, c2 = find_corners(b, pattern)
        if not (ok1 and ok2):
            print("[警告] 台面图角点不全，跳过 stage.npz")
            return 0
        ok, rvec, tvec = cv2.solvePnP(objp, c1, K1, D1, flags=cv2.SOLVEPNP_IPPE)
        R0, _ = cv2.Rodrigues(rvec)
        t0 = tvec.ravel()
        n, d0 = stage_plane_from_board(K1, D1, R0, t0, args.board_thickness)
        np.savez(os.path.splitext(args.out)[0] + "_stage.npz",
                 R0=R0, t0=t0, n=n, d0=d0, board_thickness=args.board_thickness,
                 image_size=size)
        print("台面位姿：n =", np.array2string(n, precision=5),
              f"d0 = {d0:.3f} mm")
        ok2, rvec2, tvec2 = cv2.solvePnP(objp, c2, K2, D2, flags=cv2.SOLVEPNP_IPPE)
        R2, _ = cv2.Rodrigues(rvec2)
        n2 = R2[:, 2]
        n2_in_left = R.T @ n2
        print("右相机台面法向（转到左系）=", np.array2string(n2_in_left, precision=5),
              " 与左法向夹角 = %.2f°" % np.degrees(
                  np.arccos(np.clip(abs(n2_in_left @ n), -1, 1))))
    else:
        print("[提示] 未给 --stage-left/--stage-right，未生成台面位姿。")
    return 0


if __name__ == "__main__":
    sys.exit(main())