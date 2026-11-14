# 第五章本地使用说明

准备日期：2026-11-14。教学按当前官方正文 §5.1—§5.9 顺序推进；准备文件不代表已经学完或运行完本章。

## 文件与资源

```text
D:\learn\quadruped-learning\
├── chapter04_quadruped_mjcf\assets\mjcfs\
│   ├── pupper_v3.xml
│   └── meshes\stl\                  # 复用已有网格
└── chapter05_gait_control\
    ├── run_gait_control.py            # 五种步态配置、时钟、轨迹、viewer、GIF
    ├── pupper_ik.py                   # 真实模型数值 IK/FK、运行时 weld 与位置伺服
    ├── README.md                      # 原样保留的官方 README
    ├── LOCAL_SETUP.md                 # 本地路径、版本差异与验证范围
    ├── .gitignore
    └── outputs\                      # 以后渲染时自动创建；本次未批量生成 GIF
```

解释器：`D:\Miniconda3\envs\mujoco\python.exe`。

本次已确认可导入 Python 3.12.16、MuJoCo 3.7.0、NumPy 2.5.4、Pillow 13.0.0，且 MuJoCo 提供 `MjSpec`。无需另建环境或安装依赖。

## 相对官方源码的修改

1. `pupper_ik.py` 的 `MODEL_PATH` 在项目根路径后增加 `chapter04_quadruped_mjcf`，以脚本位置解析模型的绝对路径，不依赖终端当前目录。
2. `run_gait_control.py` 导入 `MODEL_PATH`，并在 `main()` 解析参数后打印最终模型绝对路径。

模型仍从第四章原位置加载。XML 的 `meshdir="meshes/stl/"` 相对 XML 所在目录解释，13 个 mesh 文件引用均存在。没有复制 XML/STL，也没有修改第四章文件。步态配置、IK、PD、渲染逻辑保持官方实现。

## README 与当前正文的差异

官方 README 的目录树列出旧 `pupper_gait_demo.xml`，但本次官方目录只有两个 Python 脚本、README 和 `.gitignore`，实际脚本不加载旧 XML。README 最后一段称正文仍使用旧模型和 `shared`，这与当前已经改用真实 Pupper 的网页正文不一致。

本次以**当前官方正文与下载的实际 Python 源码**为教学依据；README 原文保留供对照，不下载不被使用的旧模型。

源码的 `HIP_OFFSETS` 为四个显式常量；关节、执行器、足端 site 的编号和关节限位从加载模型读取。不要把正文“全部来自 XML”的概括理解为髋偏置也由脚本动态读取。

## 控制含义与演示边界

- `data.ctrl` 是十二个目标关节角，单位为弧度。`build_sim_model()` 的默认增益为 `kp=20.0`、`kd=0.6`，保留原模型的执行器力矩限幅；不是第四章变体实验的 Python 力矩输入。
- 控制数组按模型执行器顺序是 FR、FL、RR、RL，每腿 HAA/HFE/KFE。遍历腿的 `LEG_ORDER=(FL, FR, RL, RR)` 不同；脚本用按名称查询得到的 `kin.ctrl` 映射写入，不能直接拼接四腿数组。
- `prepare_experiment()` 使用 `weld=True`；`inplace` 固定约束位置，`forward` 按预设速度修改 `model.eq_data[0, 3]`。机身前移由移动约束给定，不能作为自由基座自主行走或平衡能力的证据。
- `PupperLegIK` 使用独立的内部 `MjData` 做几何试算；它与物理仿真的实际关节和足端状态不同。
- 本章按官方完整 demo 学习，没有独立学生起点 Lab5；`lab5_` 只是渲染文件名前缀。不增加必做的自拟编程任务。

## 本次验证范围

已从最终第五章目录导入两个脚本，正确加载第四章 XML 与全部网格，并调用原地 trot 的 `prepare_experiment()` 完成初始化。运行模型为 `nq=19, nv=18, nu=12, nmesh=13, neq=1`，仿真步长为 `0.002 s`；weld 已激活，位置伺服增益为 `20.0/0.6`，执行器力矩限幅为 `[-3, 3]`。四腿目标关节到控制通道的映射、髋偏置与模型的一致性通过检查。

初始四腿 IK 的 FK 残差各约 `0.0506 mm`，只表明这组初始化目标可由当前几何模型求解。未推进物理仿真、未打开 viewer、未渲染 GIF，尚未检查动态足端跟踪或实际步态运动。第四章 XML 的内容哈希前后一致。

## Windows 使用方式（到相应运行小节再操作）

可先在 VS Code 选择上述 Conda 解释器。PowerShell 中查看参数的完整写法为：

```powershell
& "D:\Miniconda3\envs\mujoco\python.exe" "D:\learn\quadruped-learning\chapter05_gait_control\run_gait_control.py" --help
```

到 §5.6 检查原地 trot 时：

```powershell
& "D:\Miniconda3\envs\mujoco\python.exe" "D:\learn\quadruped-learning\chapter05_gait_control\run_gait_control.py" --gait trot --viewer inplace
```

注意：脚本不带 `--viewer` 会生成两段 GIF；本次准备不执行此默认行为。到 §5.7 再讨论前进与 GIF。Windows 使用 `python.exe`，无需 README 中的 `uv` 或 macOS 的 `mjpython`。

## 官方来源

- [第五章正文](https://datawhalechina.github.io/dive-into-embodied-ai/docs/practices/quadruped/cs123/gait-control)
- [官方配套目录](https://github.com/datawhalechina/dive-into-embodied-ai/tree/master/codes/practices/quadruped/cs123/5.gait-control)

下载的是 2026-11-14 取得的 master 分支文件。GitHub API 当时限流，未取得提交号；以下为下载原始文件的 SHA-256，用于标识本次取得的版本：

```text
run_gait_control.py  9c4779de291b8a28931a18801563f36b7f3791302353a5c9b8600b6affa81238
pupper_ik.py         f6980d22e5d35c204996e2bf909452a591bf5c6e64edb999411a22021c6b9bf0
README.md            3792be69902470dcdb6b2af80f347985a4fd1d11a6a30116f1144560660c5d43
.gitignore           ed18d74c2de13ea76d1bc296fdcd0ad84d34e853b7f7f48c3f85afe7fbf66cb8
```

## 2026-11-14 后续学习与运行记录

上文“本次验证范围”仅描述助手自动准备阶段的加载/初始化检查。之后，用户按指导运行了交互 viewer，并在对话中反馈：

- 原地 trot：模型连接、对角同步、离地间隙和运动连续性均无明显问题。
- 前进 trot：前后扫动清楚，对角配对正常。
- 前进 pace：同侧前后腿同步，左右两组交替。
- 前进 walk：通常一次一条腿摆动，四腿轮换可辨认。
- 前进 bound：前腿对、后腿对分别同步，前后两组交替。
- 前进 gallop：能观察到腿组内先后错开，与 bound 区别清楚。

已按官方正文完成 §5.1—§5.9 的讲解与口头理解检查，包括全局时钟/CPG与身体反馈是不同维度，以及节奏协调不保证身体平衡。本章按官方 demo 范围结课，没有额外必做 Lab5。

这些运动观察来自用户反馈，未冒充为助手另行测得的动态跟踪指标。本次未核验 GIF 导出结果，也未实现 CPG、接触/姿态步态反馈或验证解除 weld 后的自主推进和平衡。

后续安排为：Gemini 带学强化学习理论与官方 DDPG Reacher-v5；GPT 继续四足第六章 PPO 主体。该安排尚未登记为已完成。
