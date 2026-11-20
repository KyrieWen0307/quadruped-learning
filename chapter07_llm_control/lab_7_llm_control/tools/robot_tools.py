"""Lab 7 工具定义 + RobotState + TODO 1 (dispatch)。

TOOLS 列表供 OpenAI-compatible SDK function calling 使用；
RobotState 封装 MuJoCo model/data + 上游 RTNeural policy（50 Hz 策略 / 500 Hz 物理）；
dispatch() 由学生完成（TODO 1）：负责参数校验、软失败与调用 RobotState。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import mujoco
import numpy as np

# ---------------------------------------------------------------------------
# 路径设置：复用 chapter06_policy_training/lab6/shared 资产
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).resolve().parent
LAB_DIR = _TOOLS_DIR.parent
REPO_ROOT = LAB_DIR.parents[1]
SHARED_ROOT = REPO_ROOT / "chapter06_policy_training" / "lab6"
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from shared.upstream.lab_5_mujoco import (  # noqa: E402
    MODEL_FLOATING,
    OBS_TOTAL,
    RTNeuralPolicy,
    build_obs_frame,
    load_policy,
    quat_inv_rotate,
    roll_obs_history,
)

PHYS_DT = 0.002
CONTROL_DT = 0.02
CONTROL_RATIO = int(round(CONTROL_DT / PHYS_DT))

# ---------------------------------------------------------------------------
# 工具 JSON schema（教程 §7.2）
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "walk",
            "description": (
                "Walk in the body frame for a fixed duration. "
                "Stops automatically when the duration elapses. " 
                "Returns final_pose plus unwrapped delta_yaw_rad, delta_turns, total_turns, and delta_dist_m."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vx": {
                        "type": "number",
                        "description": (
                            "forward speed m/s, range [-1.5, 1.5]. "
                            "Values below 0.2 may not produce visible motion."
                        ),
                    },
                    "wz": {
                        "type": "number",
                        "description": "yaw rate rad/s, range [-2.0, 2.0]",
                    },
                    "duration": {
                        "type": "number",
                        "description": "seconds, range (0, 10]",
                    },
                },
                "required": ["vx", "wz", "duration"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop",
            "description": "Immediately set commanded velocity to 0.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pose",
            "description": "Return current (x, y, yaw) in world frame.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Hold position for N seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "description": "seconds, range (0, 10]",
                    },
                },
                "required": ["seconds"],
            },
        },
    },
]

VX_RANGE = (-1.5, 1.5)
WZ_RANGE = (-2.0, 2.0)
DURATION_RANGE = (0.0, 10.0)


# ---------------------------------------------------------------------------
# RobotState — 封装 MuJoCo model/data + RTNeural policy 的运行状态
# ---------------------------------------------------------------------------

class RobotState:
    """面向 offscreen 渲染的仿真封装（无 viewer）。

    内部维护 obs_history / last_action，提供 step_cmd() / get_pose() / is_fallen()
    让 dispatch() 驱动底层物理与 RL 策略。
    """

    def __init__(self, policy_name: str = "test"):
        self.policy: RTNeuralPolicy = load_policy(policy_name)

        self.model = mujoco.MjModel.from_xml_path(str(MODEL_FLOATING))
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
        mujoco.mj_forward(self.model, self.data)
        self.obs_history[:] = 0.0
        self.last_action[:] = 0.0
        self.target_joints = self.policy.default_joint_pos.copy()
        self.phys_step = 0
        self.total_yaw = 0.0

    def reset(self) -> None:
        self._reset_home()
        self._settle(0.5)

    def _settle(self, seconds: float = 0.5) -> None:
        """PD 静稳：零 action 跑一段让机体站稳并填充 obs_history。"""
        n = int(seconds / PHYS_DT)
        cmd = np.zeros(3, dtype=np.float32)
        desired_z = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        for s in range(n):
            if s % CONTROL_RATIO == 0:
                quat = self.data.xquat[self.base_id].copy()
                world_ang = self.data.cvel[self.base_id, 0:3].copy()
                local_ang = quat_inv_rotate(quat, world_ang)
                gravity_b = quat_inv_rotate(quat, np.array([0.0, 0.0, -1.0]))
                n_g = np.linalg.norm(gravity_b)
                if n_g > 1e-6:
                    gravity_b = gravity_b / n_g
                joint_pos = self.data.qpos[7:19].copy()

                frame = build_obs_frame(
                    local_ang_vel=local_ang,
                    gravity_in_body=gravity_b,
                    command=cmd,
                    desired_world_z_in_body=desired_z,
                    joint_pos=joint_pos,
                    last_action=self.last_action,
                    default_pose=self.policy.default_joint_pos.astype(np.float64),
                )
                self.obs_history = roll_obs_history(self.obs_history, frame)
                action = np.zeros(12, dtype=np.float32)
                self.last_action = action.copy()
                self.target_joints = (
                    self.policy.default_joint_pos + self.policy.action_scale * action
                )
                self.data.ctrl[:] = self.target_joints

            mujoco.mj_step(self.model, self.data)
            self.phys_step += 1

    def _policy_tick(self, cmd: np.ndarray) -> None:
        """50 Hz policy 更新。"""
        quat = self.data.xquat[self.base_id].copy()
        world_ang = self.data.cvel[self.base_id, 0:3].copy()
        local_ang = quat_inv_rotate(quat, world_ang)
        gravity_b = quat_inv_rotate(quat, np.array([0.0, 0.0, -1.0]))
        n = np.linalg.norm(gravity_b)
        if n > 1e-6:
            gravity_b = gravity_b / n
        joint_pos = self.data.qpos[7:19].copy()
        desired_z = np.array([0.0, 0.0, 1.0], dtype=np.float32)

        frame = build_obs_frame(
            local_ang_vel=local_ang,
            gravity_in_body=gravity_b,
            command=cmd,
            desired_world_z_in_body=desired_z,
            joint_pos=joint_pos,
            last_action=self.last_action,
            default_pose=self.policy.default_joint_pos.astype(np.float64),
        )
        self.obs_history = roll_obs_history(self.obs_history, frame)
        action = self.policy.forward(self.obs_history)
        self.last_action = action.copy()
        self.target_joints = (
            self.policy.default_joint_pos + self.policy.action_scale * action
        )

    def step_cmd(
        self,
        vx: float,
        wz: float,
        duration: float,
        *,
        frame_callback: Callable[["RobotState"], None] | None = None,
    ) -> dict[str, Any]:
        """以 (vx, 0, wz) 命令跑 duration 秒，返回结果字典。

        frame_callback(self) 在每个物理步后被调用，用于 GIF 采帧。
        """
        cmd = np.array([vx, 0.0, wz], dtype=np.float32)
        n_phys = max(1, int(duration / PHYS_DT))
        prev_yaw = self._raw_yaw()
        target_yaw = prev_yaw
        hold_heading = (wz == 0.0 and abs(vx) > 0.0)
        delta_yaw = 0.0
        x0, y0 = float(self.data.qpos[0]), float(self.data.qpos[1])
        yaw_err_int = 0.0
        for s in range(n_phys):
            if s % CONTROL_RATIO == 0:
                if hold_heading:
                    yaw_err = (target_yaw - self._raw_yaw() + np.pi) % (2.0 * np.pi) - np.pi
                    yaw_err_int = float(np.clip(yaw_err_int + yaw_err * CONTROL_DT, -0.5, 0.5))
                    wz_eff = float(np.clip(2.0 * yaw_err + 2.5 * yaw_err_int, -WZ_RANGE[1], WZ_RANGE[1]))
                    cmd = np.array([vx, 0.0, wz_eff], dtype=np.float32)
                self._policy_tick(cmd)
            self.data.ctrl[:] = self.target_joints
            mujoco.mj_step(self.model, self.data)
            self.phys_step += 1
            curr_yaw = self._raw_yaw()
            dyaw = (curr_yaw - prev_yaw + np.pi) % (2.0 * np.pi) - np.pi
            delta_yaw += dyaw
            self.total_yaw += dyaw
            prev_yaw = curr_yaw

            if frame_callback is not None:
                frame_callback(self)

            if self.is_fallen():
                return {
                    "ok": False,
                    "error": "robot fell mid-walk",
                    "final_pose": self.get_pose(),
                }
        delta_dist = float(np.hypot(float(self.data.qpos[0]) - x0, float(self.data.qpos[1]) - y0))
        return {"ok": True, "final_pose": self.get_pose(), "delta_yaw_rad": round(delta_yaw, 3),"delta_turns": round(delta_yaw / (2.0 * np.pi),3),"total_turns": round(self.total_yaw / (2.0 * np.pi), 3),"delta_dist_m": round(delta_dist, 3)}
    
    def _raw_yaw(self) -> float:
        quat = self.data.xquat[self.base_id].copy()
        return float(np.arctan2(
            2.0 * (quat[0] * quat[3] + quat[1] * quat[2]),
            1.0 - 2.0 * (quat[2] ** 2 + quat[3] ** 2),
        ))

    def get_pose(self) -> list[float]:
        x = float(self.data.qpos[0])
        y = float(self.data.qpos[1])
        yaw = self._raw_yaw()
        return [round(x, 3), round(y, 3), round(yaw, 3)]

    def is_fallen(self) -> bool:
        base_z = float(self.data.qpos[2])
        if base_z < 0.05:
            return True
        R = self.data.xmat[self.base_id].reshape(3, 3)
        roll = abs(float(np.arctan2(R[2, 1], R[2, 2])))
        pitch = abs(float(np.arctan2(
            -R[2, 0], np.sqrt(R[2, 1] ** 2 + R[2, 2] ** 2),
        )))
        return roll > 0.7 or pitch > 0.7

    @property
    def sim_time(self) -> float:
        return self.phys_step * PHYS_DT


# ---------------------------------------------------------------------------
# TODO 1: dispatch 入口（学生实现）
# ---------------------------------------------------------------------------

def dispatch(
    name: str,
    args: dict[str, Any],
    robot: RobotState,
    *,
    frame_callback: Callable[[RobotState], None] | None = None,
) -> dict[str, Any]:

    try:
        if name == 'walk':
            vx = float(args['vx'])
            wz = float(args['wz'])
            duration = float(args['duration'])
            if not (VX_RANGE[0] <= vx <= VX_RANGE[1]):
                return {"ok": False, "error": f"vx out of range [{VX_RANGE[0]}, {VX_RANGE[1]}]"}
            elif not(WZ_RANGE[0] <= wz <= WZ_RANGE[1]):
                return {"ok": False, "error": f"wz out of range [{WZ_RANGE[0]}, {WZ_RANGE[1]}]"}
            elif not(DURATION_RANGE[0] < duration <= DURATION_RANGE[1]):
                return {"ok": False, "error": f"duration out of range ({DURATION_RANGE[0]}, {DURATION_RANGE[1]}]"}
            elif robot.is_fallen():
                return {"ok": False, "error": 'robot is fallen.'}
            return robot.step_cmd(vx, wz, duration, frame_callback=frame_callback)
        elif name == 'stop':
            return robot.step_cmd(0.0,0.0,0.5,frame_callback=frame_callback)
        elif name == 'get_pose':
            return {"ok": True, "pose": robot.get_pose()}
        elif name == 'wait':
            seconds = float(args['seconds'])
            if not(DURATION_RANGE[0] < seconds <= DURATION_RANGE[1]):
                return {"ok": False, "error": f"wait time out of range ({DURATION_RANGE[0]}, {DURATION_RANGE[1]}]"}
            return robot.step_cmd(0.0, 0.0, seconds, frame_callback=frame_callback)
        else:
            return {"ok": False, "error": f"unknown tool: {name}"}
    except Exception as e: 
        return {'ok':False, 'error':str(e)}
    

            
    """执行工具调用，返回 JSON-able 结果。绝不 raise，只在返回值里写错误。

    要求（对应教程 §7.2 / §7.5 与 tests.py 7 项断言）：
    1. 用 try / except Exception as e 包住整个函数，任何意外异常都返回
       {"ok": False, "error": str(e)}，绝不抛出。
    2. 分发 4 个工具 + 未知工具：
       - "walk":
           * 从 args 取出 vx, wz, duration 并转为 float
           * 校验 VX_RANGE[0] <= vx <= VX_RANGE[1]（越界返回含 "vx" 和 "range" 的 error）
           * 校验 WZ_RANGE[0] <= wz <= WZ_RANGE[1]
           * 校验 DURATION_RANGE[0] < duration <= DURATION_RANGE[1]（注意左开右闭，0 不合法）
           * 检查 robot.is_fallen()，倒了就返回 {"ok": False, "error": ...}
           * 全部通过 → 返回 robot.step_cmd(vx, wz, duration, frame_callback=frame_callback)
       - "stop":
           * 调用 robot.step_cmd(0.0, 0.0, 0.5, frame_callback=frame_callback)
       - "get_pose":
           * 返回 {"ok": True, "pose": robot.get_pose()}
       - "wait":
           * 从 args 取出 seconds 并转为 float
           * 校验 DURATION_RANGE[0] < seconds <= DURATION_RANGE[1]
           * 返回 robot.step_cmd(0.0, 0.0, seconds, frame_callback=frame_callback)
       - 其他工具名:
           * 返回 {"ok": False, "error": f"unknown tool: {name}"}
    """
