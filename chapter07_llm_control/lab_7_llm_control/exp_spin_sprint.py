r"""对照实验脚本：录制压力测试指令的“改进前 (before)”与“改进后 (after)” GIF + 轨迹。

用法（在 chapter07_llm_control 目录下）：
    # 1. 记录改进前基线（当前原始 4 工具）
    & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\exp_spin_sprint.py --tag before

    # 2. 改进工具后再跑一次对照
    & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\exp_spin_sprint.py --tag after
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAB_DIR.parents[1]
SHARED_ROOT = REPO_ROOT / "chapter06_policy_training" / "lab6"
for _p in (SHARED_ROOT, LAB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agent.llm_agent import format_trace_table  # noqa: E402
from shared.viz import gif_utils  # noqa: E402
from starter import (  # noqa: E402
    GIF_FPS,
    GIF_WIDTH,
    PORTFOLIO_DIR,
    _setup_renderer,
    render_task_gif,
)
from tools.robot_tools import RobotState  # noqa: E402

STRESS_PROMPT = "最快速度转两圈，然后飞奔向前4m"


def main() -> None:
    parser = argparse.ArgumentParser(description="录制转两圈+飞奔4m对照实验 GIF 与轨迹")
    parser.add_argument(
        "--tag",
        choices=("before", "after", "v3"),
        required=True,
        help="实验版本标签：before（原始基线）/ after（+无折叠遥测）/ v3（+航向保持P闭环）",
    )
    args = parser.parse_args()

    label_map = {
        "before": "对比实验 · Stage1 原始基线",
        "after": "对比实验 · Stage2 +无折叠遥测",
        "v3": "对比实验 · Stage3 +航向保持",
    }
    label = label_map[args.tag]
    task = {
        "level": f"EXP_{args.tag}",
        "label": label,
        "user_msg": STRESS_PROMPT,
        "gif_name": f"exp_spin_sprint_{args.tag}.gif",
    }

    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    robot = RobotState(policy_name="test")
    renderer, camera = _setup_renderer(robot)

    try:
        print(f"开始录制 [{label}]：{STRESS_PROMPT}")
        frames, final_text, messages = render_task_gif(task, robot, renderer, camera)
    finally:
        renderer.close()

    gif_path = PORTFOLIO_DIR / task["gif_name"]
    gif_utils.write_gif(
        frames,
        gif_path,
        fps=GIF_FPS,
        max_frames=180,
        width=GIF_WIDTH,
        palette_colors=12,
    )
    gif_mb = gif_path.stat().st_size / 1024 / 1024

    trace_path = PORTFOLIO_DIR / f"exp_spin_sprint_{args.tag}_trace.md"
    trace_md = (
        f"# {label}：{STRESS_PROMPT}\n\n"
        f"- 最终位姿：`{robot.get_pose()}`\n"
        f"- Agent 回复：{final_text}\n\n"
        f"{format_trace_table(messages)}\n"
    )
    trace_path.write_text(trace_md, encoding="utf-8")

    print(f"GIF 已保存: {gif_path} ({gif_mb:.2f} MB, 原始 {len(frames)} 帧)")
    print(f"轨迹已保存: {trace_path}")
    print(f"最终位姿: {robot.get_pose()}")
    print(f"Agent 回复: {final_text}")


if __name__ == "__main__":
    main()
