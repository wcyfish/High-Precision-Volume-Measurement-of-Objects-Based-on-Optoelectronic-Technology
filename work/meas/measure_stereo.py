# -*- coding: utf-8 -*-
"""双目双剪影 + 平面扫描测体积。

用法：
  python measure_stereo.py --left shots/left.png --right shots/right.png \
      --stereo calib/stereo.npz --stage calib/stereo_stage.npz --shape l
  python measure_stereo.py ... --shape cylinder
  python measure_stereo.py --selftest          # 合成数据自检，不需要相机

原理：
  - 左右各一张背光剪影；物体暗、背景亮；孔是剪影里的亮洞。
  - 对候选高度 H，把左剪影按平面 z=H 的单应 warp 到右图，IoU 最大即 H。
  - 左剪影外轮廓反投影到 z=H 得顶面面积 A；孔按 z=0（底口）+ 同心先验扣除。
  - V = A * H。
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

from stereo_common import (
    load_npz, make_mask, largest_contour, sweep_height, stage_homography,
    backproject_contour, polygon_area, fit_circle, plane_homography, project_stage,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _fill_holes(mask):
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(mask)
    if cnts:
        cv2.drawContours(out, cnts, -1, 255, -1)
    return out


def measure_masks(m1, m2, st, stage, shape="auto", hmin=0.0, hmax=160.0, step=0.5):
    K1, K2 = st["K1"], st["K2"]
    R, T = st["R"], st["T"]
    R0, t0 = stage["R0"], stage["t0"]
    n, d0 = stage["n"], stage["d0"]

    cnt, cnts, hier = largest_contour(m1)
    if cnt is None:
        raise RuntimeError("左图没有找到剪影")

    # 高度扫描只看外轮廓：孔在底口（z=0），warp 到 z=H 会错位，不能参与 IoU
    m1f = _fill_holes(m1)
    m2f = _fill_holes(m2)
    H, best_iou, hs, vals = sweep_height(
        m1f, m2f, K1, K2, R, T, n, d0, hmin=hmin, hmax=hmax, step=step, scale=0.5)

    Hm = stage_homography(K1, R0, t0, H)
    pts = backproject_contour(cnt, Hm)
    A_out = polygon_area(pts)

    hole_cnt = None
    if shape in ("auto", "cylinder") and cnts is not None and hier is not None:
        idx = int(np.argmax([cv2.contourArea(c) for c in cnts]))
        holes = [c for j, c in enumerate(cnts)
                 if j != idx and hier[0][j][3] == idx and cv2.contourArea(c) > 50]
        if holes:
            hole_cnt = max(holes, key=cv2.contourArea)

    result = {"H_mm": float(H), "iou": float(best_iou),
              "A_mm2": float(A_out), "shape": shape}
    if hole_cnt is not None:
        H0 = stage_homography(K1, R0, t0, 0.0)
        pts_h = backproject_contour(hole_cnt, H0)
        cxh, cyh, r_i, rms_i = fit_circle(pts_h)
        cxo, cyo, r_o, rms_o = fit_circle(pts)
        A = np.pi * (r_o ** 2 - r_i ** 2)
        result.update({"hole": True, "r_out_mm": float(r_o), "r_in_mm": float(r_i),
                       "rms_circle_out": float(rms_o), "rms_circle_in": float(rms_i),
                       "concentric_err_mm": float(np.hypot(cxo - cxh, cyo - cyh)),
                       "A_mm2": float(A)})
        if shape == "l":
            result["warn"] = "L 块检测到洞，按圆柱扣孔；若不需要请加 --shape l"
    result["V_cm3"] = float(result["A_mm2"] * H / 1000.0)
    return result, dict(hs=hs, vals=vals, cnt=cnt, hole=hole_cnt, H=H)


def measure_pair(left, right, st, stage, shape="auto", undistort=True,
                 thr=0.5, hmin=0.0, hmax=160.0, step=0.5, ref=None):
    K1, D1, K2, D2 = st["K1"], st["D1"], st["K2"], st["D2"]
    if undistort:
        left = cv2.undistort(left, K1, D1)
        right = cv2.undistort(right, K2, D2)
    m1, ref1 = make_mask(left, thr=thr, ref=ref)
    m2, _ = make_mask(right, thr=thr, ref=ref)
    return measure_masks(m1, m2, st, stage, shape=shape,
                         hmin=hmin, hmax=hmax, step=step), m1, m2, ref1


# ---------------------------------------------------------------- selftest
def _synthetic():
    """合成一对剪影，验证几何/正负号/平面扫描。"""
    K = np.array([[4000.0, 0, 1224], [0, 4000.0, 1024], [0, 0, 1]])
    K1 = K.copy()
    K2 = K.copy()
    R = np.eye(3)
    T = np.array([-100.0, 0, 0])          # 右相机在左相机 +x 100mm
    R0 = np.diag([1.0, -1.0, -1.0])       # 相机看 -z；台面 z 向上
    t0 = np.array([0, 0, 500.0])

    out = []
    # L 块：80x80，缺口 30x30 在 +x,+y，高 60
    L = np.array([[-40, -40], [40, -40], [40, 10], [10, 10], [10, 40], [-40, 40]], float)
    H = 60.0
    for name, poly, H, hole in (("L", L, 60.0, None),
                                ("cylinder", None, 70.0, None)):
        size = (2448, 2048)
        ml = np.zeros((size[1], size[0]), np.uint8)
        mr = np.zeros_like(ml)
        if name == "L":
            uv1 = project_stage(poly, H, K1, R0, t0)
            uv2 = project_stage(poly, H, K2, R0, t0, R, T)
            cv2.fillPoly(ml, [np.round(uv1).astype(np.int32)], 255)
            cv2.fillPoly(mr, [np.round(uv2).astype(np.int32)], 255)
        else:
            th = np.linspace(0, 2 * np.pi, 240, endpoint=False)
            circ = np.column_stack([40 * np.cos(th), 40 * np.sin(th)])
            holec = np.column_stack([15 * np.cos(th), 15 * np.sin(th)])
            uv1 = project_stage(circ, H, K1, R0, t0)
            uv2 = project_stage(circ, H, K2, R0, t0, R, T)
            h1 = project_stage(holec, 0.0, K1, R0, t0)
            h2 = project_stage(holec, 0.0, K2, R0, t0, R, T)
            cv2.fillPoly(ml, [np.round(uv1).astype(np.int32)], 255)
            cv2.fillPoly(mr, [np.round(uv2).astype(np.int32)], 255)
            cv2.fillPoly(ml, [np.round(h1).astype(np.int32)], 0)
            cv2.fillPoly(mr, [np.round(h2).astype(np.int32)], 0)
        st = {"K1": K1, "K2": K2, "R": R, "T": T, "D1": np.zeros(5), "D2": np.zeros(5)}
        stage = {"R0": R0, "t0": t0, "n": R0[:, 2].copy(), "d0": float(R0[:, 2] @ t0)}
        res, dbg = measure_masks(ml, mr, st, stage, shape="cylinder" if name == "cylinder" else "l",
                                 hmin=0, hmax=120, step=0.25)
        out.append((name, H, res))
    return out


def run_selftest():
    cases = _synthetic()
    ok = True
    for name, H_true, res in cases:
        dh = abs(res["H_mm"] - H_true)
        if name == "L":
            A_true = 80 * 80 - 30 * 30
            dv = abs(res["V_cm3"] - A_true * H_true / 1000.0)
            print(f"[{name}] H={res['H_mm']:.3f} (真 {H_true})  A={res['A_mm2']:.1f} "
                  f"(真 {A_true})  V={res['V_cm3']:.2f}cm3  IoU={res['iou']:.4f}")
            good = dh < 1.0 and abs(res["A_mm2"] - A_true) / A_true < 0.01
        else:
            A_true = np.pi * (40 ** 2 - 15 ** 2)
            print(f"[{name}] H={res['H_mm']:.3f} (真 {H_true})  r_out={res['r_out_mm']:.2f} "
                  f"r_in={res['r_in_mm']:.2f}  A={res['A_mm2']:.1f} (真 {A_true:.1f})  "
                  f"IoU={res['iou']:.4f}")
            good = dh < 1.0 and abs(res["A_mm2"] - A_true) / A_true < 0.02
        ok = ok and good
        print("   ->", "PASS" if good else "FAIL")
    print("\nSELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", default="")
    ap.add_argument("--right", default="")
    ap.add_argument("--stereo", default="calib/stereo.npz")
    ap.add_argument("--stage", default="calib/stereo_stage.npz")
    ap.add_argument("--shape", choices=["auto", "l", "cylinder"], default="auto")
    ap.add_argument("--thr", type=float, default=0.5)
    ap.add_argument("--hmin", type=float, default=0.0)
    ap.add_argument("--hmax", type=float, default=160.0)
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--out", default="")
    ap.add_argument("--no-undistort", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    st = load_npz(args.stereo)
    stage = load_npz(args.stage)
    a = cv2.imread(args.left, cv2.IMREAD_GRAYSCALE)
    b = cv2.imread(args.right, cv2.IMREAD_GRAYSCALE)
    if a is None or b is None:
        print("读不到图片：", args.left, args.right)
        return 2

    (res, dbg), m1, m2, ref = measure_pair(
        a, b, st, stage, shape=args.shape, undistort=not args.no_undistort,
        thr=args.thr, hmin=args.hmin, hmax=args.hmax, step=args.step)
    print(json.dumps(res, ensure_ascii=False, indent=2))

    if args.out:
        vis = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
        cv2.drawContours(vis, [dbg["cnt"]], -1, (0, 255, 0), 2)
        if dbg["hole"] is not None:
            cv2.drawContours(vis, [dbg["hole"]], -1, (0, 0, 255), 2)
        txt = (f"H={res['H_mm']:.2f}mm  A={res['A_mm2']:.0f}mm2  "
               f"V={res['V_cm3']:.1f}cm3  IoU={res['iou']:.3f}")
        cv2.putText(vis, txt, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        cv2.imwrite(args.out, vis)
        print("debug:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())