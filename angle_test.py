'''Test angle calculation formula for multiwell holder'''

import numpy as np

x1 = 0
y1 = 0
x2 = 0
y2 = 1
x0 = x2 - x1
y0 = y2 - y1
A = 0
B = 1

if A == 0:
    angle_rad = np.arctan2(y0, x0)
    angle_deg = angle_rad * 360 / (2 * np.pi)
elif B == 0:
    angle_rad = np.arctan2(y0, x0)
    angle_deg = angle_rad * 360 / (2 * np.pi)
else:
    sine = (y0 - (B/A)*x0) / (A + B**2/A)
    print(sine)
    angle_rad = np.arcsin(sine)
    angle_deg = angle_rad * 360 / (2 * np.pi)


print(angle_rad)
print(angle_deg)