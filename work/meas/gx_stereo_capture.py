# -*- coding: utf-8 -*-
"""双目采集：两台大恒 USB3 黑白相机同步/顺序取图。

用法：
  python gx_stereo_capture.py --list
  python gx_stereo_capture.py --sn-left FHX25100182 --sn-right NV0200110359 \
      --exposure-ms 200 --out calib/stereo
  python gx_stereo_capture.py --pairs 20 --interval 1.0 --out calib/stereo

操作：
  - 先在 GalaxyView 里确认两台都能出图、焦距/光圈/曝光已固定，再完全退出 GalaxyView
  - 交互模式：窗口里摆棋盘，两台都看到后按 SPACE 存一对；q / ESC 退出
  - 自动模式（--pairs N）：每隔 --interval 秒存一对，适合静态棋盘快速采 20 对
  - 输出 left/pair_0001.png、right/pair_0001.png（Mono8）
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


def open_cam(dm, sn, index):
    if sn:
        return dm.open_device_by_sn(sn)
    return dm.open_device_by_index(index)


def configure(cam, exposure_ms, gain):
    for name, value in (("ExposureAuto", 0), ("GainAuto", 0),
                        ("ExposureTime", exposure_ms * 1000.0), ("Gain", gain)):
        try:
            getattr(cam, name).set(value)
        except Exception as e:
            print(f"  ! {name}: {e}")


def grab(cam, timeout=1000):
    raw = cam.data_stream[0].get_image(timeout=timeout)
    if raw is None:
        return None
    arr = raw.get_numpy_array()
    if arr is None:
        return None
    arr = np.asarray(arr)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return arr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--sn-left", default="")
    ap.add_argument("--sn-right", default="")
    ap.add_argument("--index-left", type=int, default=1)
    ap.add_argument("--index-right", type=int, default=2)
    ap.add_argument("--exposure-ms", type=float, default=200.0)
    ap.add_argument("--gain", type=float, default=0.0)
    ap.add_argument("--pairs", type=int, default=0, help="0=交互，N=自动存 N 对")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "calib", "stereo"))
    args = ap.parse_args()

    dm = gx.DeviceManager()
    n, infos = dm.update_all_device_list()
    print(f"找到 {n} 台相机")
    for i, info in enumerate(infos, 1):
        print(f"  [{i}] {info.get('model_name')}  SN={info.get('sn')}  id={info.get('device_id')}")
    if args.list or n == 0:
        return
    if n < 2:
        print("只找到 1 台。双目需要两台：检查第二台的 USB3 线/供电，先在 GalaxyView 里确认能出图。")
        return

    left = right = None
    try:
        left = open_cam(dm, args.sn_left, args.index_left)
        right = open_cam(dm, args.sn_right, args.index_right)
        print("左:", left.DeviceModelName.get(), left.DeviceSerialNumber.get())
        print("右:", right.DeviceModelName.get(), right.DeviceSerialNumber.get())
        configure(left, args.exposure_ms, args.gain)
        configure(right, args.exposure_ms, args.gain)

        os.makedirs(os.path.join(args.out, "left"), exist_ok=True)
        os.makedirs(os.path.join(args.out, "right"), exist_ok=True)

        left.stream_on()
        right.stream_on()
        for _ in range(3):          # 丢掉前几帧，等自动项稳定
            grab(left)
            grab(right)

        win = "stereo  L | R"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        saved = 0
        last_save = 0.0
        try:
            while True:
                try:
                    if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                        break
                except Exception:
                    break
                t0 = time.time()
                a = grab(left)
                b = grab(right)
                if a is None or b is None:
                    continue
                h = 600
                da = cv2.resize(a, (int(a.shape[1] * h / a.shape[0]), h))
                db = cv2.resize(b, (int(b.shape[1] * h / b.shape[0]), h))
                disp = np.hstack([cv2.cvtColor(da, cv2.COLOR_GRAY2BGR),
                                  cv2.cvtColor(db, cv2.COLOR_GRAY2BGR)])
                cv2.putText(disp, "LEFT", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                            (0, 255, 0), 2)
                cv2.putText(disp, "RIGHT", (da.shape[1] + 10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            1.0, (0, 255, 0), 2)
                cv2.putText(disp, f"saved {saved}  {'SPACE=save  q=quit' if args.pairs == 0 else f'auto {args.pairs}'}",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.imshow(win, disp)

                k = cv2.waitKey(5) & 0xFF
                if k in (27, ord("q")):
                    break
                do_save = False
                if args.pairs == 0 and k == 32:
                    do_save = True
                elif args.pairs > 0 and saved < args.pairs and time.time() - last_save >= args.interval:
                    do_save = True
                if do_save:
                    saved += 1
                    fn_l = os.path.join(args.out, "left", f"pair_{saved:04d}.png")
                    fn_r = os.path.join(args.out, "right", f"pair_{saved:04d}.png")
                    cv2.imwrite(fn_l, a)
                    cv2.imwrite(fn_r, b)
                    last_save = time.time()
                    print(f"  saved {saved}  {a.shape}  {os.path.basename(fn_l)}")
                if args.pairs > 0 and saved >= args.pairs:
                    time.sleep(0.2)
                    break
        finally:
            cv2.destroyAllWindows()
            cv2.waitKey(1)
    finally:
        for cam in (left, right):
            if cam is not None:
                try:
                    cam.stream_off()
                except Exception:
                    pass
                try:
                    cam.close_device()
                except Exception:
                    pass
        print(f"共保存 {saved if 'saved' in dir() else 0} 对到 {args.out}")


if __name__ == "__main__":
    main()