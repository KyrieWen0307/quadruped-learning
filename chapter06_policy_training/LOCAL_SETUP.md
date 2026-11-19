# 第六章本机准备记录

## 官方版本与本地目录

本机正文目录为 `D:\learn\quadruped-learning\chapter06_policy_training`。取材版本为 Datawhale 仓库的 `dca3f366935d42c1acabb057c503886833cc0cb5`。正文 demo 的三个入口文件、四份 YAML、README、tests 和 reports 均已取回。课程父目录的 `pyproject.toml` 和 `uv.lock` 也放在此处，供核对依赖。作者的两个 checkpoint、报告、视频和原始数据位于 `reports/`。本机运行产物位于 `outputs/`。

- [第六章正文](https://datawhalechina.github.io/dive-into-embodied-ai/docs/practices/quadruped/cs123/rl-gait)
- [本次采用的正文源码与作者报告](https://github.com/datawhalechina/dive-into-embodied-ai/tree/dca3f366935d42c1acabb057c503886833cc0cb5/codes/practices/quadruped/cs123/6.rl_pupper)
- [父目录依赖声明](https://github.com/datawhalechina/dive-into-embodied-ai/blob/dca3f366935d42c1acabb057c503886833cc0cb5/codes/practices/quadruped/cs123/pyproject.toml)
- [同版本正式 Lab6](https://github.com/datawhalechina/dive-into-embodied-ai/tree/dca3f366935d42c1acabb057c503886833cc0cb5/codes/practices/quadruped/cs123/exercises/lab_6_rl_pupper)

## 解释器与 Windows 入口

VS Code 中为第六章选择 `D:\learn\quadruped-learning\chapter06_policy_training\.venv\Scripts\python.exe`。这一章的环境基于原有 `mujoco` 的 Python 3.12，读取其中已安装的包。新依赖安装在第六章的 `.venv`。课程用 MuJoCo 的原生 CPU 仿真推进物理，短训练的 SB3 PPO 也选择 CPU 进行网络更新。

在 PowerShell 中运行下面两行，可检查加载的模型和零动作前滚。使用指定解释器即可，无需先激活环境。

```powershell
Set-Location 'D:\learn\quadruped-learning\chapter06_policy_training'
& .\.venv\Scripts\python.exe .\pupper_env.py
```

模型路径为 `D:\learn\quadruped-learning\chapter04_quadruped_mjcf\assets\mjcfs\pupper_v3.xml`。模型和相对目录 `meshes/stl` 中的 13 个网格内容均与该官方提交对应。正文运行入口统一经过 `pupper_env.py` 中的 `MODEL_PATH`。本地调整了该常量和直接运行时的路径打印、README 的路径提示，以及章节的 Git 忽略项。环境和控制算法保留官方实现。

| 项目 | 文件与运行约定 |
| --- | --- |
| 机身与执行器 | 基座为 `world_to_body` 自由关节，模型无等式约束。四腿依次为前右、前左、后右、后左，每腿依次是髋外展/内收、髋俯仰、膝。 |
| 位置伺服 | XML 使用带仿射偏置的 `general` 执行器实现位置伺服。裸 XML 的增益是 5 和 0.1。构造正文环境后，位置和速度增益是 5 和 0.25。单位分别为 N·m/rad 和 N·m·s/rad，各关节的力矩限幅为 ±3 N·m。 |
| 动作与时间 | `PupperEnv.step` 先把 12 个动作裁到 [−1,1]，乘以 0.5 rad 并加上各关节默认站姿，再按代码中的每关节上下限裁剪，写入 `data.ctrl`。每个目标保持 5 个 0.004 s 物理步，策略每 0.02 s 给一次动作。 |
| 基础与 gait | 本目录基础观测为 45 维，7 项奖励。gait 为 50 维并增加足端接触奖励。§6.9 的进阶版本需另读其目录与配置。 |
| 模型保存 | 本机 Reacher 的 `.pt` 保存 Actor 的 `state_dict`。本章 SB3 PPO 的 zip 可含策略、价值网络和优化器。同结构续训使用 `resume_from`，官方 `learn` 调用使用默认的步数重新计数。45→50 迁移使用 `transfer_from`，扩展输入权重并重新开始优化。 |
| 独立评估 | 正文 `evaluate.py` 的 `main` 构造 45 维环境。其演示在跌倒时会重置，改命令后下一次预测还会先用前一拍观测。看曲线和 GIF 时应一起核对回合边界和实际速度。 |

Windows 训练入口为 `train.py --config <配置路径>`，已含 `if __name__ == "__main__":`，支持 Windows 子进程。基础模型的评估入口为 `evaluate.py --checkpoint <基础模型路径> --out <独立输出目录>`。训练日志、配置和 checkpoint 保存在同一次运行对应的位置。作者报告生成脚本指向作者实验的目录与预算，重现实验时需要单独核对。

## 正式 Lab6

当前 `exercises/lab_6_rl_pupper/README.md` 要求每帧 36 维、15 帧堆叠共 540 维，含 18 项奖励。CPU 入口 `train_ppo.py` 通过 `starter.py` 使用 `envs/pupper_env.py`。`tests.py` 也导入这份实现。它使用 `exercises/shared/models/pupper_v3_floating.xml`。单独的 `starter_todo.py` 仍是 49 维、6 项奖励的旧模板。正式 Lab 留待正文后对照届时的学生起点，分步实现并验收。

## 首次验收，2026-11-18

- 专用解释器实测 Python 3.12.16、Gymnasium 1.2.2、MuJoCo 3.7.0、SB3 2.9.2、PyTorch 2.9.1+cpu、NumPy 2.5.4、PyYAML 6.0.3、pytest 9.2.0、TensorBoard 2.21.0。依赖检查通过。本机组合符合课程依赖范围，和作者锁文件的逐包版本有差异。
- 直接运行 `pupper_env.py` 打印了第四章 XML 的绝对路径，完成 100 个零动作控制步。基础与 gait 均通过独立的 12 步有限数值及目标裁剪检查。对照实验使用 seed 6 和相同零动作，分别给 `vx=0` 与 `vx=0.4`。连续 25 步的机身与关节状态完全一致，末步奖励约为 0.0460 与 0.0317。
- 官方正文测试 19 项全部通过，耗时 23.03 s。[测试输出](outputs/preflight/pytest.txt)
- 助教在本机从零运行基础 PPO 512 步。训练 seed 0，两个子进程，单环境每批 64 步，4 批，墙钟 8.55 s，含进程启动。总共两处定期保存和一个完成最后一次更新的最终模型。该轮用于检查训练、日志与保存。正式预算留到 §6.6 结合更有代表性的计时决定。[实际配置](outputs/smoke_512_seed0/config.yaml) · [设备、版本、用时与模型内容](outputs/smoke_512_seed0/run.json) · [日志](outputs/smoke_512_seed0/train.log)
- 新进程加载本次最终模型，确定性评估 seed 42。在 12 s、600 步的命令切换里，跌倒与超时次数均为 0。给定前进 0.5 m/s 的 3 s 内，平均机身前向速度为 −0.00018 m/s。该时段四足依环境的高度判据始终贴地。接受命令、持续站住及准确跟踪目标速度在此有不同的实测结果。[数值评估与各时段结果](outputs/smoke_512_seed0/eval.json) · [逐步记录](outputs/smoke_512_seed0/eval_trace.csv) · [官方评估动画](outputs/smoke_512_seed0/official_evaluation/demo.gif) · [速度曲线](outputs/smoke_512_seed0/official_evaluation/velocity_tracking.webp)
- 正式训练、本章教学验收和正式 Lab6 均待后续进行。

## 回到 §6.1

在 `pupper_env.py` 中，`PupperEnv.reset` 内可搜索 `self.cmd = self._sample_command()` 找到本回合的指令来源。在 `PupperEnv.step` 内可搜索 `self.data.ctrl[:] = motor_target` 找到 12 个关节目标的落点。入门时先追清这两个不同的数据，观测的完整拼接留到 §6.3。
