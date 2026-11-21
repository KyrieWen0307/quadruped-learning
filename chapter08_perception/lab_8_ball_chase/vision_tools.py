"""Lab 8 §8.8 选做加餐：视觉工具集（look_for / follow / ask_vlm）与扩展分发器。

架构设计：
  - 运动底座：复用第 7 章的 4 个运动工具（walk / turn / stop / get_pose）
  - 经典快眼：新增 look_for（单帧 HSV 检测 + 粗估距离）与 follow（内部跑 10 Hz FSM + 50 Hz RL）
  - VLM 顾问：新增 ask_vlm（按需把 head_cam PNG 转 base64 发给多模态大模型看图回答）

学生只需补全本文件中的 3 处 TODO：
  - TODO S1: look_for(target, robot)
  - TODO S2: follow(target, seconds, robot, frame_callback=None)
  - TODO S3: encode_rgb_b64(rgb) 与 ask_vlm(question, robot)
"""

from __future__ import annotations

import base64
import copy
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import mujoco
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

# ---------------------------------------------------------------------------
# 路径与环境变量加载（自动继承第 7 章 DeepSeek 配置，再用本章 .env 叠加 VLM 配置）
# ---------------------------------------------------------------------------

LAB8_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAB8_DIR.parents[1]
SHARED_ROOT = REPO_ROOT / "chapter06_policy_training" / "lab6"
LAB7_DIR = REPO_ROOT / "chapter07_llm_control" / "lab_7_llm_control"
LAB7_TOOLS_DIR = LAB7_DIR / "tools"

if str(LAB8_DIR) not in sys.path:
    sys.path.insert(0, str(LAB8_DIR))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))
if str(LAB7_TOOLS_DIR) not in sys.path:
    sys.path.append(str(LAB7_TOOLS_DIR))

load_dotenv(LAB7_DIR / ".env", override=False)
load_dotenv(LAB8_DIR / ".env", override=True)

from perception.ball_detector import detect_red_ball  # noqa: E402
from perception.tracker_fsm import FSMState, H_REF, TrackerFSM  # noqa: E402
from robot_tools import (  # noqa: E402
    CONTROL_RATIO,
    PHYS_DT,
    TOOLS as BASE_TOOLS,
    dispatch as base_dispatch,
)
from starter import ChaseRobotState, VISION_HZ, _setup_head_renderer  # noqa: E402

FOLLOW_MAX_SECONDS = 15.0
FOLLOW_STOP_H = H_REF  # 像素高度达到 H_REF (30 px) 说明已靠近球前，提前停下


# ---------------------------------------------------------------------------
# VisionRobotState：给 ChaseRobotState 挂上持久化头部相机渲染器
# ---------------------------------------------------------------------------


class VisionRobotState(ChaseRobotState):
    """带一键拍图 capture_rgb() 与可设红球位置的追球机器人状态。"""

    def __init__(
        self,
        policy_name: str = "test",
        head_w: int = 320,
        head_h: int = 240,
        ball_pos: tuple[float, float, float] = (1.5, 0.3, 0.05),
    ):
        self._init_ball_pos = np.array(ball_pos, dtype=np.float64)
        self.head_w = head_w
        self.head_h = head_h
        super().__init__(policy_name=policy_name)
        self.head_cam_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_CAMERA, "head_cam",
        )
        self.head_renderer = _setup_head_renderer(self, w=head_w, h=head_h)

    def _reset_home(self) -> None:
        super()._reset_home()
        self.data.mocap_pos[0] = self._init_ball_pos.copy()
        mujoco.mj_forward(self.model, self.data)

    def set_ball_pos(self, x: float, y: float, z: float = 0.05) -> None:
        self._init_ball_pos = np.array([x, y, z], dtype=np.float64)
        self.data.mocap_pos[0] = self._init_ball_pos.copy()
        mujoco.mj_forward(self.model, self.data)

    def capture_rgb(self) -> np.ndarray:
        """从头部相机 head_cam 离屏渲染一帧 (H, W, 3) uint8 RGB 图像。"""
        self.head_renderer.update_scene(self.data, camera=self.head_cam_id)
        return self.head_renderer.render()

    def close(self) -> None:
        if getattr(self, "head_renderer", None) is not None:
            self.head_renderer.close()
            self.head_renderer = None


# ---------------------------------------------------------------------------
# 扩展工具 JSON Schema（第 7 章 4 工具 + 第 8 章 3 视觉工具）
# ---------------------------------------------------------------------------

