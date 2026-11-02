import math
from pathlib import Path
import numpy as np 
import matplotlib.pyplot as plt
from pd_practice import calculate_pd
import mujoco

def sine_target(amplitude, frequency, t):
    A=amplitude
    f=frequency
    q_des=A*math.sin(2*math.pi*f*t)
    dq_des=A*2*math.pi*f*math.cos(2*math.pi*f*t)
    return q_des,dq_des

model = mujoco.MjModel.from_xml_path(
    str(Path(__file__).with_name("pendulum.xml"))
)
data = mujoco.MjData(model)

pos_act_id = mujoco.mj_name2id(
    model, mujoco.mjtObj.mjOBJ_ACTUATOR, "pos_act"
)
model.actuator_gainprm[pos_act_id, :] = 0.0
model.actuator_biasprm[pos_act_id, :] = 0.0

print("初始状态：", data.time, data.qpos[0], data.qvel[0])

times = []
targets = []
actuals = []

while data.time < 4.0:
    t = data.time

    # ① 调用 sine_target，接收 q_des 和 dq_des
    q_des,dq_des=sine_target(0.3,2.0,t)
    q = data.qpos[0]
    dq = data.qvel[0]

    # ② 调用 calculate_pd，把返回值存入 tau
    tau=calculate_pd(q_des,q,dq,kp=20.0,kd=1.5,dq_des=dq_des)
    # ③ 把 tau 写入力矩执行器的控制指令
    data.ctrl[1]=tau
    times.append(t)
    targets.append(q_des)
    actuals.append(q)

    mujoco.mj_step(model, data)

times_array = np.array(times)
targets_array = np.array(targets)
actuals_array = np.array(actuals)

mask = times_array >= 1.0
steady_targets = targets_array[mask]
steady_actuals = actuals_array[mask]

target_amplitude = (
    steady_targets.max() - steady_targets.min()
) / 2

actual_amplitude=(
    steady_actuals.max()-steady_actuals.min()
) / 2

gain=actual_amplitude/target_amplitude
gain_db=20*math.log10(gain
                      )
plt.plot(times, targets, label="target")
plt.plot(times, actuals, label="actual")
plt.xlabel("time (s)")
plt.ylabel("angle (rad)")
plt.legend()
plt.grid(True)
plt.savefig(Path(__file__).with_name("sine_tracking_2hz.png"), dpi=200)
print("目标振幅：", target_amplitude)
print("实际振幅：", actual_amplitude)
print("幅值比：", gain)
print("分贝值：", gain_db)