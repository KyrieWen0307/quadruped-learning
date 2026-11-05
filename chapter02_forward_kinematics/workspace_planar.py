import numpy as np
import matplotlib.pyplot as plt
from fk_practice import fk_planar

length=[0.3,0.25,0.15]
points=[]

for _ in range(20000):
    theta=np.random.uniform(-np.pi,np.pi,size=3)
    p=fk_planar(length,theta)[:2,3]
    points.append(p)
points=np.array(points)
print(points.shape)

plt.scatter(points[:, 0], points[:, 1], s=1, alpha=0.3)
plt.axis("equal")
plt.xlabel("x (m)")
plt.ylabel("y (m)")
plt.title("Planar arm workspace")
plt.show()