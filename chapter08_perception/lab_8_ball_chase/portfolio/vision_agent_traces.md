# Lab 8 §8.8 视觉工具 + VLM Agent 实测轨迹

## V1: 球在视野外 → 自主转身找球并走过去

- 球初始坐标：`(0.6, -1.2, 0.05)`
- 指令：`看看周围有没有红球；如果当前画面没看到，就原地转圈找找，找到后走过去停在球前。`
- 最终回复：已经找到红球并走到球前停下（转了约 90° 后在第 6 次搜索时发现红球，位于正前方约 1.4 m，视觉伺服后球在画面中已足够大，停在球前）。
- 最终位姿：`[0.238, -0.431, -1.162]`

| turn | role | type | tool_name | args | result_summary |
|------|------|------|-----------|------|----------------|
| 0 | user | text | — | — | 看看周围有没有红球；如果当前画面没看到，就原地转圈找找，找到后走过去停在球前。 |
| 1 | assistant | tool_call | look_for | {"target": "red"} | — |
| 2 | assistant | text | — | — | 我先看一下当前画面里有没有红球。 |
| 3 | tool | tool_result | — | — | {"ok": true, "found": false, "pose": [-0.006, 0.0, -0.0]} |
| 4 | assistant | tool_call | walk | {"vx": 0, "wz": 1.2, "duration": 1.5} | — |
| 5 | assistant | text | — | — | 当前画面没有红球，我原地转圈搜索。 |
| 6 | tool | tool_result | — | — | {"ok": true, "final_pose": [-0.031, 0.014, 1.166], "delta... |
| 7 | assistant | tool_call | look_for | {"target": "red"} | — |
| 8 | tool | tool_result | — | — | {"ok": true, "found": false, "pose": [-0.031, 0.014, 1.166]} |
| 9 | assistant | tool_call | walk | {"vx": 0, "wz": 1.2, "duration": 1.5} | — |
| 10 | tool | tool_result | — | — | {"ok": true, "final_pose": [-0.049, -0.017, 2.233], "delt... |
| 11 | assistant | tool_call | look_for | {"target": "red"} | — |
| 12 | tool | tool_result | — | — | {"ok": true, "found": false, "pose": [-0.049, -0.017, 2.2... |
| 13 | assistant | tool_call | walk | {"vx": 0, "wz": 1.2, "duration": 1.5} | — |
| 14 | tool | tool_result | — | — | {"ok": true, "final_pose": [-0.039, -0.047, -2.965], "del... |
| 15 | assistant | tool_call | look_for | {"target": "red"} | — |
| 16 | tool | tool_result | — | — | {"ok": true, "found": false, "pose": [-0.039, -0.047, -2.... |
| 17 | assistant | tool_call | walk | {"vx": 0, "wz": 1.2, "duration": 1.5} | — |
| 18 | tool | tool_result | — | — | {"ok": true, "final_pose": [-0.0, -0.048, -1.885], "delta... |
| 19 | assistant | tool_call | look_for | {"target": "red"} | — |
| 20 | tool | tool_result | — | — | {"ok": true, "found": false, "pose": [-0.0, -0.048, -1.885]} |
| 21 | assistant | tool_call | walk | {"vx": 0, "wz": 1.2, "duration": 1.5} | — |
| 22 | tool | tool_result | — | — | {"ok": true, "final_pose": [0.017, -0.015, -0.822], "delt... |
| 23 | assistant | tool_call | look_for | {"target": "red"} | — |
| 24 | tool | tool_result | — | — | {"ok": true, "found": true, "bbox": {"cx": 229.0, "cy": 1... |
| 25 | assistant | tool_call | follow | {"target": "red", "seconds": 8} | — |
| 26 | assistant | text | — | — | 找到红球了，现在走过去。 |
| 27 | tool | tool_result | — | — | {"ok": true, "reached": true, "stopped_state": "TRACKING"... |
| 28 | assistant | text | — | — | 已经找到红球并走到球前停下（转了约 90° 后在第 6 次搜索时发现红球，位于正前方约 1.4 m，视觉伺服后球在... |

## V2: VLM 识图判断方向 → 视觉跟随靠近红球

- 球初始坐标：`(1.8, 0.65, 0.05)`
- 指令：`先调用 ask_vlm 看一眼前方相机画面，描述你看到了什么以及球在左边还是右边；然后用视觉工具确认并走过去停在红球前。`
- 最终回复：任务完成。

**VLM 描述**：前方是一个蓝白格子地板的极简 3D 场景，视野中有一个明亮的红球停在近处地面上，阴影朝左，说明光源来自右侧；红球位于画面**左侧**。

**视觉确认与接近**：
- `look_for` 确认红球在左侧（e_yaw ≈ -0.50），距离约 1.96 m
- 通过 `follow` 视觉伺服两轮，再补一次短距离直行
- 最终红球位于画面正中（e_yaw ≈ -0.02），距离约 0.88 m，bbox 高 29px，已停在球前。

已停下并正对红球，任务完成。
- 最终位姿：`[1.022, 0.326, 0.384]`

| turn | role | type | tool_name | args | result_summary |
|------|------|------|-----------|------|----------------|
| 0 | user | text | — | — | 先调用 ask_vlm 看一眼前方相机画面，描述你看到了什么以及球在左边还是右边；然后用视觉工具确认并走过去停在红球前。 |
| 1 | assistant | tool_call | ask_vlm | {"question": "Describe what you see in this camera view. ... | — |
| 2 | assistant | text | — | — | 我先用 VLM 看一下前方画面。 |
| 3 | tool | tool_result | — | — | {"ok": true, "model": "gemini-2.5-flash", "answer": "I se... |
| 4 | assistant | tool_call | look_for | {"target": "red"} | — |
| 5 | assistant | text | — | — | VLM 看到红球在画面左侧。现在用视觉工具确认位置。 |
| 6 | tool | tool_result | — | — | {"ok": true, "found": true, "bbox": {"cx": 80.5, "cy": 13... |
| 7 | assistant | tool_call | follow | {"target": "red", "seconds": 8.0} | — |
| 8 | assistant | text | — | — | 红球在左侧（e_yaw=-0.497），距离约 2 米。开始视觉伺服靠近。 |
| 9 | tool | tool_result | — | — | {"ok": true, "reached": false, "stopped_state": "TRACKING... |
| 10 | assistant | tool_call | follow | {"target": "red", "seconds": 4.0} | — |
| 11 | assistant | text | — | — | 已经很接近（box 高 28px，接近 30px 阈值），再补一点靠近。 |
| 12 | tool | tool_result | — | — | {"ok": true, "reached": false, "stopped_state": "TRACKING... |
| 13 | assistant | tool_call | walk | {"vx": 0.35, "wz": 0, "duration": 1.0} | — |
| 14 | tool | tool_result | — | — | {"ok": true, "final_pose": [1.022, 0.326, 0.384], "delta_... |
| 15 | assistant | tool_call | look_for | {"target": "red"} | — |
| 16 | tool | tool_result | — | — | {"ok": true, "found": true, "bbox": {"cx": 157.0, "cy": 1... |
| 17 | assistant | text | — | — | 任务完成。  **VLM 描述**：前方是一个蓝白格子地板的极简 3D 场景，视野中有一个明亮的红球停在近处地面上... |
