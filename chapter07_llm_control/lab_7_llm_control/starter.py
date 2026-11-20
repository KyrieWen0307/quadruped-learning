"""Lab 7 主入口与 GIF 录制管线 — TODO 3 (render_task_gif)。

本文件串联：
  - TODO 1: tools/robot_tools.py 中的 dispatch()
  - TODO 2: agent/llm_agent.py 中的 run_agent()
  - TODO 3: 本文件中的 render_task_gif()
"""

from __future__ import annotations

import sys
from pathlib import Path

import mujoco
import numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

LAB_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAB_DIR.parents[1]
SHARED_ROOT = REPO_ROOT / "chapter06_policy_training" / "lab6"
for _p in (SHARED_ROOT, LAB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.viz import gif_utils  # noqa: E402
from tools.robot_tools import RobotState, dispatch  # noqa: E402
from agent.llm_agent import format_trace_table, run_agent  # noqa: E402

PORTFOLIO_DIR = LAB_DIR / "portfolio"
load_dotenv(LAB_DIR / ".env")

GIF_FPS = 12
GIF_WIDTH = 640
GIF_HEIGHT = 480

# ---------------------------------------------------------------------------
# 5 级任务定义
# ---------------------------------------------------------------------------

TASKS = [
    {
        "level": "L1",
        "label": "L1 原子",
        "user_msg": "向前走两步然后停下",
        "description": "单工具调用",
        "gif_name": "agent_L1_stop.gif",
    },
    {
        "level": "L2",
        "label": "L2 带数字",
        "user_msg": "向前走 1 米",
        "description": "参数转换",
        "gif_name": "agent_L2_walk.gif",
    },
    {
        "level": "L3",
        "label": "L3 多步顺序",
        "user_msg": "前进 1 米，然后右转 90 度",
        "description": "多工具顺序",
        "gif_name": "agent_L3_sequence.gif",
    },
    {
        "level": "L4",
        "label": "L4 ReAct 反馈",
        "user_msg": "走到坐标 (2, 1) 附近",
        "description": "get_pose + 迭代",
        "gif_name": "agent_L4_react.gif",
    },
    {
        "level": "L5",
        "label": "L5 容错降级",
        "user_msg": "以 3 米/秒的速度飞奔向前",
        "description": "超界 → 重试",
        "gif_name": "agent_L5_retry.gif",
    },
]


# ---------------------------------------------------------------------------
# 渲染工具（已实现，供 TODO 3 使用；已做 Windows 中文字体适配）
# ---------------------------------------------------------------------------

def _load_cjk_font(size: int) -> ImageFont.ImageFont:
    """优先加载 Windows 中文字体，避免中文任务名在 GIF 中变成方框。"""
    win_candidates = (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    )
    for path in win_candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return gif_utils.load_font(size)


def _setup_renderer(robot: RobotState) -> tuple[mujoco.Renderer, mujoco.MjvCamera]:
    """创建 offscreen renderer + camera。"""
    robot.model.vis.global_.offwidth = max(robot.model.vis.global_.offwidth, GIF_WIDTH)
    robot.model.vis.global_.offheight = max(robot.model.vis.global_.offheight, GIF_HEIGHT)
    renderer = mujoco.Renderer(robot.model, height=GIF_HEIGHT, width=GIF_WIDTH)
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(robot.model, camera)
    camera.distance = 1.4
    camera.elevation = -20.0
    camera.azimuth = 90.0
    return renderer, camera


def _caption_frame(
    frame: np.ndarray,
    level_label: str,
    user_msg: str,
    status: str,
    t: float,
) -> np.ndarray:
    """在帧上叠加任务等级、指令、agent 状态和时间戳。"""
    image = Image.fromarray(frame).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    font = _load_cjk_font(20)
    small = _load_cjk_font(14)

    draw.rectangle((0, 0, image.width, 52), fill=(255, 255, 255, 220))
    draw.text((10, 4), f"[{level_label}]", fill=(200, 60, 60, 255), font=font)
    draw.text((10, 28), user_msg, fill=(18, 30, 44, 255), font=small)

    draw.rectangle((0, image.height - 32, image.width, image.height), fill=(0, 0, 0, 160))
    draw.text(
        (10, image.height - 28),
        f"{status}  t={t:.1f}s",
        fill=(230, 230, 230, 240),
        font=small,
    )
    return np.asarray(image)


# ---------------------------------------------------------------------------
# TODO 3: render_task_gif（学生实现）
# ---------------------------------------------------------------------------

def render_task_gif(
    task: dict,
    robot: RobotState,
    renderer: mujoco.Renderer,
    camera: mujoco.MjvCamera,
) -> tuple[list[np.ndarray], str, list]:
    """运行单个任务，录制 GIF 帧，返回 (frames, final_text, messages)。

    提示：
    1. robot.reset() 重置环境，记录 t_start = robot.sim_time
    2. 录约 1 秒（GIF_FPS 帧）初始静止画面（status="waiting"）
    3. 定义 frame_callback(cb_robot)：
       - 计算相对时间 t = cb_robot.sim_time - t_start
       - 当 t >= next_frame_time：
           * camera.lookat[:] = cb_robot.data.xpos[cb_robot.base_id]
           * renderer.update_scene(cb_robot.data, camera=camera)
           * raw = renderer.render()
           * frames.append(_caption_frame(raw, task["label"], task["user_msg"], "running", t))
           * next_frame_time += 1.0 / GIF_FPS
    4. 调用 run_agent(task["user_msg"], robot, frame_callback=frame_callback)
    5. 录约 1 秒（GIF_FPS 帧）结束画面（status="done"）
    6. 返回 (frames, final_text, messages)
    """
    robot.reset()
    frames = []
    t_start = robot.sim_time
    next_frame_time = 0.0
    for _ in range(GIF_FPS):
        camera.lookat[:] = robot.data.xpos[robot.base_id]
        renderer.update_scene(robot.data, camera=camera)
        raw = renderer.render()
        frames.append(_caption_frame(raw, task["label"], task["user_msg"], "waiting", 0.0))
    def frame_callback(cb_robot):
        nonlocal next_frame_time
        t = cb_robot.sim_time - t_start
        if t >= next_frame_time:
            camera.lookat[:] = cb_robot.data.xpos[cb_robot.base_id]
            renderer.update_scene(cb_robot.data, camera=camera)
            raw = renderer.render()
            frames.append(_caption_frame(raw, task["label"], task["user_msg"], "running", t))
            next_frame_time += 1.0 / GIF_FPS
    final_text, messages = run_agent(task["user_msg"], robot, frame_callback=frame_callback)
    for i in range(GIF_FPS):
        t = robot.sim_time - t_start + i / GIF_FPS
        camera.lookat[:] = robot.data.xpos[robot.base_id]
        renderer.update_scene(robot.data, camera=camera)
        raw = renderer.render()
        frames.append(_caption_frame(raw, task["label"], task["user_msg"], "done", t))   
    return frames, final_text, messages
# ---------------------------------------------------------------------------
# 消息轨迹导出（已实现）
# ---------------------------------------------------------------------------

def export_traces(all_traces: dict[str, list], out_path: Path) -> None:
    """把所有任务的消息轨迹写到一个 markdown 文件。"""
    lines = ["# Agent 消息轨迹\n"]
    for task in TASKS:
        level = task["level"]
        if level not in all_traces:
            continue
        lines.append(f"## {task['label']}：{task['user_msg']}\n")
        lines.append(format_trace_table(all_traces[level]))
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"消息轨迹: {out_path}")


# ---------------------------------------------------------------------------
# 快速环境检查入口（不需要 API key）
# ---------------------------------------------------------------------------

def main() -> None:
    """快速环境检查（不需要 API key）。"""
    robot = RobotState(policy_name="test")
    robot.reset()
    print(f"Lab 7 环境检查通过: policy={robot.policy.path.name}, pose={robot.get_pose()}")
    try:
        print("试调 dispatch('get_pose'):", dispatch("get_pose", {}, robot))
    except NotImplementedError as e:
        print(f"尚未实现 TODO 1（预期行为）: {e}")


if __name__ == "__main__":
    main()
