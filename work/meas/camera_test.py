#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""5MP 相机检查/预览/抓图。

用法：
  python camera_test.py --list
  python camera_test.py --width 2592 --height 1944 --fourcc MJPG
  python camera_test.py --index 1 --width 2592 --height 1944 --fourcc YUY2 --exposure -6

窗口按键：s 存图（原分辨率），q 退出。
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

BACKENDS = [
    ("MSMF", cv2.CAP_MSMF),
    ("DSHOW", cv2.CAP_DSHOW),
    ("ANY", cv2.CAP_ANY),
]


def fourcc(code: str) -> int:
    try:
        return cv2.VideoWriter_fourcc(*code)
    except Exception:
        return cv2.VideoWriter.fourcc(*code)


def open_camera(index=0, width=2592, height=1944, code="MJPG", fps=30, exposure=None, gain=None):
    """依次尝试 MSMF / DSHOW / ANY，返回 (cap, backend_name)。"""
    for name, backend in BACKENDS:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        if code:
            cap.set(cv2.CAP_PROP_FOURCC, fourcc(code))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if fps:
            cap.set(cv2.CAP_PROP_FPS, fps)
        if exposure is not None:
            # 0.25 = DSHOW 手动；1.0 = MSMF 手动（不同后端不一样，读回值才可信）
            for auto_val in (0.25, 1.0):
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, auto_val)
                time.sleep(0.05)
                cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
                time.sleep(0.15)
                ok, _ = cap.read()
                if ok:
                    break
        if gain is not None:
            cap.set(cv2.CAP_PROP_GAIN, gain)
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap, name
        cap.release()
    return None, None


def read_fourcc(cap) -> str:
    v = int(cap.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


def dump_props(cap):
    props = [
        ("width", cv2.CAP_PROP_FRAME_WIDTH),
        ("height", cv2.CAP_PROP_FRAME_HEIGHT),
        ("fps", cv2.CAP_PROP_FPS),
        ("exposure", cv2.CAP_PROP_EXPOSURE),
        ("auto_exposure", cv2.CAP_PROP_AUTO_EXPOSURE),
        ("gain", cv2.CAP_PROP_GAIN),
        ("brightness", cv2.CAP_PROP_BRIGHTNESS),
        ("contrast", cv2.CAP_PROP_CONTRAST),
        ("saturation", cv2.CAP_PROP_SATURATION),
        ("gamma", cv2.CAP_PROP_GAMMA),
        ("sharpness", cv2.CAP_PROP_SHARPNESS),
        ("white_balance", cv2.CAP_PROP_WB_TEMPERATURE),
    ]
    print("---- 相机属性（读回值）----")
    print(f"  fourcc = {read_fourcc(cap)}")
    for label, prop in props:
        try:
            print(f"  {label:14s} = {cap.get(prop):.3f}")
        except Exception:
            pass
    print("----------------------------")


def list_devices(max_index=6):
    print("枚举相机（0..%d）..." % (max_index - 1))
    found = 0
    for idx in range(max_index):
        cap = None
        for name, backend in BACKENDS:
            cap = cv2.VideoCapture(idx, backend)
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    print(f"  index {idx}: backend={name}, frame={frame.shape[1]}x{frame.shape[0]}")
                    found += 1
                    cap.release()
                    break
            cap.release()
    if not found:
        print("  没有找到可打开的相机。见 README 第 8 节 Q1。")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--width", type=int, default=2592)
    ap.add_argument("--height", type=int, default=1944)
    ap.add_argument("--fourcc", default="MJPG", help="MJPG / YUY2 / 空字符串")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--exposure", type=float, default=None, help="尝试手动曝光值，如 -6")
    ap.add_argument("--gain", type=float, default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-window", action="store_true")
    args = ap.parse_args()

    if args.list:
        list_devices()
        return 0

    cap, backend = open_camera(
        args.index, args.width, args.height, args.fourcc, args.fps, args.exposure, args.gain
    )
    if cap is None:
        print("打不开相机。排查：\n"
              "  1) 相机是否插好、是否被相机/Teams/Zoom/OBS 占用\n"
              "  2) 设置 → 隐私 → 相机 → 允许桌面应用\n"
              "  3) 设备管理器里是否有黄色感叹号\n"
              "  4) 试 python camera_test.py --list 和 --index 1\n"
              "  5) 工业相机请装厂商 SDK")
        return 2

    print(f"已打开：backend={backend}, index={args.index}")
    dump_props(cap)

    os.makedirs("shots", exist_ok=True)
    if args.no_window:
        ok, frame = cap.read()
        if ok:
            cv2.imwrite(os.path.join("shots", "snapshot.png"), frame)
            print("已保存 shots/snapshot.png", frame.shape)
        cap.release()
        return 0

    cv2.namedWindow("camera", cv2.WINDOW_NORMAL)
    print("按键：s 存图，q 退出")
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            print("读帧失败")
            break
        h, w = frame.shape[:2]
        disp = frame
        if w > 1280:
            disp = cv2.resize(frame, (1280, int(h * 1280 / w)), interpolation=cv2.INTER_AREA)
        cv2.putText(disp, f"{w}x{h}  mean={frame.mean():.1f}  {backend}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow("camera", disp)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            n += 1
            fn = os.path.join("shots", f"snap_{n:03d}.png")
            cv2.imwrite(fn, frame)
            print("已保存", fn, frame.shape)

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())