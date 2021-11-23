'''
hld117_test
Giovanni Sartorello (srtgnn@gmail.com)
Test Prior HLD117
Created 2021-Nov-23 for Python 3.9.6 64-bit
'''

# import os
import sys
import time
import pyvisa as visa
# from datetime import datetime

VISA_ID = 'ASRL3::INSTR' # Find this in NI Max. Visa # should equal COM #

rm = visa.ResourceManager()
resources = rm.list_resources()
print(resources)
stage = rm.open_resource(VISA_ID, baud_rate=9600)
stage.open()
try:
    id = stage.query('?')
    # # idStrip = self.id.rstrip()
    # idString = idStrip.split(',')
    # idString.append(self.address)
    print(id)
    # print('Open: {0} {1} @ {4}\nS/N: {2}\nFirmware version: {3}'
    #         .format(*idString))
except:
    print('Failure to communicate')
time.sleep(1)
stage.close()