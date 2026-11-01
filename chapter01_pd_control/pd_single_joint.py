from pathlib import Path
import time
import mujoco
import mujoco.viewer
import numpy as np

model = mujoco.MjModel.from_xml_path(str(Path(__file__).with_name("pendulum.xml")))
data = mujoco.MjData(model)

q_des = 0.8
Kp,Kd = 20, 1

use_motor = True

if use_motor:
    pos_act_id = mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_ACTUATOR,"pos_act")
    model.actuator_gainprm[pos_act_id,:] = 0.0
    model.actuator_biasprm[pos_act_id,:] = 0.0

log = []
with mujoco.viewer.launch_passive(model,data) as viewer:
    while viewer.is_running() and data.time < 80:
        step_start = time.time()

        q=data.qpos[0]
        dq=data.qvel[0]

        if use_motor:
            tau = Kp * (q_des-q)+Kd*(0.0-dq)
            data.ctrl[1]=np.clip(tau,-5.0,5.0)
        else:
            data.ctrl[0]=q_des

        mujoco.mj_step(model,data)
        viewer.sync()
        log.append((data.time,q,dq,data.ctrl.copy()))

        dt_left = model.opt.timestep - (time.time()-step_start)
        if dt_left > 0:
            time.sleep(dt_left)