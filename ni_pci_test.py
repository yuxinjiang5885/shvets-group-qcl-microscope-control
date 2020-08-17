
'''
ni_pci_test
Giovanni Sartorello (srtgnn@gmail.com)
Test connection to NI PCIe-6361
Version 1
Python 3.6 on Windows 10 64-bit
Created 2020-Aug-17
'''

import sys
from instruments.ni_pci import pci_input

pci0 = pci_input()
inputVoltages = pci0.get_voltages(sampleNumber=10, sampleRate=1000)
