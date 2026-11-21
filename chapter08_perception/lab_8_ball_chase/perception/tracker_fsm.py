"""P 控制器 visual_servo + TrackerFSM（教程 §8.4–§8.5 · 学生 TODO 2）。"""

from __future__ import annotations

import enum

import numpy as np

KP_YAW = 1.0
KP_VX = 0.4
H_REF = 30          # 像素：球在画面中占这个高度时认为“够近了”
SEARCH_WZ = 0.6     # SEARCHING 状态下的原地慢转角速度 (rad/s)
LOST_TIMEOUT = 2.0  # 丢失目标超时阈值 (s)


class FSMState(enum.Enum):
    SEARCHING = "SEARCHING"
    TRACKING = "TRACKING"
    STOPPED = "STOPPED"


def visual_servo(
    box: dict,
    image_w: int,
    image_h: int,
) -> tuple[float, float]:
    """根据 bbox 计算底盘速度命令 (vx, wz)。

    Parameters
    ----------
    box : detect_red_ball 返回的 dict（含 cx, cy, w, h, area）
    image_w, image_h : 图像宽、高（像素）

    Returns
    -------
    (vx, wz) : float 二元组

    实现提示
    --------
    1. 水平归一化偏差：e_yaw = (box["cx"] - image_w / 2) / (image_w / 2)
       球在右侧（e_yaw > 0）需顺时针右转（wz < 0），故 wz = -KP_YAW * e_yaw
    2. 尺寸距离误差：e_size = max(0.0, 1.0 - box["h"] / H_REF)
       box["h"] < H_REF 说明球还远，给正向 vx = KP_VX * e_size；靠近后停下（vx = 0）
    3. 返回 (float(vx), float(wz))
    """
    # ===== TODO 2A START =====
    e_yaw = (box["cx"] - image_w / 2) / (image_w / 2)
    wz = -KP_YAW * e_yaw
    e_size = max(0.0, 1.0 - box["h"] / H_REF)
    vx = KP_VX * e_size
    return (float(vx),float(wz))
    # ===== TODO 2A END =====


class TrackerFSM:
    """三态追踪状态机：SEARCHING ↔ TRACKING → STOPPED。"""

    def __init__(self) -> None:
        self.state = FSMState.SEARCHING
        self._last_seen: float = 0.0
        self._last_box: dict | None = None

    def reset(self) -> None:
        self.state = FSMState.SEARCHING
        self._last_seen = 0.0
        self._last_box = None

    def step(
        self,
        t: float,
        boxes: list[dict],
        image_w: int,
        image_h: int,
    ) -> tuple[FSMState, float, float]:
        """根据当前检测结果更新状态，返回 (state, vx, wz)。

        Parameters
        ----------
        t : 当前仿真时间 (s)
        boxes : 检测到的 bbox 列表（0 个或多个）
        image_w, image_h : 图像宽、高

        实现提示
        --------
        1. 先用 box = self._select(boxes) 选出目标框：
           - 若 box is not None：更新 _last_seen=t、_last_box=box、state=FSMState.TRACKING，
             用 visual_servo(box, image_w, image_h) 返回 (self.state, vx, wz)。
        2. 若未检测到球，计算 lost_duration = t - self._last_seen：
           - 若当前处于 TRACKING：
             * lost_duration > LOST_TIMEOUT → 切入 SEARCHING（继续落到下方 SEARCHING 分支）；
             * 否则（短暂遮挡/丢帧）保持 TRACKING，若 _last_box 存在则按上一帧 visual_servo 减速 0.5 倍惯性跟随，否则返回 (self.state, 0.0, 0.0)。
           - 若当前处于 SEARCHING：
             * lost_duration > LOST_TIMEOUT * 3 → 切入 STOPPED 并返回 (self.state, 0.0, 0.0)；
             * 否则原地慢转寻找：返回 (self.state, 0.0, SEARCH_WZ)。
           - 若处于 STOPPED：返回 (self.state, 0.0, 0.0)。
        """
        # ===== TODO 2B START =====
        box = self._select(boxes)
        if box:
            self._last_seen = t
            self._last_box = box
            self.state = FSMState.TRACKING
            vx, wz = visual_servo(box, image_w, image_h)
            return self.state, vx, wz
        else:
            lost_duration = t - self._last_seen
            if self.state == FSMState.TRACKING:
                if lost_duration <= LOST_TIMEOUT:
                    if self._last_box:
                        vx, wz = visual_servo(self._last_box, image_w, image_h)
                        return self.state, vx * 0.5, wz * 0.5
                    else:
                        return(self.state, 0.0, 0.0)
                else:
                    self.state = FSMState.SEARCHING
            if self.state == FSMState.SEARCHING:
                if lost_duration > LOST_TIMEOUT * 3:
                    self.state = FSMState.STOPPED
                else:
                    return (self.state, 0.0, SEARCH_WZ)
            if self.state == FSMState.STOPPED:
                return (self.state, 0.0, 0.0)
        # ===== TODO 2B END =====

    def _select(self, boxes: list[dict]) -> dict | None:
        """多目标选择：与上一帧 bbox 中心欧氏距离最近（防止多目标跳框）。"""
        if not boxes:
            return None
        if len(boxes) == 1:
            return boxes[0]
        if self._last_box is None:
            return max(boxes, key=lambda b: b["area"])
        lx, ly = self._last_box["cx"], self._last_box["cy"]
        return min(boxes, key=lambda b: (b["cx"] - lx) ** 2 + (b["cy"] - ly) ** 2)
