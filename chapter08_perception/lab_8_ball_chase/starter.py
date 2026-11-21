"""Lab 8 学生起点：追球 Demo（Ball-Chasing Demo · 学生 TODO 3）。

物理后端严格复用 Lab 7 的 RobotState（test_policy.json + 50 Hz / 500 Hz），
只替换 XML 路径为 pupper_chase.xml（加了 head_cam + mocap 红球）。
学生需完成：
  - TODO 1: perception/ball_detector.py -> detect_red_ball()
  - TODO 2: perception/tracker_fsm.py   -> visual_servo() & TrackerFSM.step()
  - TODO 3: 本文件                       -> run_chase()
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco
import numpy as np
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# 路径设置：复用第 6 章 shared 资产与第 7 章 RobotState
# ---------------------------------------------------------------------------

LAB_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAB_DIR.parents[1]
SHARED_ROOT = REPO_ROOT / "chapter06_policy_training" / "lab6"
LAB7_TOOLS_DIR = REPO_ROOT / "chapter07_llm_control" / "lab_7_llm_control" / "tools"

if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))
if str(LAB7_TOOLS_DIR) not in sys.path:
    sys.path.append(str(LAB7_TOOLS_DIR))

from shared.viz import gif_utils  # noqa: E402
from robot_tools import CONTROL_DT, CONTROL_RATIO, PHYS_DT, RobotState  # noqa: E402

from perception.ball_detector import detect_red_ball  # noqa: E402
from perception.tracker_fsm import FSMState, H_REF, TrackerFSM  # noqa: E402

PORTFOLIO_DIR = LAB_DIR / "portfolio"
MODEL_CHASE = LAB_DIR / "models" / "pupper_chase.xml"

GIF_FPS = 10
GIF_WIDTH = 480
GIF_HEIGHT = 360
VISION_HZ = 10
CHASE_DURATION = 20.0
BALL_MOVE_INTERVAL = 3.0


# ---------------------------------------------------------------------------
# ChaseRobotState — 只替换 XML 路径，其余完全继承 Lab 7 RobotState
# ---------------------------------------------------------------------------


class ChaseRobotState(RobotState):
    """Lab 7 RobotState 的子类，唯一区别是加载 pupper_chase.xml（带 head_cam 与 mocap 红球）。"""

    def __init__(self, policy_name: str = "test"):
        from shared.upstream.lab_5_mujoco import OBS_TOTAL, load_policy  # noqa: F811

        self.policy = load_policy(policy_name)

        self.model = mujoco.MjModel.from_xml_path(str(MODEL_CHASE))
        self.model.opt.timestep = PHYS_DT
        self.model.actuator_gainprm[:, 0] = self.policy.kp
        self.model.actuator_biasprm[:, 1] = -self.policy.kp
        self.model.actuator_biasprm[:, 2] = -self.policy.kd
        self.data = mujoco.MjData(self.model)

        self.base_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, "base_link",
        )

        self.obs_history = np.zeros(OBS_TOTAL, dtype=np.float32)
        self.last_action = np.zeros(12, dtype=np.float32)
        self.target_joints = self.policy.default_joint_pos.copy()
        self.phys_step = 0
        self.total_yaw = 0.0

        self._reset_home()

    def _reset_home(self) -> None:
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[0:3] = [0.0, 0.0, 0.22]
        self.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
        self.data.qpos[7:19] = self.policy.default_joint_pos
        self.data.ctrl[:] = self.policy.default_joint_pos
        self.data.mocap_pos[0] = [1.5, 0.3, 0.05]
        mujoco.mj_forward(self.model, self.data)
        self.obs_history[:] = 0.0
        self.last_action[:] = 0.0
        self.target_joints = self.policy.default_joint_pos.copy()
        self.phys_step = 0
        self.total_yaw = 0.0


# ---------------------------------------------------------------------------
# 渲染与字幕工具
# ---------------------------------------------------------------------------


def _setup_renderer(robot: ChaseRobotState) -> tuple[mujoco.Renderer, mujoco.MjvCamera]:
    robot.model.vis.global_.offwidth = max(robot.model.vis.global_.offwidth, GIF_WIDTH)
    robot.model.vis.global_.offheight = max(robot.model.vis.global_.offheight, GIF_HEIGHT)
    renderer = mujoco.Renderer(robot.model, height=GIF_HEIGHT, width=GIF_WIDTH)
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(robot.model, camera)
    camera.distance = 3.0
    camera.elevation = -25.0
    camera.azimuth = 135.0
    return renderer, camera


def _setup_head_renderer(
    robot: ChaseRobotState, w: int = 320, h: int = 240,
) -> mujoco.Renderer:
    robot.model.vis.global_.offwidth = max(robot.model.vis.global_.offwidth, w)
    robot.model.vis.global_.offheight = max(robot.model.vis.global_.offheight, h)
    return mujoco.Renderer(robot.model, height=h, width=w)


def _caption_chase_frame(
    frame: np.ndarray,
    fsm_state: FSMState,
    vx: float,
    wz: float,
    t: float,
) -> np.ndarray:
    image = Image.fromarray(frame).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    font = gif_utils.load_font(20)
    small = gif_utils.load_font(14)

    state_text_colors = {
        FSMState.SEARCHING: (200, 160, 0, 255),
        FSMState.TRACKING: (0, 160, 60, 255),
        FSMState.STOPPED: (200, 60, 60, 255),
    }
    text_color = state_text_colors.get(fsm_state, (200, 60, 60, 255))
    draw.rectangle((0, 0, image.width, 52), fill=(255, 255, 255, 220))
    draw.text((10, 4), f"[{fsm_state.value}]", fill=text_color, font=font)
    draw.text((10, 28), f"vx={vx:.2f}  wz={wz:.2f}", fill=(18, 30, 44, 255), font=small)

    draw.rectangle((0, image.height - 32, image.width, image.height), fill=(0, 0, 0, 160))
    draw.text(
        (10, image.height - 28),
        f"Ball Chase  t={t:.1f}s",
        fill=(230, 230, 230, 240),
        font=small,
    )
    return np.asarray(image)


# ---------------------------------------------------------------------------
# 球运动控制（已实现，不需要修改）
# ---------------------------------------------------------------------------


class BallMover:
    """控制 mocap 红球的随机运动（1 秒线性插值，不瞬移）。"""

    def __init__(self, rng: np.random.Generator | None = None) -> None:
        self._rng = rng or np.random.default_rng(42)
        self._target = np.array([1.5, 0.3, 0.05])
        self._origin = self._target.copy()
        self._next_move_time = BALL_MOVE_INTERVAL
        self._move_start_time = 0.0
        self._move_duration = 1.0

    def update(self, t: float, data: mujoco.MjData) -> None:
        if t >= self._next_move_time:
            self._origin = data.mocap_pos[0].copy()
            self._target = np.array([
                self._rng.uniform(1.0, 3.0),
                self._rng.uniform(-1.0, 1.0),
                0.05,
            ])
            self._move_start_time = t
            self._move_duration = 1.0
            self._next_move_time = t + BALL_MOVE_INTERVAL

        alpha = min(1.0, (t - self._move_start_time) / self._move_duration)
        data.mocap_pos[0] = self._origin + alpha * (self._target - self._origin)


# ---------------------------------------------------------------------------
# TODO 3：追球主循环
# ---------------------------------------------------------------------------


def run_chase(
    robot: ChaseRobotState,
    head_renderer: mujoco.Renderer,
    head_w: int = 320,
    head_h: int = 240,
    duration: float = CHASE_DURATION,
    *,
    frame_callback=None,
) -> dict:
    """追球闭环：camera → detect → fsm.step → (vx, wz) → policy → mj_step。

    Returns
    -------
    dict with keys:
      - "ok": bool（是否全程未摔倒）
      - "timeline": list[dict]，每次视觉采样追加一条记录：
          {"t", "state", "vx", "wz", "e_yaw", "box_h", "dist"}
      - 摔倒时可附带 "error": "robot fell"

    实现提示（三层频率：10 Hz 视觉 / 50 Hz 策略 / 500 Hz 物理）
    ----------------------------------------------------------
    循环前准备：
      - fsm = TrackerFSM()
      - ball_mover = BallMover()
      - head_cam_id = mujoco.mj_name2id(robot.model, mujoco.mjtObj.mjOBJ_CAMERA, "head_cam")
      - vision_interval = 1.0 / VISION_HZ，next_vision_time = 0.0
      - current_vx, current_wz = 0.0, 0.0；current_state = FSMState.SEARCHING
      - timeline = []；n_phys = int(duration / PHYS_DT)；cmd = np.zeros(3, dtype=np.float32)

    每个物理步 s in range(n_phys)：
      1. t = robot.sim_time，调用 ball_mover.update(t, robot.data)
      2. 若 t >= next_vision_time（10 Hz 视觉采样）：
         - head_renderer.update_scene(robot.data, camera=head_cam_id) → rgb = head_renderer.render()
         - box = detect_red_ball(rgb)；boxes = [box] if box is not None else []
         - current_state, current_vx, current_wz = fsm.step(t, boxes, head_w, head_h)
         - next_vision_time = t + vision_interval
         - 计算球到机器人的水平欧氏距离 dist，把 {"t", "state", "vx", "wz", "e_yaw", "box_h", "dist"} 记入 timeline
           （注：state 存 current_state.value；未检测到球时 e_yaw 与 box_h 记为 None）
      3. 更新 cmd[0] = current_vx, cmd[2] = current_wz
      4. 若 s % CONTROL_RATIO == 0（50 Hz 小脑策略）：调用 robot._policy_tick(cmd)
      5. 写入 robot.data.ctrl[:] = robot.target_joints，调用 mujoco.mj_step(robot.model, robot.data)，robot.phys_step += 1
      6. 若 frame_callback is not None：调用 frame_callback(robot, current_state, current_vx, current_wz)
      7. 若 robot.is_fallen()：提前返回 {"ok": False, "error": "robot fell", "timeline": timeline}
    """
    # ===== TODO 3 START =====
    fsm = TrackerFSM()
    ball_mover = BallMover()
    head_cam_id = mujoco.mj_name2id(robot.model, mujoco.mjtObj.mjOBJ_CAMERA, "head_cam")
    vision_interval = 1.0 / VISION_HZ
    next_vision_time = 0.0
    current_vx, current_wz = 0.0, 0.0
    current_state = FSMState.SEARCHING
    timeline = []
    n_phys = int(duration / PHYS_DT)
    cmd = np.zeros(3, dtype=np.float32)
    for s in range(n_phys):
        t = robot.sim_time
        ball_mover.update(t, robot.data)
        if t >= next_vision_time:
            head_renderer.update_scene(robot.data, camera=head_cam_id)
            rgb = head_renderer.render()
            box = detect_red_ball(rgb)
            boxes = [box] if box is not None else []
            current_state, current_vx, current_wz = fsm.step(t, boxes, head_w, head_h)
            next_vision_time = t + vision_interval
            dist = np.linalg.norm(robot.data.mocap_pos[0][:2] - robot.data.qpos[0:2])
            timeline.append({
                't' : t,
                'state' : current_state.value,
                'vx' : current_vx,
                'wz' : current_wz,
                'e_yaw' : (box['cx'] - head_w / 2) / (head_w / 2) if box else None,
                'box_h' : box['h'] if box else None,
                'dist' : dist
            })
        cmd[0] = current_vx
        cmd[2] = current_wz
        if s % CONTROL_RATIO == 0:
            robot._policy_tick(cmd)
        robot.data.ctrl[:] = robot.target_joints
        mujoco.mj_step(robot.model, robot.data)
        robot.phys_step += 1
        if frame_callback is not None:
            frame_callback(robot, current_state, current_vx, current_wz)
        if robot.is_fallen():
            return {"ok": False, "error": "robot fell", "timeline": timeline}
    return {"ok": True, "timeline": timeline}
    # ===== TODO 3 END =====


# ---------------------------------------------------------------------------
# GIF 录制
# ---------------------------------------------------------------------------


def record_chase_gif(
    robot: ChaseRobotState,
    renderer: mujoco.Renderer,
    camera: mujoco.MjvCamera,
    head_renderer: mujoco.Renderer,
    head_w: int = 320,
    head_h: int = 240,
    duration: float = CHASE_DURATION,
) -> tuple[list[np.ndarray], dict]:
    """录制追球 GIF，返回 (frames, result)。"""
    robot.reset()

    frames: list[np.ndarray] = []
    t_start = robot.sim_time
    next_frame_time = [0.0]

    def frame_callback(
        cb_robot: ChaseRobotState,
        state: FSMState,
        vx: float,
        wz: float,
    ):
        t = cb_robot.sim_time - t_start
        if t >= next_frame_time[0]:
            robot_pos = cb_robot.data.xpos[cb_robot.base_id]
            ball_pos = cb_robot.data.mocap_pos[0]
            midpoint = (robot_pos + ball_pos) / 2.0
            midpoint[2] = 0.15
            camera.lookat[:] = midpoint
            renderer.update_scene(cb_robot.data, camera=camera)
            raw = renderer.render()
            frames.append(_caption_chase_frame(raw, state, vx, wz, t))
            next_frame_time[0] += 1.0 / GIF_FPS

    result = run_chase(
        robot, head_renderer, head_w, head_h, duration,
        frame_callback=frame_callback,
    )
    return frames, result


# ---------------------------------------------------------------------------
# 图表导出
# ---------------------------------------------------------------------------


def plot_tracking_error(timeline: list[dict], out_path: Path) -> None:
    """e_yaw vs 时间，叠加 FSM 状态色条。"""
    ts = [r["t"] for r in timeline]
    e_yaws = [r["e_yaw"] for r in timeline]
    states = [r["state"] for r in timeline]

    fig, ax = plt.subplots(figsize=(10, 3))

    state_colors = {"SEARCHING": "#FFC800", "TRACKING": "#00C850", "STOPPED": "#C83C3C"}
    for i in range(len(ts) - 1):
        ax.axvspan(ts[i], ts[i + 1], alpha=0.15, color=state_colors.get(states[i], "#888"))

    valid_ts = [t for t, e in zip(ts, e_yaws) if e is not None]
    valid_es = [e for e in e_yaws if e is not None]
    ax.plot(valid_ts, valid_es, "b-", linewidth=1.0, label="e_yaw")
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("e_yaw (normalized)")
    ax.set_title("Tracking Error vs Time")
    ax.legend(loc="upper right")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_detection_vs_distance(timeline: list[dict], out_path: Path) -> None:
    """球到机器人距离 vs bbox 高度。"""
    dists = [r["dist"] for r in timeline if r["box_h"] is not None]
    box_hs = [r["box_h"] for r in timeline if r["box_h"] is not None]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(dists, box_hs, s=8, alpha=0.6, label="detections")
    ax.axhline(H_REF, color="red", linewidth=1.0, linestyle="--", label=f"H_REF={H_REF}")
    ax.set_xlabel("distance to ball (m)")
    ax.set_ylabel("bbox height (px)")
    ax.set_title("Detection vs Distance")
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    """快速环境检查（离线，不需要 API key）。"""
    robot = ChaseRobotState(policy_name="test")
    robot.reset()
    print(f"Lab 8 环境检查: policy={robot.policy.path.name}")

    result = robot.step_cmd(0.5, 0.0, 2.0)
    print(f"step_cmd(0.5, 0, 2.0): {result}")

    head_renderer = _setup_head_renderer(robot)
    head_cam_id = mujoco.mj_name2id(robot.model, mujoco.mjtObj.mjOBJ_CAMERA, "head_cam")
    head_renderer.update_scene(robot.data, camera=head_cam_id)
    rgb = head_renderer.render()
    print(f"head_cam render: shape={rgb.shape}, dtype={rgb.dtype}")
    head_renderer.close()

    try:
        box = detect_red_ball(rgb)
        print(f"detect_red_ball: {box}")
    except NotImplementedError as exc:
        print(f"提示: {exc}（物理与相机渲染已就绪，可按 TODO 1–3 逐步实现）")

    print("Lab 8 环境检查通过。")


if __name__ == "__main__":
    main()
