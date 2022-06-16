'''
ni_pci_test
Giovanni Sartorello (srtgnn@gmail.com)
Test connection to NI PCIe-6361
Version 1
Python 3.6 on Windows 10 64-bit
Created 2020-Aug-17
'''

import sys
# import os
# import platform
import numpy as np
from instruments.ni_daq_multiple_ai import MultiChannelAnalogInput as MChAI

pci_ch_x = b'Dev1/ai0'
pci_ch_y = b'Dev1/ai1'

class pci_input():
    '''Get voltage from NI PCI analog inputs.'''

    def __init__(self): # Prepare NI-DAQ task
        self.multipleAI = MChAI([pci_ch_x, pci_ch_y])

    def collect(self, sampleNumber, sampleRate): # Get samples fromDAQ device
        self.multipleAI.configure(sampleNumber, sampleRate)
        voltages = self.multipleAI.readAllChannels(sampleNumber)
        self.multipleAI.clearTask()
        return voltages

    def get_voltages(self, sampleNumber, sampleRate): # Collect and average
        daqVoltages = self.collect(sampleNumber, sampleRate)
        PCI_X = np.sum(daqVoltages[0])/sampleNumber
        PCI_Y = np.sum(daqVoltages[1])/sampleNumber
        return [PCI_X, PCI_Y]

pci0 = pci_input()
inputVoltages = pci0.get_voltages(sampleNumber=10, sampleRate=1000)
