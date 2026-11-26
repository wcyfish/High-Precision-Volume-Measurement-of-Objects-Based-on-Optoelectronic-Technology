# 5MP + 12mm 相机：赛题二软件环境与操作手册

本手册对应“基于光电技术的物体体积高精度测量”。目标：在一台 Windows 电脑上，把 5MP 相机、Python/OpenCV、标定和第一次测量跑通。

当前这台机器已经完成第 1–2 步（Python 3.14.6 + venv + OpenCV 5.1），你只需要从第 3 步开始。

---

## 1. 需要安装的软件

| 软件 | 是否必需 | 说明 |
|---|---|---|
| Python 3.14.6 | 已装 | `D:\python\python.exe`，`py -0p` 可看到 |
| VS Code | 推荐 | 免费；装 Python 扩展；比 IDLE 好用 |
| 7-Zip | 可选 | 解压相机 SDK |
| 相机厂商软件 | 视相机而定 | 工业相机（海康 MVS、大恒 Galaxy、Basler pylon、迈德威视 MVViewer）用它锁曝光/增益；普通 UVC 摄像头不需要 |
| Git | 可选 | 版本管理 |

> 不要装 Python 2、32 位 Python、Anaconda 全家桶。Anaconda 会改 PATH，和现有 3.14 打架。

---

## 2. Python 环境（已配好）

### 2.1 现有环境

- 解释器：`C:\Users\86189\Desktop\DSH\work\meas\venv\Scripts\python.exe`
- 已安装：OpenCV 5.1.0.95、numpy 2.5.5、scipy 1.18.1、matplotlib 3.11.2、pandas 3.1.1、openpyxl 3.1.5

验证：

```powershell
cd C:\Users\86189\Desktop\DSH\work\meas
.\venv\Scripts\python.exe -c "import cv2, numpy, scipy; print(cv2.__version__, numpy.__version__, scipy.__version__)"
```

应输出 `5.1.0 2.5.5 1.18.1`。

### 2.2 从零复现（换电脑时）

```powershell
# 1) 安装 Python 3.12/3.14（python.org，勾选 Add python.exe to PATH）
# 2) 建虚拟环境（路径不要有空格）
D:\python\python.exe -m venv C:\work\meas\venv
# 3) 激活
C:\work\meas\venv\Scripts\activate
# 4) 升级 pip（国内镜像）
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
# 5) 装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

`requirements.txt` 就在本目录。

### 2.3 VS Code 配置

1. 安装 VS Code，扩展商店搜 `Python`（Microsoft）安装。
2. `文件 → 打开文件夹` 选 `C:\Users\86189\Desktop\DSH\work\meas`。
3. `Ctrl+Shift+P` → `Python: Select Interpreter` → 选 `.\venv\Scripts\python.exe`。
4. 打开 `camera_test.py`，右上角运行按钮；或终端里 `python camera_test.py`。
5. 终端没自动激活 venv 时，手动执行 `.\venv\Scripts\activate`。

### 2.4 常见安装错误

- `'python' 不是内部或外部命令`：PATH 没加，或装到了 WindowsApps 影子；用绝对路径 `D:\python\python.exe`。
- `pip` SSL/超时：加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`；公司网络换手机热点。
- `No module named cv2`：解释器选错（选到系统 Python），按 2.3 重选。
- `opencv-python` 装不上：Python 版本太新/太旧；用 3.12 建新 venv。

---

## 3. 相机连接与检查

### 3.1 连接

- 5MP 相机优先插 **USB 3.0**（蓝色口），不要经过无源 Hub；线材 ≤1.5m。
- 设备管理器 → `照相机`/`图像设备`，应出现相机名称；黄色感叹号=驱动问题。
- Windows 设置 → 隐私和安全性 → 相机 → 打开“允许桌面应用访问相机”。
- 关掉可能占用相机的程序：相机、Teams、Zoom、OBS、微信视频。

### 3.2 先跑测试脚本

```powershell
cd C:\Users\86189\Desktop\DSH\work\meas
.\venv\Scripts\activate
python camera_test.py --list
```

`--list` 会枚举 0–5 号设备，打印能打开的分辨率。然后：

```powershell
python camera_test.py --width 2592 --height 1944 --fourcc MJPG
```

- 窗口里按 `s` 存一张原图到 `shots/`，按 `q` 退出。
- 脚本会打印实际分辨率、FPS、曝光/增益，以及“手动曝光是否生效”。

