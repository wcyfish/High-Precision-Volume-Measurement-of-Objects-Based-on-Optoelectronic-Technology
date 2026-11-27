# 双目双剪影 + 平面扫描（赛题二）

这套脚本用两台 5MP 黑白相机（MER2-501-79U3M / MER-503-36U3M）从上方拍背光剪影，
不依赖 SGBM（PLA 无纹理），用“平面扫描 + IoU”求高度，再算体积。

## 0. 硬件与固定参数

| 项 | 值 |
|---|---|
| 基线 | 80–120 mm（模型按 100 mm） |
| 镜头 | 两支 12 mm C 口，手动光圈 f/8 |
| 工作距离 | 镜头前到台面 480–520 mm（模型 496 mm） |
| 曝光 | 手动 200–250 ms（先试 200 ms） |
| 增益 | 0 |
| 光源 | 背光常亮（本方案不用激光） |
| 台面 | 玻璃上表面定义为 z=0 |

两台相机都装好、调好焦、锁光圈后，**完全退出 GalaxyView**（它会占用相机）。

## 1. 采标定对（棋盘格）

棋盘：9×12 格、格距 20.01 mm → 内角点 **11×8**。

```powershell
cd C:\Users\86189\Desktop\DSH\work\meas
.\venv312\Scripts\python.exe gx_stereo_capture.py --pairs 20 --interval 1.0 `
  --out calib\stereo
```

摆 15–20 个姿态：上下左右、四角、倾斜 ±30°，**两台相机都要看到完整棋盘**。
交互模式（`--pairs 0`）按 SPACE 存一对，适合手动摆。

检查：`calib\stereo\left\pair_0001.png` 与 `right\pair_0001.png` 必须同一姿态。

## 2. 台面位姿

棋盘**平放在玻璃上**，左右各拍一张：

```powershell
.\venv312\Scripts\python.exe gx_stereo_capture.py --pairs 1 --interval 0 --out calib\stage_pair
copy calib\stage_pair\left\pair_0001.png  calib\stage_left.png
copy calib\stage_pair\right\pair_0001.png calib\stage_right.png
```

## 3. 标定

```powershell
.\venv312\Scripts\python.exe calibrate_stereo.py `
  --left calib\stereo\left --right calib\stereo\right `
  --pattern 11x8 --square 20.01 `
  --stage-left calib\stage_left.png --stage-right calib\stage_right.png `
  --out calib\stereo.npz
```

验收：
- 单目 RMS < 0.3 px（< 0.5 px 可用）
- stereo RMS < 0.5 px
- 基线 ≈ 100 mm（和卷尺量的一致）
- `calib\stereo_stage.npz` 生成；台面法向与右相机转过来的法向夹角 < 1°

## 4. 测一件

背光开、激光关，物体放在台面中间（别贴边）：

```powershell
.\venv312\Scripts\python.exe gx_stereo_capture.py --pairs 1 --interval 0 --out shots
# 或交互模式按 SPACE 存一对

.\venv312\Scripts\python.exe measure_stereo.py `
  --left shots\left\pair_0001.png --right shots\right\pair_0001.png `
  --stereo calib\stereo.npz --stage calib\stereo_stage.npz `
  --shape l --out shots\debug_l.png
```

- L 块：`--shape l`
- 圆柱：`--shape cylinder`（自动扣孔，孔按 z=0 底口 + 同心先验）
- 不知道：`--shape auto`

输出：H（mm）、A（mm²）、V（cm³）、IoU；`--out` 存一张画了轮廓的调试图。

## 5. 自检（不用相机）

```powershell
.\venv312\Scripts\python.exe measure_stereo.py --selftest
```

合成 L 块 / 圆柱，检查 H、面积、体积；当前结果：
- L：H 60.5（真 60），A 5498.5（真 5500），IoU 0.9988
- 圆柱：H 70.0，r_out 40.01，r_in 15.12，A 4310.3（真 4319.7）

## 6. 精度与注意

- 高度分辨率由扫描步长决定，默认 0.5 mm；要更细用 `--step 0.25`（慢一倍）。
- 面积误差主要来自边缘阈值和镜头畸变；孔必须按 **z=0 底口** 反投影，按 z=H 会把孔算小约 (WD−H)/WD。
- 物体要“跨光轴”（台面中心 50×50 mm 框内），否则外轮廓不是顶面轮廓。
- 两帧之间物体/相机不能动；动了就重拍。
- 双目对 **黑色/反光** 物体仍靠剪影，背光够亮就行；透明件不行（会透光）。
- 如果 IoU 峰值很平（< 0.9），检查：基线是否真的 100 mm、台面位姿是否用平放棋盘、两台是否同焦。

## 7. 常见问题

- **只找到 1 台**：第二台 USB3 线/供电；先在 GalaxyView 里确认能出图。
- **打开失败**：GalaxyView 还开着；或两台同时开带宽不够，降帧率/曝光。
- **找不到棋盘**：棋盘没完整入镜、太暗/太亮、或格距填错；`--pattern 11x8` 是内角点数。
- **H 明显偏大/偏小**：台面位姿图不是平放棋盘，或 `d0` 的符号/板厚错了；重拍台面图。