EXTRA_VISION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "look_for",
            "description": (
                "Capture one frame from the robot's head camera and detect the target "
                "(currently supports 'red' / 'red ball'). Does NOT move the robot. "
                "Returns found, bbox, normalized horizontal error e_yaw (-1 left, +1 right), "
                "and rough distance_m."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Target name, e.g. 'red' or 'red ball'.",
                    },
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "follow",
            "description": (
                "Run closed-loop visual servoing (10 Hz HSV + TrackerFSM + 50 Hz RL gait) "
                "to walk toward the target for at most `seconds` seconds (0.5 to 15.0). "
                "Stops early once the ball is close enough (bbox height >= 30 px)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Target name, e.g. 'red' or 'red ball'.",
                    },
                    "seconds": {
                        "type": "number",
                        "description": "Max follow duration in seconds, range [0.5, 15.0].",
                    },
                },
                "required": ["target", "seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_vlm",
            "description": (
                "Send the current head camera image to a multimodal VLM to visually describe "
                "the scene or answer a high-level navigation question (e.g. what do you see, "
                "is the ball on the left or right, should the robot turn left/right/go straight). "
                "Use sparingly when semantic understanding is needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Specific visual question about the current camera frame.",
                    },
                },
                "required": ["question"],
            },
        },
    },
]

VISION_TOOLS = copy.deepcopy(BASE_TOOLS) + EXTRA_VISION_TOOLS


# ---------------------------------------------------------------------------
# TODO S1：单帧视觉探测 look_for()（教程 §8.8）
# ---------------------------------------------------------------------------


def look_for(target: str, robot: VisionRobotState) -> dict[str, Any]:
    """拍一帧头部相机图像，用 HSV 检测红球，返回结构化观测结果（不移动机器人）。

    实现提示
    --------
    1. 校验 target：若 "red" 不在 target.lower() 中（且不是 "红"），返回软失败
       {"ok": False, "error": f"unsupported HSV target: {target!r}, try 'red' or use ask_vlm"}
    2. 调 rgb = robot.capture_rgb()，再用 detect_red_ball(rgb) 拿到 box
    3. 若 box is None：返回 {"ok": True, "found": False, "pose": robot.get_pose()}
    4. 若检测到球：
       - 计算水平归一化偏差 e_yaw = (box["cx"] - robot.head_w / 2) / (robot.head_w / 2)
       - 粗估距离（小孔成像近似）：distance_m = round(H_REF / max(box["h"], 1) * 0.85, 2)
       - 返回 {"ok": True, "found": True, "bbox": box, "e_yaw": round(e_yaw, 3),
               "distance_m": distance_m, "pose": robot.get_pose()}
    """
    # ===== TODO S1 START =====
    if "red" not in target.lower() and "红" not in target:
        return {"ok": False, "error": f"unsupported HSV target: {target!r}, try 'red' or use ask_vlm"}
    rgb = robot.capture_rgb()
    box = detect_red_ball(rgb)
    if box is None:
        return {"ok": True, "found": False, "pose": robot.get_pose()}
    else:
        e_yaw = (box["cx"] - robot.head_w / 2) / (robot.head_w / 2)
        distance_m = round(H_REF / max(box["h"], 1) * 0.85, 2)
        return {"ok": True, "found": True, "bbox": box, "e_yaw": round(e_yaw, 3), "distance_m": distance_m, "pose": robot.get_pose()}
    # ===== TODO S1 END =====


# ---------------------------------------------------------------------------
# TODO S2：连续视觉伺服跟随 follow()（教程 §8.8）
# ---------------------------------------------------------------------------