> 当前这台机器上的 `USB2.0 HD UVC WebCam` 在 OpenCV 里打不开（隐私已允许、设备状态 OK），说明它可能被占用、被物理遮挡，或本身就是笔记本内置摄像头。把 5MP 相机插上后重新跑 `--list`；如果仍打不开，看第 8 节。

### 3.3 分辨率与带宽

5MP = 2592×1944。USB2 带宽只够：

- MJPG：2592×1944 @ 15–30fps（压缩，边缘有振铃）
- YUY2：2592×1944 @ 2–5fps（无压缩，边缘最准）

静态测量用 YUY2 更准；预览/对焦用 MJPG 更流畅。脚本里 `--fourcc YUY2` 或 `MJPG` 切换。

---

## 4. 相机参数怎么设

### 4.1 参数表

| 参数 | 建议值 | 原因 |
|---|---|---|
| 分辨率 | 2592×1944 | 全分辨率，不要裁剪/缩放 |
| FourCC | YUY2（测量）/ MJPG（预览） | JPEG 振铃会偏置边缘 |
| 帧率 | 5–10 fps | 静态，低帧率换更长曝光 |
| 曝光 | 手动，按场景调 | 自动曝光会让两拍亮度不一致 |
| 增益 | 0（最低） | 增益=噪声 |
| 白平衡 | 手动锁定（如 5000K） | 单帧双通道必须锁 |
| 伽马 | 1.0 / 关闭 | 伽马会改变边缘灰度分布 |
| 锐化 | 0 / 关闭 | 锐化会偏置边缘 |
| 降噪 | 0 / 关闭 | 降噪会抹掉激光线 |
| 背光 | 恒流，预热 5–10 min | 亮度漂移直接影响阈值 |

### 4.2 曝光怎么调

两拍分别设：

1. **剪影帧**：背光开、激光关。调曝光到白场灰度 **200–230**（不要到 255 饱和），物体呈黑。
2. **激光帧**：背光关（或降到很暗）、激光开。调曝光到激光线峰值 **200–240**（不要饱和），背景尽量黑。

如果相机不支持手动曝光（UVC 常见），三个办法：

- 用厂商软件锁曝光，再让 OpenCV 读流；
- 固定光照 + 镜头光圈固定，让自动曝光“没得调”；
- 换一台支持 UVC 手动曝光的工业相机（海康/大恒/Basler）。

脚本里的 `--exposure`、`--gain` 只是“尝试设置”，是否生效要看打印的读回值。

### 4.3 对焦与光圈

- 12mm 镜头、工作距离 250mm 时，视野约 119–183mm（取决于传感器尺寸，见 4.4）。
- 光圈先设 **f/8**，对焦到物体中部（约 215–220mm），再收到 **f/16** 看景深。
- 12mm、WD250、允许弥散 2 像素时：f/8 景深约 34mm，f/11 约 46mm，f/16 约 66mm，f/22 约 91mm。
- 60mm 高的物体（顶面 190mm、台面 250mm）建议 **f/16 + 对焦 220mm**；若顶面边缘发虚，收到 f/22 再试。
- 光圈太小衍射会糊：f/16 在 2.2µm 像素上已经有明显衍射，先保证边缘位置对称，再谈锐度。

### 4.4 视场够不够

`视野宽度 ≈ 工作距离 × 传感器宽度 / 焦距`

| 传感器 | 尺寸(mm) | WD250 视野(mm) | 像素当量(mm/px) |
|---|---|---|---|
| 1/2.5" | 5.7×4.3 | 119×90 | 0.046 |
| 1/1.8" | 7.2×5.4 | 150×113 | 0.058 |
| 2/3" | 8.8×6.6 | 183×138 | 0.071 |

100mm 物体要留 ≥10% 余量：1/2.5" 在 WD250 只有 9mm 余量（每边 4.5mm），很紧；1/1.8" 和 2/3" 才舒服。不够就：升高相机到 WD300、换 8mm 镜头、或换大靶面相机。

实测方法：台面上放一把直尺，拍一张，数 100mm 占多少像素，反算 mm/px。

---

## 5. 标定

### 5.1 棋盘格

- 9×12 内角点（即 10×13 个方格），格距 10mm；A4 打印。
- 打印后 **用卡尺量 10 个格的总长**（例如 99.6mm），实际格距 = 99.6/10 = 9.96mm；标定时用这个值。
- 纸会翘：用喷胶贴在 3mm 亚克力/玻璃上，或贴 5mm 雪弗板；平整度 <0.1mm。
- 表面哑光，避免反光。

