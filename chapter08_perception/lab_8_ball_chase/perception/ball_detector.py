"""红球 HSV 阈值检测（教程 §8.3 方案 A · 学生 TODO 1）。"""

from __future__ import annotations

import cv2
import numpy as np

# 红色在 OpenCV HSV（H ∈ [0, 180]）中横跨 0°，需要两段区间取并集
_LOW1 = np.array([0, 120, 80], dtype=np.uint8)
_HIGH1 = np.array([10, 255, 255], dtype=np.uint8)
_LOW2 = np.array([170, 120, 80], dtype=np.uint8)
_HIGH2 = np.array([180, 255, 255], dtype=np.uint8)

_MIN_AREA = 50


def detect_red_ball(rgb: np.ndarray) -> dict | None:
    """检测图像中的红球，返回 bbox dict 或 None。

    Parameters
    ----------
    rgb : (H, W, 3) uint8 RGB 图像（来自 mujoco.Renderer.render()）

    Returns
    -------
    dict with keys {"cx", "cy", "w", "h", "area"} 或 None（未检测到）

    实现提示
    --------
    1. 将 RGB 图像转到 HSV 空间（可直接 cv2.COLOR_RGB2HSV，或先 RGB→BGR 再 BGR→HSV）
    2. 用 _LOW1/_HIGH1 与 _LOW2/_HIGH2 分别做 cv2.inRange，再按位或（|）合并成 mask
    3. cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE) 找外轮廓
    4. 若没有轮廓，返回 None；否则取 cv2.contourArea 最大的轮廓，面积 < _MIN_AREA 返回 None
    5. 用 cv2.boundingRect(best) 取 (x, y, w, h)，返回 cx=x+w/2, cy=y+h/2, w, h, area
    """
    # ===== TODO 1 START =====
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, _LOW1, _HIGH1) | cv2.inRange(hsv, _LOW2, _HIGH2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    best = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(best)
    if area < _MIN_AREA:
        return None
    x, y, w, h = cv2.boundingRect(best)
    return {'cx': x+w/2,
            'cy': y+h/2,
            'w': w,
            'h': h,
            'area': area
            }
    # ===== TODO 1 END =====
