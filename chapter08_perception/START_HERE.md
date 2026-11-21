# Lab 8 本机学生起点

本目录取自 Datawhale 开源仓库 `codes/practices/quadruped/cs123/exercises/lab_8_ball_chase`，并整理为与 Lab 7 一致的**单一真源学生骨架**（测试脚本与录屏脚本都直接调用你自己写的函数）。

## 学生编辑哪三处 TODO？

1. **TODO 1**：`lab_8_ball_chase/perception/ball_detector.py` 中的 `detect_red_ball(rgb)`
   - RGB → HSV → 红色跨 0° 两段 `cv2.inRange` 取并集 → `cv2.findContours` 最大轮廓去噪 → 返回 `bbox` 字典或 `None`（对应正文 §8.3 方案 A）。
2. **TODO 2**：`lab_8_ball_chase/perception/tracker_fsm.py` 中的 `visual_servo()` 与 `TrackerFSM.step()`
   - 视觉伺服 P 控制器 + `SEARCHING / TRACKING / STOPPED` 三态状态机切换（对应正文 §8.4–§8.5）。
3. **TODO 3**：`lab_8_ball_chase/starter.py` 中的 `run_chase()`
   - 组装 **500 Hz 物理 / 50 Hz RL 策略 / 10 Hz 视觉感知** 三层频率闭环，记录 `timeline` 并驱动 `frame_callback`（对应正文 §8.6–§8.7）。

## 本机环境与资产复用

- **Python 解释器**：复用第 6–7 章虚拟环境 `D:\learn\quadruped-learning\chapter06_policy_training\.venv\Scripts\python.exe`（已补装 `opencv-python`）。
- **物理与策略资产**：
  - 13 个 STL 网格复用 `chapter04_quadruped_mjcf/assets/mjcfs/meshes/stl/`
  - `test_policy.json`、`lab_5_mujoco.py`、`gif_utils.py` 复用 `chapter06_policy_training/lab6/shared/`
  - `RobotState` 物理循环基类复用 `chapter07_llm_control/lab_7_llm_control/tools/robot_tools.py`

## 常用命令（Windows PowerShell）

```powershell
Set-Location D:\learn\quadruped-learning\chapter08_perception

# 1. 快速环境检查（离线，验证 pupper_chase.xml、test_policy.json 与 head_cam 离屏渲染）
& ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_8_ball_chase\starter.py

# 2. 运行官方 7 条离线数值断言（验收 TODO 1–2 与物理/相机集成）
& ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_8_ball_chase\tests.py

# 3. 跑 20 秒追球 demo 并生成 GIF 与图表（验收 TODO 3）
& ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_8_ball_chase\eval_chase.py

# 4. 一键生成全部毕业交付物（含检查 notes.md）
& ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_8_ball_chase\make_artifacts.py
```
