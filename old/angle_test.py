'''Test angle calculation formula for multiwell holder'''

import numpy as np

# x1 = 0
# y1 = 0
x1 = -35000
y1 = 5000

# x2 = 1
# y2 = 0
x2 = 35000
y2 = -5000

y1 = -y1
y2 = -y2

x0 = x2 - x1
y0 = y2 - y1

# A = 1
# B = 0
A = 7
B = 1

if A == 0 or B == 0:
    angle_rad = np.arctan2(y0, x0)
    angle_deg = angle_rad * 360 / (2 * np.pi)
else:
    # sine = (y0 - (B/A)*x0) / (A + B**2/A)
    # print(sine)
    angle_rad = np.arctan2(y0, x0) - np.arctan2(B, A)
    # angle_rad = np.arcsin(sine)
    angle_deg = angle_rad * 360 / (2 * np.pi)

print(angle_rad)
print(angle_deg)