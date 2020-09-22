'''
mircat_sweep_test
Giovanni Sartorello (srtgnn@gmail.com)
MIRcat sweep function test
'''

WL_START = 5.2
WL_END = 9.7
WL_STEP = 0.1

from instruments.mircat import laser

laser1 = laser()
laser1.arm()
laser1.stabilize()
# laser1.enable()
laser1.sweep(WL_START, WL_END, WL_STEP)
# laser1.disable()
# laser1.disarm()
laser1.disconnect()