### 5.2 采图

```powershell
python capture_calib.py --pattern 9x12 --square 9.96 --count 20
```

- 板放在相机前，覆盖画面中心、四角、边缘；
- 姿态：正对、左右倾斜 ±20–30°、上下倾斜 ±20–30°、旋转 0°/90°；
- 每张都要完整、清晰、无遮挡；不要运动模糊；
- 按 `空格` 保存，按 `q` 退出；保存到 `calib/images/`。

### 5.3 内参

```powershell
python calibrate_intrinsics.py --dir calib/images --pattern 9x12 --square 9.96
```

- 输出 `calib/intrinsics.npz`（K、dist、rms、image_size）。
- 验收：重投影 RMS **< 0.3 px**；>0.5 px 重拍（板不平、模糊、姿态太单一）。
- 同时打印水平/垂直视场角，核对 4.4 的估算。

### 5.4 台面位姿

- 标定板平放在玻璃台面上，拍一张，`solvePnP(..., SOLVEPNP_IPPE)` 得 R、t。
- 板顶面即 z=0；若板厚 t（卡尺量），物体放在玻璃上时物体底面 z=−t，高度 H=z_top+t。
- 更稳的做法：做一块 3mm 的“测量板”，物体永远放在板上，z=0 就是板顶，不用每次减厚度。

### 5.5 激光平面

- 五级台阶块（10/20/30/40/50mm，卡尺实测高度），放在玻璃上，一字线激光横穿五级。
- 每个台阶顶面的激光线像素 → 反投影到该台阶的 z → 得三维点；SVD 拟合平面 n·X=d。
- 验收：拟合残差 <0.1mm；用量块复测高度 <0.2mm。

---

## 6. 第一次测量

1. 物体放在 50×50mm 定位框内，保证跨光轴（相机正下方）。
2. 背光开、激光关，拍剪影；二值化、取外轮廓，反投影到 z=H 算面积 A。
3. 背光关、激光开，拍线；取物体顶面的线，算 H。
4. V = A·H；与卡尺/排水法对比，记录相对误差。
5. 同一件重复 10 次，看极差；目标 <1%。

---

## 7. 文件清单

| 文件 | 用途 |
|---|---|
| `camera_test.py` | 枚举/预览/抓图/打印相机参数 |
| `capture_calib.py` | 棋盘格采图 |
| `calibrate_intrinsics.py` | 内参标定 + RMS + 视场 |
| `requirements.txt` | 依赖 |
| `calib/` | 标定图与结果 |
| `shots/` | 抓拍图 |

---

## 8. 常见问题

**Q1：`backend is generally available but can't be used to capture by index`**

按顺序排查：

1. 关掉相机/Teams/Zoom/OBS/微信；
2. 设置 → 隐私 → 相机 → 允许桌面应用；
3. 设备管理器 → 相机 → 禁用再启用；卸载设备后“扫描硬件改动”；
4. 换 USB 口（直插主板，不过 Hub）；换线；
5. `python camera_test.py --list` 看 0–5 号哪个能开；
6. 用 Windows“相机”应用试；相机应用能开、OpenCV 不能，换 `--backend dshow/msmf` 或换 OpenCV 版本；
7. 工业相机装厂商 SDK，用厂商的 Python 接口（UVC 可能只是它的第二模式）。

**Q2：5MP 只有 2–5fps**

USB2 带宽不够。测量用 YUY2 低帧率没问题；要流畅预览换 MJPG，或换 USB3 口/线。

**Q3：画面全黑/全白**

全黑：镜头盖、光圈太小、曝光太短、背光没开。全白：曝光太长、增益太高、背光太亮。先自动曝光看一眼，再锁手动。

**Q4：标定 RMS 大**

板不平（纸翘）、图模糊、姿态太单一、格距填错、角点检测到了错误棋盘。看每张误差，删掉最差的 2–3 张重标。

**Q5：激光线太粗/太暗**

线激光的焦距没调（拧镜头前端），或曝光不对；峰值 200–240，不要 255。背景光要压掉。

---

## 9. 参考

- OpenCV 相机标定：https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html
- 针孔模型与畸变：https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html
- 棋盘格生成：https://calib.io/pages/camera-calibration-pattern-generator（选 9×12、10mm、PDF）