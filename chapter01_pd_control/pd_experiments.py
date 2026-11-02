from pathlib import Path

import matplotlib.pyplot as plt
import mujoco
import numpy as np

q_des=0.8

def make_model():
    model = mujoco.MjModel.from_xml_path(str(Path(__file__).with_name("pendulum.xml")))
    pos_act_id = mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_ACTUATOR,"pos_act")
    model.actuator_gainprm[pos_act_id,:]=0.0
    model.actuator_biasprm[pos_act_id,:]=0.0
    return model

def run_pd(Kp,Kd,disturbance=False):
    model = make_model()
    data = mujoco.MjData(model)
    ts,qs=[],[]

    while data.time<8:
        q=data.qpos[0]
        dq=data.qvel[0]
        tau=Kp*(q_des-q)+Kd*(0-dq)
        data.ctrl[1]=np.clip(tau,-5.0,5.0)
        data.qfrc_applied[0]=2.0 if disturbance and data.time>3.0 else 0.0

        mujoco.mj_step(model,data)
        ts.append(data.time)
        qs.append(data.qpos[0])

    return np.array(ts),np.array(qs)

plt.figure(figsize=(8, 4))
# 实验 1:固定 Kp,只改变 Kd,看欠阻尼 / 临界附近 / 过阻尼三种响应。
for Kd, label in [(0.5, "A: Kd=0.5"), (12.0, "B: Kd=12"), (40.0, "C: Kd=40")]:
    t, q = run_pd(Kp=40.0, Kd=Kd)
    plt.plot(t, q, label=label)
plt.axhline(q_des, linestyle="--", color="black", label="target")
plt.xlabel("time (s)")
plt.ylabel("q (rad)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig(Path(__file__).with_name("pd_kd_sweep.png"), dpi=200)

plt.figure(figsize=(8, 4))
# 实验 2:加入恒定外扰,对比纯 P 和 PD 的稳态误差。
for Kd, label in [(0.0, "P only"), (1.0, "PD")]:
    t, q = run_pd(Kp=20.0, Kd=Kd, disturbance=True)
    plt.plot(t, q, label=label)
plt.axhline(q_des, linestyle="--", color="black", label="target")
plt.axvline(3.0, linestyle=":", color="gray", label="disturbance")
plt.xlabel("time (s)")
plt.ylabel("q (rad)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig(Path(__file__).with_name("pd_disturbance_error.png"), dpi=200)