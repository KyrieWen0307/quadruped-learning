import numpy as np
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "chapter02_forward_kinematics"))
from fk_practice import fk_planar


def fk_xy(theta):
    T = fk_planar([0.3, 0.25, 0.15], theta)
    return T[:2, 3]

def ik_analytic_planar(xy,phi,L=(0.3,0.25,0.15),elbow_up=True):
    x,y=xy
    xp = x - L[2] * np.cos(phi)
    yp = y - L[2] * np.sin(phi)
    r2 = xp**2 + yp**2  
    cos_theta2=(r2-L[0]**2-L[1]**2)/(2*L[0]*L[1])
    if cos_theta2 > 1 or cos_theta2 < -1:
        print('不可达')
        return None
    if elbow_up:
        elbow=1
    else:
        elbow=-1
    theta2=elbow*(np.acos(cos_theta2))
    alpha= np.arctan2(yp,xp)
    beta = np.arctan2(L[1] * np.sin(theta2), L[0] + L[1] * np.cos(theta2))    
    theta1=alpha-beta
    theta3=phi-theta1-theta2
    return np.array([theta1,theta2,theta3])

def jac_planar(theta,L=(0.3,0.25,0.15)):
    t1,t2,t3=theta
    L1,L2,L3=L
    s1, c1 = np.sin(t1), np.cos(t1)
    s12, c12 = np.sin(t1 + t2), np.cos(t1 + t2)
    s123, c123 = np.sin(t1 + t2 + t3), np.cos(t1 + t2 + t3)
    return np.array([
        [-L1*s1 - L2*s12 - L3*s123, -L2*s12 - L3*s123, -L3*s123],
        [ L1*c1 + L2*c12 + L3*c123,  L2*c12 + L3*c123,  L3*c123],
    ])

def ik_dls(fk_fn, jac_fn, theta0, p_target,
           lam=0.05, step=0.3, tol=1e-4, max_iter=200):
    theta=theta0.copy()
    for k in range(max_iter):
        p = fk_fn(theta)
        e = p_target - p
        if np.linalg.norm(e)<tol:
            return theta,k,e
        J=jac_fn(theta)
        JJt=J@J.T
        dtheta=J.T@np.linalg.solve(JJt+(lam**2)*np.eye(JJt.shape[0]),e)
        theta+=step*dtheta
    e = p_target - fk_fn(theta)
    return theta,max_iter,e

if __name__ == '__main__':
    print(jac_planar(np.deg2rad([30,30,30])))
    theta=ik_analytic_planar((0.4,0.2),np.deg2rad(30))
    print(np.rad2deg(theta))
    authen=fk_planar([0.3,0.25,0.15],theta)[:3,3]
    print(authen)
    print(jac_planar(theta))
    theta_dls, steps, e = ik_dls(
        fk_xy, jac_planar,
        theta0=np.zeros(3),
        p_target=np.array([0.4, 0.2])
    )
    print(np.rad2deg(theta_dls),steps,e)
    print(fk_planar([0.3,0.25,0.15],theta_dls)[:2,3])