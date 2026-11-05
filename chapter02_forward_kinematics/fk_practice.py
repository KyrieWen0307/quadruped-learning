import numpy as np
import math

def trans(length):
    T=np.eye(4)
    T[:3,3]=length,0,0
    return T

def rot_z(theta):
    R=np.eye(4)
    R[0:2,0]=math.cos(theta),math.sin(theta)
    R[0:2,1]=math.cos(theta+math.pi/2),math.sin(theta+math.pi/2)
    return R

def fk_planar(length,theta):
    T_total=np.eye(4)
    for i in range(3):
        T_i=rot_z(theta[i])@trans(length[i])
        T_total=T_total@T_i
    return T_total

if __name__ == "__main__":

    theta=[]
    for i in range(3):
        angle=float(input(f'theta{i+1}='))
        theta.append(angle)

    theta=np.deg2rad(theta)
    length=[0.3,0.25,0.15]
    print(fk_planar(length,theta)[:3,3])
