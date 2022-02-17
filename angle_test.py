'''Test angle calculation formula'''

import numpy as np

x1 = 0
y1 = 0
x2 = -10
y2 = -2
x0 = x2 - x1
y0 = y2 - y1
A = 10
B = 2

sine = (y0 - (B/A)*x0) / (A + B**2/A)
angle_rad = np.arcsin(sine)
angle_deg = angle_rad * 360 / (2 * np.pi)

print(sine)
print(angle_rad)
print(angle_deg)