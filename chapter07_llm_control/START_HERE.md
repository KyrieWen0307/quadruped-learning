# Lab 7 本机学生起点

本目录取自 Datawhale 仓库提交 `e1a31f1f549224518f1297cd1eccafa879f3ee32` 的 `codes/practices/quadruped/cs123/exercises/lab_7_llm_control`。

## 学生编辑哪三个文件？

本机已整理为单一真源结构（所有测试与录屏入口都直接跑你自己写的函数）：

1. **TODO 1**：`lab_7_llm_control/tools/robot_tools.py` 中的 `dispatch()` — 工具参数校验、软失败返回与调用 `RobotState`；由 `tests.py` 的 7 条离线断言直接验证（**不需要 API Key**）。
2. **TODO 2**：`lab_7_llm_control/agent/llm_agent.py` 中的 `run_agent()` — OpenAI-compatible SDK 原生 `tool_calls` 多轮闭环。
3. **TODO 3**：`lab_7_llm_control/starter.py` 中的 `render_task_gif()` — 接 `frame_callback` 完成 12 fps 离屏采帧与字幕叠加；由 `eval_tasks.py` / `make_artifacts.py` 直接调用。

## 本机环境与资产复用

- **Python 解释器**：复用第 6 章虚拟环境 `D:\learn\quadruped-learning\chapter06_policy_training\.venv\Scripts\python.exe`（已补装 `openai`、`python-dotenv`）。
- **物理与策略资产**：自动复用 `D:\learn\quadruped-learning\chapter06_policy_training\lab6\shared\` 中的 `pupper_v3_floating.xml`、`test_policy.json`、`lab_5_mujoco.py` 与 `gif_utils.py`，不重复拷贝大文件。
- **Windows 中文字体适配**：`starter.py` 中的 `_caption_frame()` 优先加载 Windows 系统自带的微软雅黑/黑体，避免中文任务名在 GIF 里变成方框。
- **密钥安全**：复制 `lab_7_llm_control/.env.example` 为 `lab_7_llm_control/.env` 填入 DeepSeek API Key；`.env` 已被 `.gitignore` 忽略。

## 常用命令（Windows PowerShell）

```powershell
Set-Location D:\learn\quadruped-learning\chapter07_llm_control

# 1. 快速环境检查（离线，验证模型与 test_policy.json 可加载）
& ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\starter.py

# 2. 运行官方 7 条数值断言（离线，验收 TODO 1）
& ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\tests.py

# 3. 跑 L1–L5 全部任务并生成 GIF + 消息轨迹（需配置 .env，验收 TODO 1–3）
& ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\eval_tasks.py
```
