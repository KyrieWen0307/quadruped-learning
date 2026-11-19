"""Pupper RL Gymnasium 环境（CPU/SB3 路径）。

奖励配方 + 命令分布 + 观测设计 + 域随机化全部与 MJX/brax 版（`pupper_env_mjx.py`）
对齐，使 SB3 / SubprocVecEnv 路径能复现 brax-PPO 200M 步的训练结果。

关键设计：
- 观测：36 维 / step × 15 帧 stack = 540（IMU 6 + cmd 3 + desired_world_z 3 + 关节角差 12
  + last_act 12），含 IMU latency + 观测噪声 + 动作 latency。
- 奖励：18 项，penalty 项 term 返回正幅值、权重写负；tracking 项权重写正。
  最终 reward = sum(scale × term) × dt，clip 到 [0, 10000]。
- 命令：vx ∈ [-0.75, 0.75]，vy ∈ [-0.5, 0.5]，wz ∈ [-2.0, 2.0]，
  以 1% 概率回零命令，step 500 处中途重采样。
- 域随机化：随机初始位姿 + 偶发 kick + 观测噪声 + 动作延迟。
- 物理：250 Hz physics（0.004 s）× 5 = 50 Hz control（0.02 s），与 MJX 版一致。
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

EXERCISES_DIR = Path(__file__).resolve().parents[2]
if str(EXERCISES_DIR) not in sys.path:
    sys.path.insert(0, str(EXERCISES_DIR))

from shared.rl.obs_helpers import base_local_gravity  # noqa: E402

DEFAULT_XML = str(EXERCISES_DIR / "shared" / "models" / "pupper_v3_floating.xml")

JOINT_NAMES = [
    "leg_front_r_1", "leg_front_r_2", "leg_front_r_3",
    "leg_front_l_1", "leg_front_l_2", "leg_front_l_3",
    "leg_back_r_1",  "leg_back_r_2",  "leg_back_r_3",
    "leg_back_l_1",  "leg_back_l_2",  "leg_back_l_3",
]

FOOT_BODIES = [
    "leg_front_r_3",
    "leg_front_l_3",
    "leg_back_r_3",
    "leg_back_l_3",
]

FOOT_SITES = [
    "leg_front_r_3_foot_site",
    "leg_front_l_3_foot_site",
    "leg_back_r_3_foot_site",
    "leg_back_l_3_foot_site",
]

UPPER_LEG_BODIES = [
    "leg_front_r_2",
    "leg_front_l_2",
    "leg_back_r_2",
    "leg_back_l_2",
]

# Reward weight table — penalty 项 term 返回正幅值，权重写负；tracking 项写正。
REWARD_WEIGHTS = {
    "tracking_lin_vel": 1.5,
    "tracking_ang_vel": 0.8,
    "tracking_orientation": 1.0,
    "lin_vel_z": -2.0,
    "ang_vel_xy": -0.05,
    "orientation": -5.0,
    "torques": -2e-4,
    "joint_acceleration": -1e-6,
    "mechanical_work": 0.0,
    "action_rate": -0.01,
    "feet_air_time": 0.2,
    "stand_still": -0.5,
    "stand_still_joint_velocity": -0.1,
    "abduction_angle": -0.1,
    "termination": -100.0,
    "foot_slip": -0.1,
    "knee_collision": -1.0,
    "body_collision": -1.0,
}

TRACKING_SIGMA = 0.25
AIR_TIME_TARGET = 0.1
CMD_DEAD_ZONE = 0.05
STAND_STILL_THRESHOLD = 0.1

KP = 5.0
KD = 0.25
ACTION_SCALE = 1.0
MAX_STEPS = 1000

# Bar F 物理：control 50 Hz，physics 250 Hz
DT_CONTROL = 0.02
DT_PHYSICS = 0.004

# 命令分布
CMD_VX_RANGE = (-0.75, 0.75)
CMD_VY_RANGE = (-0.5, 0.5)
CMD_WZ_RANGE = (-2.0, 2.0)
ZERO_CMD_PROB = 0.01
RESAMPLE_STEP = 500

# default_pose（与 MJX 版 literal 一致；不再用 IK 求 stance_q）
DEFAULT_POSE = np.array(
    [0.26, 0.0, -0.52, -0.26, 0.0, 0.52, 0.26, 0.0, -0.52, -0.26, 0.0, 0.52],
    dtype=np.float64,
)
DESIRED_ABDUCTION = np.zeros(4, dtype=np.float64)

# 终止条件
TERMINAL_BODY_Z = 0.10
TERMINAL_BODY_ANGLE = 0.52  # rad ≈ 30°
EARLY_TERMINATION_STEP = 500

# 域随机化幅度
ANG_VEL_NOISE = 0.3
GRAVITY_NOISE = 0.1
MOTOR_ANGLE_NOISE = 0.1
LAST_ACTION_NOISE = 0.01
KICK_VEL = 0.2
KICK_PROBABILITY = 0.02
START_POS_RANGE = (-2.0, 2.0, -2.0, 2.0, 0.15, 0.20)  # x_min, x_max, y_min, y_max, z_min, z_max

# action / IMU latency 分布（与 MJX 版一致）
ACTION_LATENCY_DIST = np.array([0.2, 0.8], dtype=np.float64)  # 80% lagged by 1 step
IMU_LATENCY_DIST = np.array([0.5, 0.5], dtype=np.float64)

# 关节角软限位（与 MJX 版一致）
JOINT_LOWERS = np.array(
    [-1.220, -0.420, -2.790, -2.510, -3.140, -0.710,
     -1.220, -0.420, -2.790, -2.510, -3.140, -0.710],
    dtype=np.float64,
)
JOINT_UPPERS = np.array(
    [2.510, 3.140, 0.710, 1.220, 0.420, 2.790,
     2.510, 3.140, 0.710, 1.220, 0.420, 2.790],
    dtype=np.float64,
)

# Frame stack 大小，与 MJX 版的 observation_history 一致
N_STACK = 15
OBS_DIM_PER_STEP = 36
OBS_DIM_STACKED = N_STACK * OBS_DIM_PER_STEP  # = 540

FOOT_RADIUS = 0.02


class PupperEnv(gym.Env):
    """CPU/SB3 训练用 Pupper 环境，与 MJX/brax 版逐项对齐。"""

    metadata = {"render_modes": ["rgb_array"]}

    def __init__(self, xml: str = DEFAULT_XML, max_steps: int = MAX_STEPS):
        super().__init__()
        self.model = mujoco.MjModel.from_xml_path(xml)
        self.data = mujoco.MjData(self.model)
        self.model.opt.timestep = DT_PHYSICS
        self.dt = DT_CONTROL
        self.n_substeps = max(1, int(round(DT_CONTROL / DT_PHYSICS)))
        self.max_steps = max_steps

        self.action_space = spaces.Box(-1.0, 1.0, (12,), np.float32)
        self.observation_space = spaces.Box(
            -100.0, 100.0, (OBS_DIM_STACKED,), np.float32,
        )

        self._base_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "base_link")
        self._joint_qpos_ids = []
        self._joint_qvel_ids = []
        for name in JOINT_NAMES:
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            self._joint_qpos_ids.append(int(self.model.jnt_qposadr[jid]))
            self._joint_qvel_ids.append(int(self.model.jnt_dofadr[jid]))
        self._joint_qpos_ids = np.array(self._joint_qpos_ids, dtype=int)
        self._joint_qvel_ids = np.array(self._joint_qvel_ids, dtype=int)

        self._foot_site_ids = np.array([
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, n) for n in FOOT_SITES
        ], dtype=int)
        self._lower_leg_body_ids = np.array([
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, n) for n in FOOT_BODIES
        ], dtype=int)

        # geom ids for collision-based penalties
        body_id_torso = self._base_id
        self._torso_geom_ids = self._body_to_geom_ids(body_id_torso)
        self._upper_leg_geom_ids = np.concatenate([
            self._body_to_geom_ids(mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, n))
            for n in UPPER_LEG_BODIES
        ])

        self._setup_pd()

        # 内部 buffer
        self._action_buffer = np.zeros((12, ACTION_LATENCY_DIST.shape[0]), dtype=np.float64)
        self._imu_buffer = np.zeros((6, IMU_LATENCY_DIST.shape[0]), dtype=np.float64)
        self._imu_buffer[5, :] = -1.0  # gravity z=-1 initially
        self._obs_history = np.zeros(OBS_DIM_STACKED, dtype=np.float32)

        self.last_action = np.zeros(12, dtype=np.float32)
        self.last_joint_vel = np.zeros(12, dtype=np.float64)
        self.last_contact = np.zeros(4, dtype=bool)
        self.feet_air_time = np.zeros(4, dtype=np.float64)
        self.cmd = np.zeros(3, dtype=np.float32)
        self.desired_world_z = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        self.step_count = 0

    def _body_to_geom_ids(self, body_id: int) -> np.ndarray:
        adr = int(self.model.body_geomadr[body_id])
        n = int(self.model.body_geomnum[body_id])
        return np.arange(adr, adr + n, dtype=int)

    def _setup_pd(self) -> None:
        self.model.actuator_gainprm[:, 0] = KP
        self.model.actuator_biasprm[:, 1] = -KP
        self.model.actuator_biasprm[:, 2] = -KD

    # ----------------- gym API -----------------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        mujoco.mj_resetData(self.model, self.data)

        # 随机初始位置 + yaw
        x_min, x_max, y_min, y_max, z_min, z_max = START_POS_RANGE
        x0 = self.np_random.uniform(x_min, x_max)
        y0 = self.np_random.uniform(y_min, y_max)
        z0 = self.np_random.uniform(z_min, z_max)
        yaw = self.np_random.uniform(-np.pi, np.pi)
        self.data.qpos[0] = x0
        self.data.qpos[1] = y0
        self.data.qpos[2] = z0
        self.data.qpos[3] = np.cos(yaw / 2)
        self.data.qpos[4] = 0.0
        self.data.qpos[5] = 0.0
        self.data.qpos[6] = np.sin(yaw / 2)
        self.data.qpos[self._joint_qpos_ids] = DEFAULT_POSE
        self.data.qvel[:] = 0.0
        self.data.ctrl[:] = DEFAULT_POSE
        mujoco.mj_forward(self.model, self.data)

        self._action_buffer[:] = 0.0
        self._imu_buffer[:] = 0.0
        self._imu_buffer[5, :] = -1.0
        self._obs_history[:] = 0.0

        self.last_action[:] = 0.0
        self.last_joint_vel[:] = 0.0
        self.last_contact[:] = False
        self.feet_air_time[:] = 0.0
        self.cmd = self._sample_command()
        self.desired_world_z[:] = np.array([0.0, 0.0, 1.0])
        self.step_count = 0

        obs = self._get_obs()
        return obs, {}

    def step(self, action):
        action = np.asarray(action, dtype=np.float32).clip(-1.0, 1.0)

        # 偶发 kick：base 线速度被打扰
        if self.np_random.uniform() < KICK_PROBABILITY:
            dvx = self.np_random.uniform(-1, 1) * KICK_VEL
            dvy = self.np_random.uniform(-1, 1) * KICK_VEL
            self.data.qvel[0] += dvx
            self.data.qvel[1] += dvy

        # action latency
        lagged_action, self._action_buffer = _sample_lagged(
            self.np_random, self._action_buffer, action.astype(np.float64), ACTION_LATENCY_DIST,
        )
        motor_targets = DEFAULT_POSE + lagged_action * ACTION_SCALE
        motor_targets = np.clip(motor_targets, JOINT_LOWERS, JOINT_UPPERS)
        self.data.ctrl[:] = motor_targets
        for _ in range(self.n_substeps):
            mujoco.mj_step(self.model, self.data)

        joint_angles = self.data.qpos[self._joint_qpos_ids].astype(np.float64)
        joint_vel = self.data.qvel[self._joint_qvel_ids].astype(np.float64)

        # foot contact via site z
        foot_z = self.data.site_xpos[self._foot_site_ids][:, 2] - FOOT_RADIUS
        contact = foot_z < 1e-3
        contact_filt_mm = contact | self.last_contact
        contact_filt_cm = (foot_z < 3e-2) | self.last_contact
        first_contact = (self.feet_air_time > 0) & contact_filt_mm
        self.feet_air_time = self.feet_air_time + self.dt

        # 终止判定
        up_in_body = self._gravity_in_body() * -1.0  # gravity 是 (-z) in world，body 帧投影后 z 分量
        done_orient = up_in_body[2] < np.cos(TERMINAL_BODY_ANGLE)
        done_joint = bool(np.any(joint_angles < JOINT_LOWERS) or np.any(joint_angles > JOINT_UPPERS))
        done_height = self.data.qpos[2] < TERMINAL_BODY_Z
        terminated = bool(done_orient or done_joint or done_height)

        reward, info = self._compute_reward(action, joint_angles, joint_vel, contact_filt_cm, first_contact, terminated)

        # 更新 state.info
        self.last_action = action.copy()
        self.last_joint_vel = joint_vel
        self.feet_air_time = self.feet_air_time * (~contact_filt_mm).astype(np.float64)
        self.last_contact = contact
        self.step_count += 1

        truncated = self.step_count >= self.max_steps
        # Changing commands should not reset the elapsed episode steps.
        if self.step_count % RESAMPLE_STEP == 0 and not (terminated or truncated):
            self.cmd = self._sample_command()

        obs = self._get_obs()
        return obs, reward, terminated, truncated, info

    # ----------------- reward -----------------

    def _compute_reward(self, action, joint_angles, joint_vel, contact_filt_cm, first_contact, terminated):
        """TODO 1: Compute all 18 raw terms and apply REWARD_WEIGHTS.

        Return the bounded reward after multiplying by dt, and a dict of weighted r_* components.
        """
        R = self.data.xmat[self._base_id].reshape(3,3)
        local_vel = R.T @self.data.qvel[0:3]
        vel_err = np.sum((self.cmd[:2] - local_vel[0:2])**2)
        vel_r = np.exp(-vel_err/TRACKING_SIGMA)
        ang_err = (self.cmd[2] - self.data.qvel[5])**2
        ang_r = np.exp(-ang_err/TRACKING_SIGMA)
        ori_err = np.sum((-self._gravity_in_body()-self.desired_world_z)**2)
        ori_r = np.exp(- ori_err/TRACKING_SIGMA)
        r_lin_vel_z = (self.data.qvel[2])**2
        ang_vel_world = R@self.data.qvel[3:6]
        r_ang_vel_xy = np.sum(ang_vel_world[:2]**2)
        rot_up = R @ np.array([0.0,0.0,1.0])
        ori_r2 = np.sum(rot_up[:2]**2)
        torques = self.data.qfrc_actuator[self._joint_qvel_ids]
        r_torques = np.sum(torques**2)
        joint_acc = (joint_vel - self.last_joint_vel)/self.dt
        r_joint_acc = np.sum(joint_acc**2)
        me_work = torques * joint_vel
        r_me_work = np.sum(np.abs(me_work))
        r_action_rate = np.sum((action-self.last_action)**2)
        cmd_norm = np.linalg.norm(self.cmd)
        r_feet_air_time = np.sum((self.feet_air_time - AIR_TIME_TARGET) * first_contact) * (cmd_norm > CMD_DEAD_ZONE)
        r_stand_still = np.sum(np.abs(joint_angles - DEFAULT_POSE)) * (cmd_norm < STAND_STILL_THRESHOLD)
        r_stand_still_joint_vel = np.sum(np.abs(joint_vel)) * (cmd_norm < STAND_STILL_THRESHOLD)
        r_abduction_angle = np.sum((joint_angles[1::3] - DESIRED_ABDUCTION) ** 2)
        termination = float(terminated and self.step_count < EARLY_TERMINATION_STEP)
        r_foot_slip = 0.0
        for i, sid in enumerate(self._foot_site_ids):
            if contact_filt_cm[i]:
                vel6 = np.zeros(6)
                mujoco.mj_objectVelocity(
                    self.model, self.data,
                    mujoco.mjtObj.mjOBJ_SITE,
                int(sid),
                    vel6, 0,
                )
                r_foot_slip += np.sum(vel6[3:5]**2)
        knee_col = 0
        body_col = 0
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            if c.dist < 0.0 and (c.geom1 in set(self._upper_leg_geom_ids) or c.geom2 in set(self._upper_leg_geom_ids)):
                knee_col += 1
            if c.dist < 0.0 and (c.geom1 in set(self._torso_geom_ids) or c.geom2 in set(self._torso_geom_ids)):
                body_col +=1
        
        terms = {
            'tracking_lin_vel' : vel_r,
            'tracking_ang_vel' : ang_r,
            'tracking_orientation' : ori_r,
            'lin_vel_z' : r_lin_vel_z,
            'ang_vel_xy' : r_ang_vel_xy,
            'orientation' : ori_r2,
            'torques' : r_torques,
            'joint_acceleration' : r_joint_acc,
            'mechanical_work' : r_me_work,
            'action_rate' : r_action_rate,
            'feet_air_time' : r_feet_air_time,
            'stand_still' : r_stand_still,
            'stand_still_joint_velocity' : r_stand_still_joint_vel,
            'abduction_angle' : r_abduction_angle,
            'termination' : termination,
            'foot_slip' : r_foot_slip,
            'knee_collision' : knee_col,
            'body_collision' : body_col
        }
        info = {}
        for k, v in terms.items():
            info[f'r_{k}'] = float(v * REWARD_WEIGHTS[k])
        reward = float(np.clip(sum(info.values()) * self.dt, 0.0, 10000.0))
        return reward, info
    # ----------------- helpers -----------------

    def _gravity_in_body(self) -> np.ndarray:
        R = self.data.xmat[self._base_id].reshape(3, 3)
        return R.T @ np.array([0.0, 0.0, -1.0])

    def _get_obs(self) -> np.ndarray:
        # IMU 数据：local angular vel + gravity in body
        """TODO 2: Build noisy and delayed observations, then stack 15 frames.

        Newest frame first. Each frame: IMU(6), cmd(3), desired z(3), joint angle offsets(12), last action(12). Return a float32 copy.
        """
        gyro = self.data.sensor("body_gyro").data
        noise = self.np_random.uniform(-ANG_VEL_NOISE, ANG_VEL_NOISE, size=3)
        gravity = self._gravity_in_body()
        gravity_noise = self.np_random.uniform(
            -GRAVITY_NOISE, GRAVITY_NOISE, size=3,
        )
        gravity_obs = gravity + gravity_noise
        gravity_obs = gravity_obs / np.linalg.norm(gravity_obs)

        imu_now = np.concatenate([gyro + noise, gravity_obs])
        joint_angles = self.data.qpos[self._joint_qpos_ids].astype(np.float64)
        joint_delta = joint_angles - DEFAULT_POSE
        lagged_imu, self._imu_buffer = _sample_lagged(self.np_random,self._imu_buffer,imu_now, IMU_LATENCY_DIST)
        joint_delta = joint_delta + self.np_random.uniform(
            -MOTOR_ANGLE_NOISE, MOTOR_ANGLE_NOISE, size=12,
        )
        last_action_obs = self.last_action + self.np_random.uniform(
            -LAST_ACTION_NOISE,LAST_ACTION_NOISE,size=12
        )
        obs_step = np.concatenate([lagged_imu,self.cmd,self.desired_world_z,joint_delta,last_action_obs])
        obs_step = np.array(obs_step,dtype=np.float32)
        obs_step = np.clip(obs_step, -100.0, 100.0)
        self._obs_history = np.roll(self._obs_history, OBS_DIM_PER_STEP)
        self._obs_history[:OBS_DIM_PER_STEP]=obs_step
        return self._obs_history.copy()


    def _sample_command(self) -> np.ndarray:
        """TODO 3: Sample vx, vy, wz with self.np_random.

        Return float32 shape (3,). Match the official wide ranges and near-zero branch.
        """
        if self.np_random.uniform() < ZERO_CMD_PROB:
            cmd = self.np_random.uniform(-STAND_STILL_THRESHOLD,STAND_STILL_THRESHOLD,size=3)
        else:
            vx = self.np_random.uniform(*CMD_VX_RANGE)
            vy = self.np_random.uniform(*CMD_VY_RANGE)
            wz = self.np_random.uniform(*CMD_WZ_RANGE)
            cmd = [vx,vy,wz]
        cmd = np.array(cmd,dtype=np.float32)
        return cmd

def _sample_lagged(
    rng: np.random.Generator, buffer_newest_first: np.ndarray, new_value: np.ndarray, distribution: np.ndarray,
):
    """Push `new_value` to front of buffer, sample one column weighted by `distribution`."""
    buf = np.roll(buffer_newest_first, shift=1, axis=1)
    buf[:, 0] = new_value
    idx = rng.choice(buf.shape[1], p=distribution)
    return buf[:, idx].copy(), buf


class FrameStackedPupperEnv(gym.Env):
    """Backward-compat wrapper.

    Bar D 版本通过这个 wrapper 把 49-dim flat obs stack 15 帧。本版本 `PupperEnv`
    内部已经做了 15 帧 stack（与 MJX/brax 版一致），所以这个 wrapper 退化为
    透明 passthrough，保留接口避免破坏 starter.py 等老调用点。
    """

    metadata = {"render_modes": ["rgb_array"]}

    def __init__(self, n_stack: int = N_STACK, **inner_kwargs):
        super().__init__()
        if n_stack != N_STACK:
            raise ValueError(
                f"PupperEnv 内置 stack={N_STACK} 帧；FrameStackedPupperEnv "
                f"传 n_stack={n_stack} 没意义。请直接用 PupperEnv 或保持默认。"
            )
        self.inner = PupperEnv(**inner_kwargs)
        self.action_space = self.inner.action_space
        self.observation_space = self.inner.observation_space

    def reset(self, *, seed=None, options=None):
        return self.inner.reset(seed=seed, options=options)

    def step(self, action):
        return self.inner.step(action)

    def __getattr__(self, name):
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.__dict__["inner"], name)
