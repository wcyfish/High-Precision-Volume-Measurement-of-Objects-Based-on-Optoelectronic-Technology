#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""棋盘格采图：按空格保存，q 退出。

用法：
  python capture_calib.py --pattern 9x12 --square 9.96 --count 20
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from camera_test import open_camera


def parse_pattern(s: str):
    a, b = s.lower().split("x")
    return int(a), int(b)


def find_corners(gray, pattern):
    """优先 findChessboardCornersSB（更稳），失败退回经典法 + 亚像素。"""
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
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--width", type=int, default=2592)
    ap.add_argument("--height", type=int, default=1944)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--pattern", default="9x12", help="内角点数，如 9x12")
    ap.add_argument("--square", type=float, default=10.0, help="实测格距 mm")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--out", default="calib/images")
    args = ap.parse_args()

    pattern = parse_pattern(args.pattern)
    os.makedirs(args.out, exist_ok=True)

    cap, backend = open_camera(args.index, args.width, args.height, args.fourcc)
    if cap is None:
        print("打不开相机，见 README 第 8 节 Q1")
        return 2
    print(f"backend={backend}  pattern={pattern}  square={args.square}mm")
    print("把棋盘格放满画面不同位置/角度；空格保存，q 退出")

    saved = 0
    while saved < args.count:
        ok, frame = cap.read()
        if not ok or frame is None:
            print("读帧失败")
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ok_cb, corners = find_corners(gray, pattern)
        disp = frame.copy()
        if ok_cb:
            cv2.drawChessboardCorners(disp, pattern, corners, ok_cb)
        h, w = disp.shape[:2]
        if w > 1280:
            disp = cv2.resize(disp, (1280, int(h * 1280 / w)), interpolation=cv2.INTER_AREA)
        cv2.putText(disp, f"saved {saved}/{args.count}  {'OK' if ok_cb else 'no board'}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 255, 0) if ok_cb else (0, 0, 255), 2)
        cv2.imshow("calib", disp)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" ") and ok_cb:
            saved += 1
            fn = os.path.join(args.out, f"calib_{saved:02d}.png")
            cv2.imwrite(fn, frame)
            print("保存", fn)
            time.sleep(0.2)

    cap.release()
    cv2.destroyAllWindows()
    print(f"共保存 {saved} 张到 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())