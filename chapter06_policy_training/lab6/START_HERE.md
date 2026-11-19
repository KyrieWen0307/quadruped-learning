# Lab6 本机学生起点

本目录取自 Datawhale 仓库提交 `dca3f366935d42c1acabb057c503886833cc0cb5`。官方 README、测试入口和训练参数可在 `lab_6_rl_pupper/` 查阅。[对应官方提交](https://github.com/datawhalechina/dive-into-embodied-ai/tree/dca3f366935d42c1acabb057c503886833cc0cb5/codes/practices/quadruped/cs123/exercises/lab_6_rl_pupper)

## 实际编辑和运行的是哪份文件？

编辑 `lab_6_rl_pupper/envs/pupper_env.py`。训练入口 `train_ppo.py` 经 `starter.py` 使用该模块，`tests.py` 也用它。其观测由 36 维的当前帧和 14 帧历史拼成 540 维，动作 12 维，奖励分项 18 个。旧 `starter_todo.py` 保留作版本对照，其 49 维、6 项配方与当前测试要求有差异。

当前学生文件只空出了 `_get_obs()`、`_compute_reward()` 和 `_sample_command()` 三个方法。建议按官方分步任务先做观测，再做奖励与命令。README 写的 1% 回零分支在同版本参考实现中抽样范围为每轴 ±0.1。后续实现时会单独说明。

## 本机核验与适配

- 沿用第六章 `.venv` 的 Python 3.12、MuJoCo 3.7.0 和 CPU 版 SB3。课程 exercises 的通用依赖清单随目录保留。Windows 启动用该解释器直接执行 Python 入口。
- 模型加载路径为 `D:\learn\quadruped-learning\chapter06_policy_training\lab6\shared\models\pupper_v3_floating.xml`。只调整其 `meshdir` 以引用第四章已核对指纹的 13 个 STL。实际加载检查得到一个自由关节、零个等式约束、12 个执行器。
- 命令重采样保留回合累计步数，实测第 500 步可换命令，第 1000 步触发超时。评估发送指令时同步更新实际环境和最新观测的指令槽，保留较旧历史帧。速度图读机身前向分量。训练保存会保留中间检查点，指定续训路径不存在时会报错。
- 四项官方测试已用官方参考实现在本机过了一遍。学生文件的三个 TODO 仍待完成。它们完成后，再运行学生版的四项官方测试和独立的训练、变速、跌倒与可视化验收。
- 作品集中的并排 GIF 需要单独取得 Stanford 的上游对照权重。现有 `shared/rl/fetch_policies.sh` 提供该权重来源。准备对照评估时再获取。

从第六章目录运行学生版官方测试的命令如下。

```powershell
& .\.venv\Scripts\python.exe -X utf8 .\lab6\lab_6_rl_pupper\tests.py
```
