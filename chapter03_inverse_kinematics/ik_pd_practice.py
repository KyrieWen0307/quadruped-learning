from pathlib import Path
import mujoco
import numpy as np
from ik_planar_practice import ik_dls
import matplotlib.pyplot as plt
import mujoco.viewer
import time

xml_path = Path(__file__).resolve().parent / "planar_3dof.xml"
model = mujoco.MjModel.from_xml_path(str(xml_path))
data = mujoco.MjData(model)
ik_data = mujoco.MjData(model)
end_id = mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_SITE,"end_site")

def fk_mj(theta):
    ik_data.qpos[:3]=theta
    mujoco.mj_forward(model,ik_data)
    return ik_data.site_xpos[end_id,:2].copy()

def jac_mj(theta):
    ik_data.qpos[:3]=theta
    mujoco.mj_forward(model,ik_data)
    jacp = np.zeros((3,model.nv))
    mujoco.mj_jacSite(model,ik_data,jacp,None,end_id)
    return jacp[:2,:3].copy()

def circle_target(t):
    center=np.array([0.45,0.0])
    radius=0.08
    period=8.0

    angle=2*np.pi*t/period
    offset=[radius*np.cos(angle),radius*np.sin(angle)]
    return center+offset

def triangle_target(t):
    vertices = np.array([
        [0.45,  0.10],
        [0.30, -0.10],
        [0.55, -0.05],
    ])
    period = 3.0

    seg = (t % period) / (period / 3)
    i = int(seg) % 3
    s = seg - int(seg)

    p0 = vertices[i]
    p1 = vertices[(i + 1) % 3]

    return (1-s)*p0+s*p1

if __name__ == "__main__":
    q_before = data.qpos.copy()
    theta_test = np.deg2rad([30, 30, 30])

    print("试算末端：", fk_mj(theta_test))
    print("试算雅可比：\n", jac_mj(theta_test))
    print("物理关节角保持不变：",
          np.array_equal(data.qpos, q_before))
    print("电机数量：", model.nu)
    p_target = np.array([0.4, 0.1])
    theta_target, steps, e = ik_dls(
    fk_mj, jac_mj,
    theta0=np.zeros(3),
    p_target=p_target
    )
    print("目标关节角（度）：", np.rad2deg(theta_target))
    print("IK 迭代次数：", steps)
    print("末端误差范数：", np.linalg.norm(e))
    for step_test in [0.1,0.3,1.0]:
        q_test, n_test, e_test = ik_dls(
            fk_mj, jac_mj,
            theta0=np.zeros(3),
            p_target=np.array([0.4, 0.1]),
            lam=0.05,
            step=step_test,
            tol=1e-4,
            max_iter=200
        )

        print("step：", step_test)
        print("更新次数：", n_test)
        print("IK残差（m）：", np.linalg.norm(e_test))
        print("关节角（度）：", np.rad2deg(q_test))
    Kp=np.array([60.0,60.0,40.0])
    Kd=np.array([4.0,4.0,2.0])
    model.opt.timestep = 0.0001
    theta_target, _, _ = ik_dls(
        fk_mj, jac_mj,
        theta0=theta_target,
        p_target=triangle_target(0.0)
    )

    data.qpos[:3] = theta_target
    data.qvel[:3] = 0.0
    mujoco.mj_forward(model, data)

    traj_log = []
    step_count = 0
    max_ik_error = 0.0
    with mujoco.viewer.launch_passive(model, data) as viewer:
        with viewer.lock():
            viewer.cam.lookat[:] = [0.35, 0.0, 0.0]
            viewer.cam.distance = 0.9
            viewer.cam.azimuth = 90
            viewer.cam.elevation = -90

        wall_start = time.perf_counter()
        sim_start = data.time

        while viewer.is_running() and data.time < 15.0:
            t = data.time
            p_target = triangle_target(t)

            theta_target, steps, e = ik_dls(
                fk_mj, jac_mj,
                theta0=theta_target,
                p_target=p_target
            )
            max_ik_error = max(max_ik_error, np.linalg.norm(e))
            if step_count % 100 == 0:
                traj_log.append((
                    t,
                    p_target.copy(),
                    data.site_xpos[end_id, :2].copy()
                ))
            step_count += 1
            q=data.qpos[:3]
            dq=data.qvel[:3]
            tau=Kp*(theta_target-q)+Kd*(0-dq)
            data.ctrl[:3]=tau
            mujoco.mj_step(model,data)
            mujoco.mj_forward(model, data)
            if step_count % 100 == 0:
                delay = (
                    wall_start + (data.time - sim_start)
                    - time.perf_counter()
                )
                if delay > 0:
                    time.sleep(delay)

                target_now = triangle_target(data.time)
                actual_now = data.site_xpos[end_id, :2].copy()

                markers = [
                    ([target_now[0], target_now[1], 0.04],
                     [0, 1, 0, 1]),
                    ([actual_now[0], actual_now[1], 0.04],
                     [1, 0, 0, 1]),
                ]

                with viewer.lock():
                    viewer.user_scn.ngeom = 0

                    for i, (pos, color) in enumerate(markers):
                        mujoco.mjv_initGeom(
                            viewer.user_scn.geoms[i],
                            type=mujoco.mjtGeom.mjGEOM_SPHERE,
                            size=[0.012, 0, 0],
                            pos=pos,
                            mat=np.eye(3).ravel(),
                            rgba=color,
                        )

                    viewer.user_scn.ngeom = len(markers)

                viewer.sync()
    p_actual = data.site_xpos[end_id, :2].copy()

    targets = np.array([row[1] for row in traj_log])
    actuals = np.array([row[2] for row in traj_log])

    errors = np.linalg.norm(targets - actuals, axis=1)
    print("平均跟踪误差（m）：", errors.mean())
    print("最大跟踪误差（m）：", errors.max())
    print("运动期间最大IK残差（m）：", max_ik_error)

    plt.plot(targets[:, 0], targets[:, 1], "--", label="target")
    plt.plot(actuals[:, 0], actuals[:, 1], label="actual")
    plt.axis("equal")
    plt.xlabel("x (m)")
    plt.ylabel("y (m)")
    plt.legend()
    plt.grid(True)
    plt.show()