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
                                    DAQmx_Val_CountUp,
                                    DAQmx_Val_FiniteSamps,
                                    DAQmx_Val_GroupByChannel,
                                    DAQmx_Val_Rising,
                                    DAQmx_Val_Volts)
from PyDAQmx.DAQmxFunctions import (byref,
                                    DAQmxCfgDigEdgeStartTrig,
                                    DAQmxCfgDigEdgeRefTrig,
                                    DAQmxCfgSampClkTiming,
                                    DAQmxClearTask,
                                    DAQmxCreateAIVoltageChan,
                                    DAQmxCreateCICountEdgesChan,
                                    DAQmxCreateTask,
                                    DAQmxReadAnalogF64,
                                    DAQmxResetDevice,
                                    DAQmxStartTask,
                                    DAQmxStopTask,
                                    DAQmxWaitUntilTaskDone)
#from PyDAQmx.Task import TaskHandle
from PyDAQmx.DAQmxTypes import int32, TaskHandle

DAQ_TIMEOUT = 10 # s

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

    def acquire(self, sampleNumber):
        '''Acquire data, one line per channel.'''
        DAQmxStartTask(self.taskHandle)
        data = np.zeros((self.numberOfChannel, sampleNumber), dtype=np.float64)
        read = int32()
        DAQmxReadAnalogF64(self.taskHandle,
                           sampleNumber,
                           10.0,
                           DAQmx_Val_GroupByChannel,
                           data,
                           sampleNumber*self.numberOfChannel,
                           byref(read),
                           None)
        # DAQmxWaitUntilTaskDone(self.taskHandle, DAQ_TIMEOUT)
        DAQmxStopTask(self.taskHandle)
        return data

    def clear_task(self):
        DAQmxClearTask(self.taskHandle)

    def configure(self, sampleNumber, sampleRate):
        '''Configure on-demand acquisition.'''
        DAQmxCreateTask("",byref(self.taskHandle))
        for name in self.physicalChannel:
            DAQmxCreateAIVoltageChan(self.taskHandle,
                                     name,
                                     '',
                                     DAQmx_Val_Cfg_Default,
                                     self.limit[name][0],
                                     self.limit[name][1],
                                     DAQmx_Val_Volts,
                                     None)
        DAQmxCfgSampClkTiming(self.taskHandle,
                              '',
                              sampleRate,
                              DAQmx_Val_Rising,
                              DAQmx_Val_FiniteSamps,
                              sampleNumber)

    def configure_triggered(self, triggerChannel, sampleNumber, sampleRate):
        '''Configure triggered acquisition.'''
        DAQmxCreateTask("",byref(self.taskHandle))
        # DAQmxCreateCICountEdgesChan(self.taskHandle,
        #                             triggerChannel,
        #                             '',
        #                             DAQmx_Val_Rising,   # Edge
        #                             0,                  # Counter start
        #                             DAQmx_Val_CountUp)  # Count direction
        for name in self.physicalChannel:
            DAQmxCreateAIVoltageChan(self.taskHandle,
                                     name,
                                     '',
                                     DAQmx_Val_Cfg_Default,
                                     self.limit[name][0],
                                     self.limit[name][1],
                                     DAQmx_Val_Volts,
                                     None)
        DAQmxCfgSampClkTiming(self.taskHandle,
                              '',
                              sampleRate,
                              DAQmx_Val_Rising,
                              DAQmx_Val_FiniteSamps,
                              sampleNumber)
        # DAQmxCfgDigEdgeRefTrig(self.taskHandle,
        #                        triggerChannel,
        #                        DAQmx_Val_Rising, 2)
        DAQmxCfgDigEdgeStartTrig(self.taskHandle,
                                 triggerChannel,
                                 DAQmx_Val_Rising);