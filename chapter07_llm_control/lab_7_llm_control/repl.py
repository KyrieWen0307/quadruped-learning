r"""第 7 章 §7.7.1 交互式文本 REPL（带实时 MuJoCo 3D Viewer）。

直接调用你自己写的 dispatch() 与 run_agent()，在终端输入自然语言，
实时观看 Pupper 在 3D 画面里执行动作。

用法（建议在 IDE 新开一个独立 PowerShell 标签页运行，不影响第 6 章训练）：
    Set-Location D:\learn\quadruped-learning\chapter07_llm_control
    & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\repl.py

纯终端无窗口模式：
    & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\repl.py --no-viewer
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import mujoco
import mujoco.viewer

LAB_DIR = Path(__file__).resolve().parent
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))

from agent.llm_agent import format_trace_table, run_agent  # noqa: E402
from tools.robot_tools import CONTROL_RATIO, PHYS_DT, RobotState, dispatch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab 7 交互式文本 REPL（实时 3D 可视化）")
    parser.add_argument("--no-viewer", action="store_true", help="不打开 3D 窗口，仅终端交互")
    parser.add_argument("--speed", type=float, default=1.0, help="仿真播放倍速（默认 1.0 实时）")
    args = parser.parse_args()

    robot = RobotState(policy_name="test")
    robot.reset()

    viewer = None
    if not args.no_viewer:
        viewer = mujoco.viewer.launch_passive(robot.model, robot.data)
        viewer.cam.distance = 1.6
        viewer.cam.elevation = -22.0
        viewer.cam.azimuth = 90.0
        viewer.cam.lookat[:] = robot.data.xpos[robot.base_id]
        viewer.sync()

    step_counter = 0
    last_sync_wall = time.perf_counter()
    sync_dt = (CONTROL_RATIO * PHYS_DT) / max(args.speed, 0.1)

    def frame_callback(cb_robot: RobotState) -> None:
        nonlocal step_counter, last_sync_wall
        if viewer is None or not viewer.is_running():
            return
        step_counter += 1
        if step_counter % CONTROL_RATIO == 0:
            viewer.cam.lookat[:] = cb_robot.data.xpos[cb_robot.base_id]
            viewer.sync()
            now = time.perf_counter()
            remain = sync_dt - (now - last_sync_wall)
            if remain > 0:
                time.sleep(remain)
            last_sync_wall = time.perf_counter()

    print("=" * 60)
    print("Pupper 交互式语言控制 REPL 已就绪！（直接驱动你写的 dispatch + run_agent）")
    print("内置快捷指令：")
    print("  pose   — 查看当前 [x, y, yaw]（不耗 API）")
    print("  reset  — 把机器狗重置回原点")
    print("  quit   — 退出（Ctrl+C 触发紧急 stop）")
    print("=" * 60)

    try:
        while True:
            if viewer is not None and not viewer.is_running():
                print("3D 窗口已关闭，退出 REPL。")
                break

            try:
                cmd = input("\nyou> ").strip()
            except KeyboardInterrupt:
                print("\n[安全急停] 触发 stop() ...")
                res = dispatch("stop", {}, robot, frame_callback=frame_callback)
                print("stop ->", res)
                continue
            except EOFError:
                break

            if not cmd:
                continue
            if cmd.lower() in ("quit", "exit", "q"):
                break
            if cmd.lower() == "pose":
                print("pose ->", robot.get_pose())
                continue
            if cmd.lower() == "reset":
                robot.reset()
                if viewer is not None and viewer.is_running():
                    viewer.cam.lookat[:] = robot.data.xpos[robot.base_id]
                    viewer.sync()
                print("已重置回原点 ->", robot.get_pose())
                continue

            last_sync_wall = time.perf_counter()
            try:
                final_text, messages = run_agent(cmd, robot, frame_callback=frame_callback)
            except KeyboardInterrupt:
                print("\n[安全急停] 中断当前指令，执行 stop() ...")
                res = dispatch("stop", {}, robot, frame_callback=frame_callback)
                print("stop ->", res)
                continue

            print("\nbot>", final_text)
            print("\n--- 本轮工具轨迹 ---")
            print(format_trace_table(messages))
            print(f"当前位姿: {robot.get_pose()}")
    finally:
        if viewer is not None:
            viewer.close()


if __name__ == "__main__":
    main()
