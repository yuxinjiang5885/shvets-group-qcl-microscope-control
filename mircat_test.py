'''
mircat_test
Giovanni Sartorello (srtgnn@gmail.com)
MIRcat library test
'''

TARGET_QCL = 2
TARGET_WL = 6.2 # um

from instruments.mircat import laser

laser1 = laser()
# print(laser1.get_wavelength())
laser1.arm()
laser1.stabilize()
laser1.tune(TARGET_QCL, TARGET_WL)
laser1.disarm()
laser1.disconnect()