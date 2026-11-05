from pathlib import Path
import mujoco
import numpy as np
from fk_practice import fk_planar
import matplotlib.pyplot as plt
import time
import mujoco.viewer

model_path=Path(__file__).with_name("planar_3dof.xml")
model = mujoco.MjModel.from_xml_path(str(model_path))
data = mujoco.MjData(model)
length=[0.3,0.25,0.15]
theta=np.deg2rad([0,90,-90])
data.qpos[:3]=theta

with mujoco.viewer.launch_passive(model,data)as v:
    while v.is_running():
        mujoco.mj_forward(model,data)
        p = fk_planar(length,data.qpos[:3])[:3,3]
        v.user_scn.ngeom=0
        mujoco.mjv_initGeom(
        v.user_scn.geoms[0],
        type=mujoco.mjtGeom.mjGEOM_SPHERE,
        size=[0.02,0,0],pos=p,mat=np.eye(3).flatten(),
        rgba=[1,0.3,0.3,1],
        )
        v.user_scn.ngeom=1

        v.sync()
        time.sleep(0.02)