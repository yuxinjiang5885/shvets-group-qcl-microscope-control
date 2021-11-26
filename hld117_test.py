'''
hld117_test
Giovanni Sartorello (srtgnn@gmail.com)
Test Prior HLD117
Created 2021-Nov-26 for Python 3.9.6 64-bit
'''

from instruments.hld117 import stage
# import os
# import sys
# import time
# from datetime import datetime

stage1 = stage()
stage1.connect()
stage1.identify()
# stage1.center()
stage1.disconnect()
