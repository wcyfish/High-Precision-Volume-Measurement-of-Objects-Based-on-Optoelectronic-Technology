# -*- coding: utf-8 -*-
"""大恒 Galaxy 相机 + 棋盘格内参采集（gxipy 版，替代 OpenCV VideoCapture 的 capture_calib.py）

用法：
  python gx_calib_capture.py --exposure-ms 270 --count 20
  python gx_calib_capture.py --pattern 9x12 --square 9.96 --out calib/images

操作：
  - 相机被 GalaxyView 占用时打不开，先完全退出 GalaxyView
  - 窗口里摆一个姿态，看到绿色角点后按 SPACE 保存；q / ESC 退出
  - 建议 15–20 个姿态：远/近、左/右、上/下、绕光轴转 ±30°
"""
import os
import sys
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sn", default="")
    ap.add_argument("--index", type=int, default=1)
    ap.add_argument("--exposure-ms", type=float, default=270.0)
    ap.add_argument("--gain", type=float, default=0.0)
    ap.add_argument("--pattern", default="9x12", help="内角点数，如 9x12")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "calib", "images"))
    args = ap.parse_args()

    cols, rows = (int(v) for v in args.pattern.lower().split("x"))
    pattern = (cols, rows)

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
    try:
        while saved < args.count:
            raw = cam.data_stream[0].get_image(timeout=2000)
            if raw is None:
                continue
            arr = np.asarray(raw.get_numpy_array())
            if arr is None:
                continue
            gray = arr if arr.ndim == 2 else cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
            ok, corners = cv2.findChessboardCorners(
                gray, pattern,
                flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
            disp = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            if ok:
                cv2.drawChessboardCorners(disp, pattern, corners, ok)
            scale = min(1.0, 1200.0 / gray.shape[1])
            if scale < 1.0:
                disp = cv2.resize(disp, None, fx=scale, fy=scale)
            text = f"saved {saved}/{args.count}  {'OK' if ok else 'no board'}  SPACE=save  q=quit"
            cv2.putText(disp, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 255, 0) if ok else (0, 0, 255), 2)
            cv2.imshow(win, disp)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):
                break
            if k == 32 and ok:
                saved += 1
                fn = os.path.join(args.out, f"calib_{saved:02d}.png")
                cv2.imwrite(fn, gray)
                print(f"  saved {fn}  ({saved}/{args.count})")
    finally:
        cam.stream_off()
        cam.close_device()
        cv2.destroyAllWindows()

    print(f"共保存 {saved} 张到 {args.out}")


if __name__ == "__main__":
    main()