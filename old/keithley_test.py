#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
keithley_test
Giovanni Sartorello (srtgnn@gmail.com)
Test keithley SMU functionality
Created 2019-Feb-27 for Python 3.7.2
'''

# import os
import sys
import time
# from datetime import datetime
from instruments.keithley import SMU
from instruments.visa_identify import visa_identify
# macPath = '/Users/giovanni/Library/Mobile Documents/com~apple~CloudDocs/Software/Python'
# winPath = 'C:\\Users\\Saturn\\iCloudDrive\\Software\\Python'
# if os.name == 'nt':
#     sys.path.append(winPath)
# else:
#     sys.path.append(macPath)

SOURCE_VOLTAGE = 1. # V

visaIdentify = visa_identify()

identified = visaIdentify.identify('TCP','KEITH') # TCP/IP device from KEITHley
instrAddress = identified[0] # There should not be more than one
k2450 = SMU(instrAddress)
if not k2450.ready:
    print('The instrument was not ready, please reboot it.')
    sys.exit()
k2450.reset()
# now0 = datetime.now()
# k2450.datetimeinstr(now0.year, now0.month, now0.day, now0.hour, now0.minute,
#     now0.second)
print('Date and time: {}'.format(k2450.datetimeinstr()))
print('Terminals: {}'.format(k2450.terminals('rear')))
print('Autorange on/off: {}'.format(k2450.measure_autorange()))
print('Measure function: {}'.format(k2450.measure_function('current')))
print('Sense mode: {}'.format(k2450.measure_sense_mode(2)))
k2450.make_buffer()
print('Current: {:.3E} A'.format(k2450.read_buffer()))
print('Source function: {}'.format(k2450.source_function('voltage')))
print('Source level: {:.3E} V'.format(k2450.source_level(SOURCE_VOLTAGE)))
k2450.source_output('on')
time.sleep(1.5)
k2450.source_output('off')
k2450.close()
