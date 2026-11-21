r"""Lab 8 §8.8 选做加餐：语言 + 视觉工具 + VLM 多模态具身 Agent 演示与实时 3D/语音交互。

用法（在 chapter08_perception 目录下）：
  # 1. 跑标准双任务演示（自动录制 GIF + 导出轨迹到 portfolio/）
  & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_8_ball_chase\vision_agent.py

  # 2. 启动实时 3D 文本交互 REPL（可随时输入指令找球、问 VLM、追球）
  & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_8_ball_chase\vision_agent.py --repl

  # 3. 启动实时 3D + 麦克风语音交互（复用第 7 章 faster-whisper）
  & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_8_ball_chase\vision_agent.py --voice
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import mujoco
import mujoco.viewer
import numpy as np
from openai import OpenAI
from PIL import Image, ImageDraw

LAB8_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAB8_DIR.parents[1]
SHARED_ROOT = REPO_ROOT / "chapter06_policy_training" / "lab6"
LAB7_DIR = REPO_ROOT / "chapter07_llm_control" / "lab_7_llm_control"

if str(LAB8_DIR) not in sys.path:
    sys.path.insert(0, str(LAB8_DIR))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))
if str(LAB7_DIR) not in sys.path:
    sys.path.append(str(LAB7_DIR))

from shared.viz import gif_utils  # noqa: E402
from agent.llm_agent import format_trace_table  # noqa: E402
from starter import GIF_FPS, GIF_HEIGHT, GIF_WIDTH, PORTFOLIO_DIR, _setup_renderer  # noqa: E402
from vision_tools import (  # noqa: E402
    VISION_TOOLS,
    VisionRobotState,
    vision_dispatch,
)

DEFAULT_MODEL = "deepseek-chat"

VISION_SYSTEM = (
    "You are an embodied controller for a quadruped robot (Pupper v3) equipped with a front head camera "
    "in a MuJoCo simulation. You have motion tools (walk, stop, get_pose, stand) AND vision tools "
    "(look_for, follow, ask_vlm). There is NO separate `turn` tool — rotate in place using walk(vx=0, wz=..., duration=...).\n"
    "Strategy:\n"
    "1. Call look_for('red') first to check if a red ball is currently in the camera view.\n"
    "2. If look_for returns found=false, rotate in place using walk(vx=0, wz=1.2, duration=1.5) (turns ~60 deg each step) "
    "and call look_for('red') again until you find it.\n"
    "3. Once found, call follow('red', seconds=8.0) to visually servo toward the ball and stop in front of it. "
    "If follow stalls because the ball is still far away, you may combine walk(vx=0.5, wz=0, duration=1.5) and look_for('red').\n"
    "4. If the user asks you to describe the scene or use the VLM, call ask_vlm(question) first.\n"
    "5. If any tool returns ok=false, adapt automatically without asking permission. "
    "When the goal is complete, reply concisely in Chinese."
)


def run_vision_agent(
    user_msg: str,
    robot: VisionRobotState,
    *,
    max_turns: int = 16,
    model: str | None = None,
    frame_callback=None,
) -> tuple[str, list[dict[str, Any]]]:
    """多模态具身 Agent 循环：主大脑调用运动 + 视觉 + VLM 工具。"""
    client = OpenAI()
    if model is None:
        model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": VISION_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    for _ in range(max_turns):
        resp = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            tools=VISION_TOOLS,
            messages=messages,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls or resp.choices[0].finish_reason != "tool_calls":
            return msg.content or "", messages

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
                result = vision_dispatch(
                    tc.function.name,
                    args,
                    robot,
                    frame_callback=frame_callback,
                )
            except json.JSONDecodeError as exc:
                result = {"ok": False, "error": f"invalid JSON: {exc}"}
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return "max turns reached", messages


def _load_cn_font(size: int):
    from PIL import ImageFont

    for path in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",
    ):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return gif_utils.load_font(size)


def _caption_frame(frame: np.ndarray, title: str, t: float) -> np.ndarray:
    image = Image.fromarray(frame).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    font = _load_cn_font(16)
    small = _load_cn_font(13)
    draw.rectangle((0, 0, image.width, 34), fill=(255, 255, 255, 220))
    draw.text((10, 6), title, fill=(18, 30, 44, 255), font=font)
    draw.rectangle((0, image.height - 28, image.width, image.height), fill=(0, 0, 0, 160))
    draw.text((10, image.height - 24), f"§8.8 Vision+VLM Agent  t={t:.1f}s", fill=(235, 235, 235, 240), font=small)
    return np.asarray(image)


def run_demo_suite() -> None:
    """运行 §8.8 双场景闭环演示，导出 GIF 与消息轨迹。"""
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    tasks = [
        {
            "id": "V1_search_and_follow",
            "title": "V1: 球在视野外 → 自主转身找球并走过去",
            "ball_pos": (0.6, -1.2, 0.05),
            "prompt": "看看周围有没有红球；如果当前画面没看到，就原地转圈找找，找到后走过去停在球前。",
        },
        {
            "id": "V2_vlm_then_follow",
            "title": "V2: VLM 识图判断方向 → 视觉跟随靠近红球",
            "ball_pos": (1.8, 0.65, 0.05),
            "prompt": "先调用 ask_vlm 看一眼前方相机画面，描述你看到了什么以及球在左边还是右边；然后用视觉工具确认并走过去停在红球前。",
        },
    ]

    trace_sections: list[str] = ["# Lab 8 §8.8 视觉工具 + VLM Agent 实测轨迹\n"]

    for task in tasks:
        print("\n" + "=" * 64)
        print(task["title"])
        print("=" * 64)
        robot = VisionRobotState(policy_name="test", ball_pos=task["ball_pos"])
        renderer, camera = _setup_renderer(robot)
        frames: list[np.ndarray] = []

        try:
            robot.reset()
            t_start = robot.sim_time
            next_frame_t = [0.0]

            def frame_cb(cb_robot: VisionRobotState) -> None:
                t = cb_robot.sim_time - t_start
                if t >= next_frame_t[0]:
                    r_pos = cb_robot.data.xpos[cb_robot.base_id]
                    b_pos = cb_robot.data.mocap_pos[0]
                    mid = (r_pos + b_pos) / 2.0
                    mid[2] = 0.15
                    camera.lookat[:] = mid
                    renderer.update_scene(cb_robot.data, camera=camera)
                    raw = renderer.render()
                    frames.append(_caption_frame(raw, task["title"], t))
                    next_frame_t[0] += 1.0 / GIF_FPS

            reply, messages = run_vision_agent(
                task["prompt"],
                robot,
                frame_callback=frame_cb,
            )
            print(f"最终回复: {reply}")
            trace_md = format_trace_table(messages)
            print(trace_md)

            gif_path = PORTFOLIO_DIR / f"vision_agent_{task['id']}.gif"
            if frames:
                gif_utils.write_gif(
                    frames,
                    gif_path,
                    fps=GIF_FPS,
                    max_frames=120,
                    width=GIF_WIDTH,
                    palette_colors=64,
                )
                print(f"GIF 已保存: {gif_path} ({len(frames)} 帧)")

            trace_sections.append(
                f"## {task['title']}\n\n"
                f"- 球初始坐标：`{task['ball_pos']}`\n"
                f"- 指令：`{task['prompt']}`\n"
                f"- 最终回复：{reply}\n"
                f"- 最终位姿：`{robot.get_pose()}`\n\n"
                f"{trace_md}\n"
            )
        finally:
            renderer.close()
            robot.close()

    trace_path = PORTFOLIO_DIR / "vision_agent_traces.md"
    trace_path.write_text("\n".join(trace_sections), encoding="utf-8")
    print(f"\n完整轨迹已写入: {trace_path}")


def run_interactive(*, voice: bool = False, seconds: float = 4.0) -> None:
    """启动实时 3D MuJoCo 窗口 + 文本/语音交互式视觉 Agent。"""
    whisper_model = None
    record_audio = None
    transcribe_audio = None

    if voice:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from faster_whisper import WhisperModel
        from voice_repl import record_audio as _rec, transcribe_audio as _trans

        print("正在加载 faster-whisper (small, CPU int8)...")
        whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
        record_audio = _rec
        transcribe_audio = _trans

    robot = VisionRobotState(policy_name="test", ball_pos=(1.5, 0.5, 0.05))
    robot.reset()

    print("\n实时 3D 视觉+VLM Agent 已启动！输入示例：")
    print("  - '先用 VLM 看看前面有什么，再走过去停在红球前'")
    print("  - 'ball 0.5 -1.3' （快速把红球挪到指定坐标）")
    print("  - 'reset' / 'quit'")

    try:
        with mujoco.viewer.launch_passive(robot.model, robot.data) as viewer:
            viewer.cam.distance = 3.0
            viewer.cam.elevation = -25.0
            viewer.cam.azimuth = 135.0
            viewer.sync()

            last_sync = [time.perf_counter()]

            def viewer_cb(cb_robot: VisionRobotState) -> None:
                now = time.perf_counter()
                if now - last_sync[0] >= 1.0 / 30.0:
                    viewer.cam.lookat[:] = cb_robot.data.xpos[cb_robot.base_id]
                    viewer.sync()
                    last_sync[0] = now

            while viewer.is_running():
                if voice:
                    raw = input("\n按回车开始录音（或输入 ball x y / reset / quit）：").strip()
                    if raw.lower() in {"q", "quit", "exit"}:
                        break
                    if raw.lower() == "reset":
                        robot.reset()
                        viewer.sync()
                        continue
                    if raw.lower().startswith("ball "):
                        parts = raw.split()
                        if len(parts) >= 3:
                            robot.set_ball_pos(float(parts[1]), float(parts[2]))
                            viewer.sync()
                            print(f"红球已移至 ({parts[1]}, {parts[2]}, 0.05)")
                        continue
                    print(f"🎤 录音中（{seconds:.1f} s）...")
                    audio = record_audio(seconds=seconds)
                    user_msg = transcribe_audio(whisper_model, audio)
                    print(f"📝 识别结果: {user_msg!r}")
                    if not user_msg:
                        continue
                else:
                    user_msg = input("\n你 > ").strip()
                    if not user_msg:
                        continue
                    if user_msg.lower() in {"q", "quit", "exit"}:
                        break
                    if user_msg.lower() == "reset":
                        robot.reset()
                        viewer.sync()
                        continue
                    if user_msg.lower().startswith("ball "):
                        parts = user_msg.split()
                        if len(parts) >= 3:
                            robot.set_ball_pos(float(parts[1]), float(parts[2]))
                            viewer.sync()
                            print(f"红球已移至 ({parts[1]}, {parts[2]}, 0.05)")
                        continue

                try:
                    reply, messages = run_vision_agent(
                        user_msg,
                        robot,
                        frame_callback=viewer_cb,
                    )
                    viewer.sync()
                    print(format_trace_table(messages))
                    print(f"Pupper > {reply}")
                except KeyboardInterrupt:
                    print("\n⚠️ 已急停！")
    finally:
        robot.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Lab 8 §8.8 视觉工具 + VLM Agent")
    parser.add_argument("--repl", action="store_true", help="启动实时 3D 文本交互 REPL")
    parser.add_argument("--voice", action="store_true", help="启动实时 3D 语音交互（faster-whisper）")
    parser.add_argument("--seconds", type=float, default=4.0, help="语音录音时长（秒）")
    args = parser.parse_args()

    if args.voice:
        run_interactive(voice=True, seconds=args.seconds)
    elif args.repl:
        run_interactive(voice=False)
    else:
        run_demo_suite()


if __name__ == "__main__":
    main()
