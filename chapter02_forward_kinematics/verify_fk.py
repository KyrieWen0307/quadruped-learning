from pathlib import Path
import mujoco
import numpy as np
from fk_practice import fk_planar
import matplotlib.pyplot as plt

model_path=Path(__file__).with_name("planar_3dof.xml")
model = mujoco.MjModel.from_xml_path(str(model_path))
data = mujoco.MjData(model)

end_id = mujoco.mj_name2id(
    model,mujoco.mjtObj.mjOBJ_SITE,"end_site"
)

print("关节位置变量数量：",model.nq)
print("末端site编号：",end_id)

length=[0.3,0.25,0.15]
all_err=[]

for _ in range(100):
    theta=np.random.uniform(-np.pi,np.pi,size=3)
    p_ours=fk_planar(length,theta)[:3,3]
    data.qpos[:3]=theta
    mujoco.mj_forward(model,data)
    p_mj=data.site_xpos[end_id].copy()
    err=np.linalg.norm(p_ours-p_mj)
    all_err.append(err)
max_err=max(all_err)
print(f'100组姿态的最大位置误差：{max_err:.3e}m')
