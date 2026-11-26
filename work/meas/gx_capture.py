# -*- coding: utf-8 -*-
"""大恒 Galaxy 相机取图 / 曝光增益配置（MER2-501-79U3M 等 USB3 黑白机）

用法：
  python gx_capture.py --list
  python gx_capture.py --exposure-ms 20 --gain 0
  python gx_capture.py --sweep                 # 5/10/20/40/80ms 各拍一张
  python gx_capture.py --sn FHX25100182 --exposure-ms 5 --frames 5

说明：
  - 需要先安装 Galaxy SDK；脚本自动把本地补丁版 gxipy 加入 sys.path
  - 相机被 GalaxyView 占用时打不开，先完全退出 GalaxyView
  - 输出 Mono8 PNG，文件名带曝光时间，例如 gx_test_20ms_0.png
"""
import os
import sys
import time
import argparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 本地补丁版 gxipy（原版 DeviceManager.py 里 from numpy.compat import long
# 在 NumPy 2.x 下会 ImportError，已改为 long = int）
SDK_PY = r"C:\Users\86189\Desktop\DSH\work\meas\sdk_py"
if SDK_PY not in sys.path:
    sys.path.insert(0, SDK_PY)

_SDK = r"C:\Program Files\Daheng Imaging\GalaxySDK"
# DSH 进程可能早于 SDK 安装启动，继承不到 SDK 写入的机器级环境变量；
# 这里显式补齐，否则 GXInitLib 会报 "Failed to get GenTL path"。
os.environ["GALAXY_GENICAM_ROOT"] = os.path.join(_SDK, "GenICam")
os.environ["GALAXY_GENICAM_CACHE"] = r"C:\ProgramData\Galaxy\xml\cache"
os.environ["GENICAM_GENTL64_PATH"] = os.path.join(_SDK, "GenTL", "Win64")
os.environ["GENICAM_GENTL32_PATH"] = os.path.join(_SDK, "GenTL", "Win32")

# gxwrapper 用 WinDLL('GxIAPI.dll', winmode=0)，winmode=0 走老式搜索顺序，
# 必须把 APIDll 与 GenICam 的 bin 目录放进 PATH，否则依赖 DLL 找不到。
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
    ap.add_argument("--list", action="store_true", help="只枚举相机")
    ap.add_argument("--sn", default="", help="按序列号打开，默认按索引")
    ap.add_argument("--index", type=int, default=1, help="1 起的设备索引")
    ap.add_argument("--exposure-ms", type=float, default=20.0)
    ap.add_argument("--gain", type=float, default=0.0)
    ap.add_argument("--frames", type=int, default=2)
    ap.add_argument("--sweep", action="store_true", help="按 5/10/20/40/80ms 扫曝光")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "shots", "gx_test.png"))
    args = ap.parse_args()

    dm = gx.DeviceManager()
    n, infos = dm.update_all_device_list()
    print(f"找到 {n} 台相机")
    for i, info in enumerate(infos, 1):
        print(f"  [{i}] {info.get('model_name')}  SN={info.get('sn')}  id={info.get('device_id')}")
    if args.list or n == 0:
        return

    try:
        cam = dm.open_device_by_sn(args.sn) if args.sn else dm.open_device_by_index(args.index)
    except Exception as e:
        print(f"打开相机失败：{e}")
        print("如果 GalaxyView 正开着，先完全退出它再试。")
        return

    try:
        print("已打开:", cam.DeviceModelName.get(), cam.DeviceSerialNumber.get())
    except Exception:
        pass

    def set_feature(name, value):
        try:
            getattr(cam, name).set(value)
            print(f"  {name} = {value}")
        except Exception as e:
            print(f"  ! {name} 设置失败: {e}")

    set_feature("ExposureAuto", 0)   # GxAutoEntry.OFF
    set_feature("GainAuto", 0)       # GxAutoEntry.OFF
    set_feature("ExposureTime", args.exposure_ms * 1000.0)  # us
    set_feature("Gain", args.gain)
    for name, value in (("Gamma", 1.0), ("BlackLevel", 0.0), ("Sharpness", 0.0)):
        try:
            getattr(cam, name).set(value)
        except Exception:
            pass

    exps = [5, 10, 20, 40, 80] if args.sweep else [args.exposure_ms]
    cam.stream_on()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    base, ext = os.path.splitext(args.out)
    saved = []
    for e in exps:
        cam.ExposureTime.set(e * 1000.0)
        time.sleep(0.2)
        for k in range(args.frames):
            raw = cam.data_stream[0].get_image(timeout=2000)
            if raw is None:
                print(f"exp {e:g}ms frame {k}: 取图超时")
                continue
            arr = raw.get_numpy_array()
            if arr is None:
                print(f"exp {e:g}ms frame {k}: 不支持的像素格式 {raw.get_pixel_format()}")
                continue
            arr = np.asarray(arr)
            p = f"{base}_{e:g}ms_{k}{ext}"
            cv2.imwrite(p, arr)
            saved.append(p)
            print(f"exp {e:g}ms frame {k}: {arr.shape} {arr.dtype} "
                  f"min={arr.min()} max={arr.max()} mean={arr.mean():.1f} -> {p}")
    cam.stream_off()
    cam.close_device()
    print("done:", ", ".join(saved))


if __name__ == "__main__":
    main()