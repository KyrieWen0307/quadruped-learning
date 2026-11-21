# Lab 8 反思与实测观察

## 1. 标准追球闭环（10 Hz 视觉 / 50 Hz RL / 500 Hz 物理）

- **丢球 → 超时搜索 → 找回**：在 20 秒随机变向追球实测（`tracking_error.png`）中，`t ≈ 6.3 s` 红球丢失后，状态机前 2 秒保持 `TRACKING` 减速惯性跟随；超过 `LOST_TIMEOUT = 2.0 s` 后在 `t ≈ 8.3 s` 精准切入 `SEARCHING` 原地慢转，并于 `t ≈ 9.2 s` 重新抓回红球切回 `TRACKING`。
- **纯 P 控制的稳态静差**：`e_yaw` 在稳定跟随段停留在约 `+0.18 ~ +0.20` 而非严格归零——与第 7 章消融一致，`test_policy.json` 前进时存在系统性左偏，纯 P 控制器缺少积分项 I，需要留出非零水平偏差来抵消底层左飘。
- **小孔成像与分辨率天花板**：`detection_vs_distance.png` 呈现出清晰的反比例关系 $h \propto 1/d$。靠近至 `~0.85 m` 时 `bbox` 高度越过 `H_REF = 30 px`（实测 `30–33 px`）触发停步；而远至 `~2.4 m` 时高度跌至 `9–10 px`，接近 `_MIN_AREA = 50` 噪点门限，320×240 分辨率成为远距检测上限。

## 2. §8.8 选做加餐（视觉工具 + Gemini VLM + 实时 3D 语音闭环）

- **底层策略低速死区与 ReAct 自救**：初期 `follow()` 在 `1.6 m` 处算出 `vx ≈ 0.19 m/s`，落入 `test_policy.json` 的低速死区（原地踏步几乎不前移），DeepSeek 观察到位置锁死后自主改用 `walk(vx=0.5)` 跨过死区抵达球前；在 `follow()` 中加入最小启动前向速度 `max(current_vx, 0.35)` 后，视野外找球任务 `V1` 首次调用 `follow('red', 8)` 即 `reached=True` 一步停在球前。
- **VLM 思考 Token 预算坑**：`gemini-2.5-flash` 默认消耗内部 thinking tokens，`max_tokens=256` 会导致正文中文回复刚输出几个字就被截断；调高至 `max_tokens=1024` 后，VLM 完整识别出场景布局、红球位于画面左侧乃至光照阴影方向，并与 `look_for` 测得的 `e_yaw = -0.497` 精准吻合。
- **三层分工边界**：高频视觉伺服必须下沉到本地 10 Hz HSV/FSM（< 1 ms），LLM/VLM 只做低频战略调度与按需语义看图，结合本地 `faster-whisper` 即可跑通“语音 → 语言规划 → 视觉/VLM 感知 → RL 步态 → 物理仿真”完整闭环。
