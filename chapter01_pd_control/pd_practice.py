import numpy as np

def calculate_pd(q_des, q, dq, kp, kd,dq_des=0):
    tau_p=kp*(q_des-q)
    tau_d=kd*(dq_des-dq)
    tau=tau_p+tau_d
    tau_cmd=np.clip(tau,-5,5)
    return tau_cmd

if __name__ == "__main__":
    result = calculate_pd(0.0, 0.0, 0.0, 20.0, 1.5, 0.9424778)
    print(result)