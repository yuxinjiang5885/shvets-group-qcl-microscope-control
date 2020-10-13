'''
ni_daq
Giovanni Sartorello (srtgnn@gmail.com)
Library of DAQmx tools for integrated setups
Version 4
Python 3.6 on Windows 10 64-bit
Created 2017-Sep-08
'''

import numpy as np
from PyDAQmx.DAQmxConstants import (DAQmx_Val_Cfg_Default,
                                    DAQmx_Val_FiniteSamps,
                                    DAQmx_Val_GroupByChannel,
                                    DAQmx_Val_Rising,
                                    DAQmx_Val_Volts)
from PyDAQmx.DAQmxFunctions import (byref,
                                    DAQmxCfgSampClkTiming,
                                    DAQmxClearTask,
                                    DAQmxCreateAIVoltageChan,
                                    DAQmxCreateTask,
                                    DAQmxReadAnalogF64,
                                    DAQmxResetDevice,
                                    DAQmxStartTask,
                                    DAQmxStopTask)
#from PyDAQmx.Task import TaskHandle
from PyDAQmx.DAQmxTypes import int32, TaskHandle

class MultiChannelAnalogInput():
    '''Read multiple analog input channels simultaneously with NI DAQmx.'''

    def __init__(self, physicalChannel, limit = None, reset = False):
        self.physicalChannel = physicalChannel
        self.numberOfChannel = physicalChannel.__len__()
        if limit is None:
            self.limit = dict([(name, (-10.0,10.0))
            for name in self.physicalChannel])
        elif type(limit) == tuple:
            self.limit = dict([(name, limit) for name in self.physicalChannel])
        else:
            self.limit = dict([(name, limit[i])
            for  i,name in enumerate(self.physicalChannel)])
        if reset:
            DAQmxResetDevice(physicalChannel[0].split('/')[0] )
        self.taskHandle = TaskHandle()

    def configure(self, sampleNumber, sampleRate):
        DAQmxCreateTask("",byref(self.taskHandle))
        for name in self.physicalChannel:
             DAQmxCreateAIVoltageChan(self.taskHandle,name,"",
                                      DAQmx_Val_Cfg_Default,
                                     self.limit[name][0],self.limit[name][1],
                                     DAQmx_Val_Volts,None)
        DAQmxCfgSampClkTiming(self.taskHandle,"",sampleRate,DAQmx_Val_Rising,
                              DAQmx_Val_FiniteSamps,sampleNumber)

    def readAllChannels(self, sampleNumber):
        DAQmxStartTask(self.taskHandle)
        '''One line per channel'''
        data = np.zeros((self.numberOfChannel,sampleNumber), dtype=np.float64)
        read = int32()
        DAQmxReadAnalogF64(self.taskHandle,sampleNumber,10.0,
                           DAQmx_Val_GroupByChannel,data,
                           sampleNumber*self.numberOfChannel,
                           byref(read),None)
        DAQmxStopTask(self.taskHandle)
        return data

    def clearTask(self):
        DAQmxClearTask(self.taskHandle)