def follow(
    target: str,
    seconds: float,
    robot: VisionRobotState,
    *,
    frame_callback: Callable[[VisionRobotState], None] | None = None,
) -> dict[str, Any]:
    """在本地运行 10 Hz 视觉伺服 + 50 Hz RL 步态追球，最多跑 seconds 秒。

    Parameters
    ----------
    target : 目标名称（需包含 'red' 或 '红'）
    seconds : 最长跟随秒数，需校验在 (0, FOLLOW_MAX_SECONDS] 范围内，否则返回软失败
    robot : VisionRobotState
    frame_callback : 可选录屏/3D Viewer 回调，每个物理步后调用 frame_callback(robot)

    实现提示
    --------
    1. 参数软校验：检查 target 与 seconds（注意先 float 强转并捕获 ValueError/TypeError）
    2. 初始化 fsm = TrackerFSM()、vision_interval = 1.0 / VISION_HZ、next_vision_time = robot.sim_time
       n_phys = max(1, int(seconds / PHYS_DT))、cmd = np.zeros(3, dtype=np.float32)
       current_state = FSMState.SEARCHING、current_vx = current_wz = 0.0、reached = False、last_box = None
    3. 循环 s in range(n_phys)：
       - t = robot.sim_time
       - 若 t >= next_vision_time：
           * rgb = robot.capture_rgb()
           * box = detect_red_ball(rgb)；boxes = [box] if box is not None else []
           * current_state, current_vx, current_wz = fsm.step(t, boxes, robot.head_w, robot.head_h)
           * next_vision_time = t + vision_interval
           * 若 box is not None：更新 last_box = box
           * 若 current_state == FSMState.TRACKING and box is not None and box["h"] >= FOLLOW_STOP_H：
               设 reached = True 并 break（已靠近到安全停步距离！）
       - 写入 cmd[0] = current_vx, cmd[2] = current_wz
       - 每 CONTROL_RATIO 步调 robot._policy_tick(cmd)
       - robot.data.ctrl[:] = robot.target_joints → mujoco.mj_step(robot.model, robot.data) → robot.phys_step += 1
       - 若 frame_callback is not None：调用 frame_callback(robot)
       - 若 robot.is_fallen()：返回 {"ok": False, "error": "robot fell during follow", "final_pose": robot.get_pose()}
    4. 返回汇总字典：
       {
           "ok": True,
           "reached": reached,
           "stopped_state": current_state.value,
           "final_box_h": last_box["h"] if last_box else None,
           "final_pose": robot.get_pose(),
       }
    """
    # ===== TODO S2 START =====
    if "red" not in target.lower() and "红" not in target:
        return {"ok": False, "error": f"unsupported target: {target!r}, try 'red'"}
    try:
        seconds = float(seconds)
    except(TypeError, ValueError):
        return {"ok": False, "error": f"seconds must be a number, got {seconds!r}"}
    if not (0.0 < seconds <= FOLLOW_MAX_SECONDS):
        return {"ok": False, "error": f"seconds={seconds} out of range (0, {FOLLOW_MAX_SECONDS}]"}
    fsm = TrackerFSM()
    vision_interval = 1.0 / VISION_HZ
    next_vision_time = robot.sim_time
    n_phys = max(1, int(seconds / PHYS_DT))
    cmd = np.zeros(3, dtype=np.float32)
    current_state = FSMState.SEARCHING
    current_vx = current_wz = 0.0
    reached = False
    last_box = None
    for s in range(n_phys):
        t = robot.sim_time
        if t >= next_vision_time:
            rgb = robot.capture_rgb()
            box = detect_red_ball(rgb)
            boxes = [box] if box is not None else []
            current_state, current_vx, current_wz = fsm.step(t, boxes, robot.head_w, robot.head_h)
            next_vision_time = t + vision_interval
            if box is not None: 
                last_box = box
                if current_state == FSMState.TRACKING and box is not None and box["h"] >= FOLLOW_STOP_H:
                    reached = True
                    break
        cmd[0] = max(current_vx, 0.35) if (current_state == FSMState.TRACKING and current_vx > 0.05) else current_vx
        cmd[2] = current_wz
        if s % CONTROL_RATIO == 0:
            robot._policy_tick(cmd)
        robot.data.ctrl[:] = robot.target_joints
        mujoco.mj_step(robot.model, robot.data)
        robot.phys_step += 1
        if frame_callback is not None:
            frame_callback(robot)
        if robot.is_fallen():
            return {"ok": False, "error": "robot fell during follow", "final_pose": robot.get_pose()}
    return {
                "ok": True,
                "reached": reached,
                "stopped_state": current_state.value,
                "final_box_h": last_box["h"] if last_box else None,
                "final_pose": robot.get_pose(),
            }
    # ===== TODO S2 END =====


# ---------------------------------------------------------------------------
# TODO S3：VLM 多模态看图 encode_rgb_b64() + ask_vlm()（教程 §8.8 进阶）
# ---------------------------------------------------------------------------


def encode_rgb_b64(rgb: np.ndarray) -> str:
    """将 (H, W, 3) uint8 RGB 数组在内存中编码为 PNG 的 base64 字符串（不落盘）。

    实现提示（4 行搞定）
    --------------------
    1. img = Image.fromarray(rgb)
    2. buf = BytesIO()
    3. img.save(buf, format="PNG")
    4. return base64.b64encode(buf.getvalue()).decode("ascii")
    """
    # ===== TODO S3A START =====
    img = Image.fromarray(rgb)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
    # ===== TODO S3A END =====


