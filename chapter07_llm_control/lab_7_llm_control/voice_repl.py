r"""第 7 章 §7.7.2 选做扩展：语音控制实时 3D Pupper（faster-whisper + DeepSeek + MuJoCo）。

按回车对着麦克风说话 → 本地 Whisper 转成中文 → 直接喂给你写的 run_agent() → 实时看 3D Pupper 执行！

学生只需补两处超短 TODO（各 4–6 行）：
  - TODO A: record_audio()      — 用 sounddevice 录 16 kHz 单声道 float32 音频
  - TODO B: transcribe_audio()  — 用 faster-whisper 把音频数组转成中文文本

用法（在 chapter07_llm_control 目录下）：
    # 查看本机麦克风设备列表
    & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\voice_repl.py --list-devices

    # 启动语音控制（默认 small 模型 + 每次录 4 秒，首次会自动从国内镜像下载模型）
    & ..\chapter06_policy_training\.venv\Scripts\python.exe -X utf8 .\lab_7_llm_control\voice_repl.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# 优先走国内 HuggingFace 镜像下载 faster-whisper 权重（必须在导入 faster_whisper 之前设置）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import mujoco
import mujoco.viewer
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

LAB_DIR = Path(__file__).resolve().parent
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))

from agent.llm_agent import format_trace_table, run_agent  # noqa: E402
from tools.robot_tools import CONTROL_RATIO, PHYS_DT, RobotState, dispatch  # noqa: E402

SAMPLE_RATE = 16000  # Whisper 原生采样率 16 kHz
CHINESE_HINT = "以下是对四足机器人Pupper下达的简体中文控制指令，例如：向前走一米、右转九十度、停下、转两圈。"


# ---------------------------------------------------------------------------
# TODO A: 录音（对应教程 §7.7.2）
# ---------------------------------------------------------------------------

def record_audio(seconds: float = 4.0, sr: int = SAMPLE_RATE, device: int | None = None) -> np.ndarray:
    """录制 seconds 秒单声道 float32 音频，返回一维 np.ndarray。

    提示（3 行搞定）：
    1. audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32", device=device)
    2. sd.wait()
    3. return audio.squeeze()
    """
    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32", device=device)
    sd.wait()
    return audio.squeeze()

# ---------------------------------------------------------------------------
# TODO B: 语音转文字（faster-whisper）
# ---------------------------------------------------------------------------

def transcribe_audio(whisper_model: WhisperModel, audio: np.ndarray) -> str:
    """用 faster-whisper 把一维 float32 音频转成中文文本。

    提示（3 行搞定）：
    1. segments, _ = whisper_model.transcribe(
           audio,
           language="zh",
           initial_prompt=CHINESE_HINT,
           vad_filter=True,   # 自动过滤静音段，减少幻觉乱码
       )
    2. 把所有分段拼接："".join(seg.text for seg in segments).strip()
    3. 返回拼接后的字符串
    """
    segments, _ = whisper_model.transcribe(audio, language="zh", initial_prompt=CHINESE_HINT, vad_filter=True)
    return "".join(seg.text for seg in segments).strip()

# ---------------------------------------------------------------------------
# 主循环（已写好：加载模型 + 3D Viewer + 急停 + 自动记录实验日志）
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lab 7 语音控制实时 3D Pupper")
    parser.add_argument("--model", default="small", help="Whisper 模型大小：tiny / base / small（中文推荐 small）")
    parser.add_argument("--seconds", type=float, default=4.0, help="每次按回车录音秒数（默认 4.0 秒）")
    parser.add_argument("--device", type=int, default=None, help="指定输入麦克风编号（先用 --list-devices 查看）")
    parser.add_argument("--no-viewer", action="store_true", help="不弹 3D 窗口，仅终端语音交互")
    parser.add_argument("--list-devices", action="store_true", help="列出本机音频输入输出设备后退出")
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    print(f"正在加载 faster-whisper ({args.model}, CPU int8) ... 首次运行会自动下载权重。")
    t0 = time.perf_counter()
    whisper_model = WhisperModel(args.model, device="cpu", compute_type="int8")
    print(f"模型加载完成，耗时 {time.perf_counter() - t0:.1f} s")

    robot = RobotState(policy_name="test")
    robot.reset()

    viewer = None
    if not args.no_viewer:
        viewer = mujoco.viewer.launch_passive(robot.model, robot.data)
        viewer.cam.distance = 1.6
        viewer.cam.elevation = -22.0
        viewer.cam.azimuth = 90.0
        viewer.cam.lookat[:] = robot.data.xpos[robot.base_id]
        viewer.sync()

    step_counter = 0
    last_sync_wall = time.perf_counter()
    sync_dt = CONTROL_RATIO * PHYS_DT

    def frame_callback(cb_robot: RobotState) -> None:
        nonlocal step_counter, last_sync_wall
        if viewer is None or not viewer.is_running():
            return
        step_counter += 1
        if step_counter % CONTROL_RATIO == 0:
            viewer.cam.lookat[:] = cb_robot.data.xpos[cb_robot.base_id]
            viewer.sync()
            now = time.perf_counter()
            remain = sync_dt - (now - last_sync_wall)
            if remain > 0:
                time.sleep(remain)
            last_sync_wall = time.perf_counter()

    print("=" * 60)
    print(f"Pupper 语音控制已就绪！（每次录 {args.seconds:.1f} 秒，直接驱动你写的 dispatch + run_agent）")
    print("操作说明：")
    print("  直接按回车  — 开始录音并执行语音指令")
    print("  输入 reset  — 把机器狗重置回原点")
    print("  输入 pose   — 查看当前 [x, y, yaw]")
    print("  输入 quit   — 退出（Ctrl+C 触发紧急 stop）")
    print("=" * 60)

    try:
        while True:
            if viewer is not None and not viewer.is_running():
                print("3D 窗口已关闭，退出语音控制。")
                break

            try:
                user_in = input("\n[按回车开始说话 | reset | pose | quit] > ").strip()
            except KeyboardInterrupt:
                print("\n[安全急停] 触发 stop() ...")
                print("stop ->", dispatch("stop", {}, robot, frame_callback=frame_callback))
                continue
            except EOFError:
                break

            if user_in.lower() in ("quit", "exit", "q"):
                break
            if user_in.lower() == "pose":
                print("pose ->", robot.get_pose())
                continue
            if user_in.lower() == "reset":
                robot.reset()
                if viewer is not None and viewer.is_running():
                    viewer.cam.lookat[:] = robot.data.xpos[robot.base_id]
                    viewer.sync()
                print("已重置回原点 ->", robot.get_pose())
                continue

            print(f"🎤 正在录音 {args.seconds:.1f} 秒，请说话...")
            audio = record_audio(seconds=args.seconds, sr=SAMPLE_RATE, device=args.device)

            t_asr = time.perf_counter()
            text = transcribe_audio(whisper_model, audio)
            asr_ms = (time.perf_counter() - t_asr) * 1000
            print(f"📝 Whisper 识别 ({asr_ms:.0f} ms): {text!r}")

            if not text:
                print("（未检测到有效语音，请再按回车重说）")
                continue

            last_sync_wall = time.perf_counter()
            try:
                final_text, messages = run_agent(text, robot, frame_callback=frame_callback)
            except KeyboardInterrupt:
                print("\n[安全急停] 中断当前指令，执行 stop() ...")
                print("stop ->", dispatch("stop", {}, robot, frame_callback=frame_callback))
                continue

            print("\nbot>", final_text)
            print("\n--- 本轮工具轨迹 ---")
            print(format_trace_table(messages))
            print(f"当前位姿: {robot.get_pose()}")
    finally:
        if viewer is not None:
            viewer.close()


if __name__ == "__main__":
    main()
