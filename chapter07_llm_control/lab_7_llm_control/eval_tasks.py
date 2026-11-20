"""加载 upstream policy + API key，跑 L1–L5 任务，录 GIF + 导出消息轨迹。"""

from __future__ import annotations

import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAB_DIR.parents[1]
SHARED_ROOT = REPO_ROOT / "chapter06_policy_training" / "lab6"
for _p in (SHARED_ROOT, LAB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.viz import gif_utils  # noqa: E402
from tools.robot_tools import RobotState  # noqa: E402
from starter import (  # noqa: E402
    GIF_FPS,
    GIF_WIDTH,
    PORTFOLIO_DIR,
    TASKS,
    _setup_renderer,
    export_traces,
    render_task_gif,
)


def main() -> None:
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)

    robot = RobotState(policy_name="test")
    renderer, camera = _setup_renderer(robot)

    all_traces: dict[str, list] = {}

    try:
        for i, task in enumerate(TASKS):
            print(f"{'=' * 60}")
            print(f"Task {i + 1}/{len(TASKS)}: {task['label']} — {task['user_msg']}")
            print(f"{'=' * 60}")

            frames, final_text, messages = render_task_gif(
                task, robot, renderer, camera,
            )
            all_traces[task["level"]] = messages

            gif_path = PORTFOLIO_DIR / task["gif_name"]
            gif_utils.write_gif(
                frames,
                gif_path,
                fps=GIF_FPS,
                max_frames=120,
                width=GIF_WIDTH,
                palette_colors=12,
            )
            gif_mb = gif_path.stat().st_size / 1024 / 1024
            print(f"  GIF: {gif_path} ({gif_mb:.2f} MB, {len(frames)} frames)")
            print(f"  Agent 回复: {final_text}")
    finally:
        renderer.close()

    traces_path = PORTFOLIO_DIR / "agent_traces.md"
    export_traces(all_traces, traces_path)

    print(f"\n{'=' * 60}")
    print(f"全部 {len(TASKS)} 个任务完成，交付物在 {PORTFOLIO_DIR}/")


if __name__ == "__main__":
    main()
