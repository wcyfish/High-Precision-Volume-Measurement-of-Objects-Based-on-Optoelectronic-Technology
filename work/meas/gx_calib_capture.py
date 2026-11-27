# -*- coding: utf-8 -*-
"""大恒 Galaxy 相机 + 棋盘格内参采集（gxipy 版）

用法：
  python gx_calib_capture.py --exposure-ms 200 --count 20
  python gx_calib_capture.py --pattern 11x8 --square 20.01

操作：
  - 相机被 GalaxyView 占用时打不开，先完全退出 GalaxyView
  - 窗口里摆姿态，看到绿色角点后按 SPACE 保存；q / ESC 退出
  - pattern 默认 auto：自动在 (11,8)/(8,11)/(9,12)/(12,9) 里试，
    找到后锁定，避免“板子在画面里但一直 no board”

性能说明：
  - 检测在 0.5 倍缩略图上做，保存的仍是 2448×2048 原图
  - 200 ms 曝光本身最多 5 fps；预览帧率低主要是曝光时间，不是代码卡死
  - 关窗口时先停流再 destroyAllWindows，避免 Python “无响应”
"""
import os
import sys
import time
import argparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SDK_PY = r"C:\Users\86189\Desktop\DSH\work\meas\sdk_py"
if SDK_PY not in sys.path:
    sys.path.insert(0, SDK_PY)

_SDK = r"C:\Program Files\Daheng Imaging\GalaxySDK"
os.environ["GALAXY_GENICAM_ROOT"] = os.path.join(_SDK, "GenICam")
os.environ["GALAXY_GENICAM_CACHE"] = r"C:\ProgramData\Galaxy\xml\cache"
os.environ["GENICAM_GENTL64_PATH"] = os.path.join(_SDK, "GenTL", "Win64")
os.environ["GENICAM_GENTL32_PATH"] = os.path.join(_SDK, "GenTL", "Win32")
for _d in (os.path.join(_SDK, "APIDll", "Win64"),
           os.path.join(_SDK, "GenICam", "bin", "Win64_x64"),
           os.path.join(_SDK, "GenTL", "Win64")):
    if os.path.isdir(_d):
        os.add_dll_directory(_d)
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")

import numpy as np
import cv2
import gxipy as gx

CANDIDATES = [(11, 8), (8, 11), (9, 12), (12, 9)]


def detect_board(gray, candidates):
    """返回 (pattern, corners_full) 或 (None, None)。

    先在 0.5 倍图上试经典法（约 70 ms），失败再试 SB(ACCURACY)；
    仍失败才回到原图试。找到后把角点乘回原图坐标。
    """
    h, w = gray.shape
    scale = 0.5
    small = cv2.resize(gray, (int(w * scale), int(h * scale)),
                       interpolation=cv2.INTER_AREA)
    for p in candidates:
        for im, s in ((small, scale), (gray, 1.0)):
            # 经典法在 0.5 倍图上约 70 ms，先用它；SB 的 EXHAUSTIVE 在本机要 7.9 s，
            # 绝对不能放在预览循环里，这里只用 ACCURACY。
            try:
                ok, corners = cv2.findChessboardCorners(
                    im, p, flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
            except Exception:
                ok = False
            if ok:
                return p, corners.astype(np.float32) / s
            try:
                ok, corners = cv2.findChessboardCornersSB(
                    im, p, flags=cv2.CALIB_CB_ACCURACY)
            except Exception:
                ok = False
            if ok:
                return p, corners.astype(np.float32) / s
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sn", default="")
    ap.add_argument("--index", type=int, default=1)
    ap.add_argument("--exposure-ms", type=float, default=200.0)
    ap.add_argument("--gain", type=float, default=0.0)
    ap.add_argument("--pattern", default="auto", help="auto 或 11x8 这种内角点数")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "calib", "images"))
    args = ap.parse_args()

    if args.pattern.lower() == "auto":
        candidates = CANDIDATES
    else:
        a, b = args.pattern.lower().split("x")
        candidates = [(int(a), int(b))]

    dm = gx.DeviceManager()
    n, infos = dm.update_all_device_list()
    print(f"找到 {n} 台相机")
    for i, info in enumerate(infos, 1):
        print(f"  [{i}] {info.get('model_name')}  SN={info.get('sn')}")
    if n == 0:
        return

    try:
        cam = dm.open_device_by_sn(args.sn) if args.sn else dm.open_device_by_index(args.index)
    except Exception as e:
        print(f"打开相机失败：{e}")
        print("如果 GalaxyView 正开着，先完全退出它。")
        return

    for name, value in (("ExposureAuto", 0), ("GainAuto", 0),
                        ("ExposureTime", args.exposure_ms * 1000.0), ("Gain", args.gain)):
        try:
            getattr(cam, name).set(value)
            print(f"  {name} = {value}")
        except Exception as e:
            print(f"  ! {name}: {e}")

    os.makedirs(args.out, exist_ok=True)
    cam.stream_on()
    win = "gx calib"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    saved = 0
    locked = None
    miss = 0
    fps = 0.0
    last = time.time()
    try:
        while saved < args.count:
            try:
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except Exception:
                break

            raw = cam.data_stream[0].get_image(timeout=500)
            if raw is None:
                continue
            arr = np.asarray(raw.get_numpy_array())
            if arr is None:
                continue
            gray = arr if arr.ndim == 2 else cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

            now = time.time()
            dt = now - last
            last = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 / dt if fps else 1.0 / dt

            if locked is None:
                pattern, corners = detect_board(gray, candidates)
                if pattern is not None:
                    locked = pattern
                    miss = 0
            else:
                pattern, corners = detect_board(gray, [locked])
                if pattern is None:
                    miss += 1
                    if miss >= 10:
                        locked = None
                else:
                    miss = 0

            dscale = 1200.0 / gray.shape[1]
            disp = cv2.resize(gray, None, fx=dscale, fy=dscale,
                              interpolation=cv2.INTER_AREA)
            disp = cv2.cvtColor(disp, cv2.COLOR_GRAY2BGR)
            if pattern is not None and corners is not None:
                cv2.drawChessboardCorners(disp, pattern, corners * dscale, True)

            ok = pattern is not None
            text = (f"saved {saved}/{args.count}  {'OK ' + str(pattern) if ok else 'no board'}"
                    f"  {fps:4.1f} fps  SPACE=save  q=quit")
            cv2.putText(disp, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 0) if ok else (0, 0, 255), 2)
            cv2.imshow(win, disp)

            k = cv2.waitKey(5) & 0xFF
            if k in (27, ord("q")):
                break
            if k == 32 and ok:
                saved += 1
                fn = os.path.join(args.out, f"calib_{saved:02d}.png")
                cv2.imwrite(fn, gray)
                print(f"  saved {fn}  ({saved}/{args.count})  pattern={pattern}")
    finally:
        try:
            cam.stream_off()
        finally:
            cam.close_device()
        cv2.destroyAllWindows()
        cv2.waitKey(1)

    print(f"共保存 {saved} 张到 {args.out}")


if __name__ == "__main__":
    main()