def ask_vlm(question: str, robot: VisionRobotState) -> dict[str, Any]:
    """拍一帧头部相机图像并发送给多模态 VLM（OpenAI 兼容接口）回答视觉问题。

    实现提示
    --------
    1. 读取环境变量：
       api_key = os.getenv("VLM_API_KEY")
       base_url = os.getenv("VLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
       model = os.getenv("VLM_MODEL", "gemini-2.5-flash")
       若 api_key 为空或仍是占位符 "paste-your-..."，返回软失败：
       {"ok": False, "error": "VLM_API_KEY not configured in lab_8_ball_chase/.env"}
    2. 拍图并编码：rgb = robot.capture_rgb() → b64 = encode_rgb_b64(rgb)
    3. 用 OpenAI(api_key=api_key, base_url=base_url) 构造客户端，调用 chat.completions.create：
       messages = [{
           "role": "user",
           "content": [
               {"type": "text", "text": question},
               {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
           ],
       }]
       （用 try/except Exception 捕获网络或接口异常，转成 {"ok": False, "error": ...} 软失败，绝不崩溃！）
    4. 取出 answer = resp.choices[0].message.content or ""，返回：
       {"ok": True, "model": model, "answer": answer.strip()}
    """
    # ===== TODO S3B START =====
    api_key = os.getenv("VLM_API_KEY")
    base_url = os.getenv("VLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    model = os.getenv("VLM_MODEL", "gemini-2.5-flash")
    if not api_key or api_key.startswith("paste-your"):
        return {"ok": False, "error": "VLM_API_KEY not configured in lab_8_ball_chase/.env"}
    rgb = robot.capture_rgb()
    b64 = encode_rgb_b64(rgb)
    client = OpenAI(api_key=api_key, base_url=base_url)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }]
    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=messages,
        )
    except Exception as exc:
        return {"ok": False, "error": f"VLM call failed: {exc}"}
    answer = resp.choices[0].message.content or ""
    return  {"ok": True, "model": model, "answer": answer.strip()}
    # ===== TODO S3B END =====


# ---------------------------------------------------------------------------
# 统一扩展分发器（已实现：老运动工具转发第 7 章，新视觉工具转发上面 3 个函数）
# ---------------------------------------------------------------------------


def vision_dispatch(
    name: str,
    args: dict[str, Any],
    robot: VisionRobotState,
    *,
    frame_callback: Callable[[VisionRobotState], None] | None = None,
) -> dict[str, Any]:
    """统一分发第 7 章运动工具与第 8 章视觉工具。"""
    if name == "look_for":
        if "target" not in args:
            return {"ok": False, "error": "missing required parameter: target"}
        return look_for(str(args["target"]), robot)

    if name == "follow":
        if "target" not in args or "seconds" not in args:
            return {"ok": False, "error": "missing required parameters: target, seconds"}
        return follow(
            str(args["target"]),
            args["seconds"],
            robot,
            frame_callback=frame_callback,
        )

    if name == "ask_vlm":
        if "question" not in args:
            return {"ok": False, "error": "missing required parameter: question"}
        return ask_vlm(str(args["question"]), robot)

    return base_dispatch(name, args, robot, frame_callback=frame_callback)


# ---------------------------------------------------------------------------
# 离线自测入口（验收 TODO S1–S3，无需消耗 LLM 额度）
# ---------------------------------------------------------------------------


def main() -> None:
    robot = VisionRobotState(policy_name="test", ball_pos=(1.5, 0.3, 0.05))
    try:
        robot.reset()
        print("1. 测试 look_for('red'):")
        r1 = look_for("red", robot)
        print("  ", r1)
        assert r1["ok"] is True and r1["found"] is True

        print("2. 测试 encode_rgb_b64():")
        rgb = robot.capture_rgb()
        b64 = encode_rgb_b64(rgb)
        print(f"   base64 长度={len(b64)} 字符 (前 24 字符: {b64[:24]}...)")
        assert len(b64) > 1000

        print("3. 测试 follow('red', 5.0):")
        r2 = follow("red", 5.0, robot)
        print("  ", r2)
        assert r2["ok"] is True

        print("4. 测试 ask_vlm():")
        r3 = ask_vlm(
            "What do you see in front of the quadruped robot? Is there a red ball on the left, center, or right? Reply in one short sentence.",
            robot,
        )
        print("  ", r3)
        print("vision_tools 自检完成！")
    finally:
        robot.close()


if __name__ == "__main__":
    main()
