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
                                    DAQmx_StartTrig_Retriggerable,
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
                                    DAQmxSetTrigAttribute,
                                    DAQmxStartTask,
                                    DAQmxStopTask,
                                    DAQmxWaitUntilTaskDone)
#from PyDAQmx.Task import TaskHandle
from PyDAQmx.DAQmxTypes import int32, TaskHandle

DAQMX_TIMEOUT = 20 # s

class MultiChannelAnalogInput():
    '''Read multiple analog input channels simultaneously with NI DAQmx.'''

    def __init__(self, physicalChannel, limit = None, reset = False):
        self.physicalChannel = physicalChannel
        self.numberOfChannel = physicalChannel.__len__()
        if limit is None:
            self.limit = dict([(name, (-10.0,10.0)) for name in self.physicalChannel])
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
                           DAQMX_TIMEOUT,
                           DAQmx_Val_GroupByChannel,
                           data,
                           sampleNumber*self.numberOfChannel,
                           byref(read),
                           None)
        # DAQmxWaitUntilTaskDone(self.taskHandle, DAQMX_TIMEOUT)
        DAQmxStopTask(self.taskHandle)
        return data

    def acquire_fast(self, sampleNumber):
        '''Acquire data, one line per channel, no task start/stop.
           For repeated and retriggered use between a start and a stop call.'''
        data = np.zeros((self.numberOfChannel, sampleNumber), dtype=np.float64)
        read = int32()
        DAQmxReadAnalogF64(self.taskHandle,
                           sampleNumber,
                           DAQMX_TIMEOUT,
                           DAQmx_Val_GroupByChannel,
                           data,
                           sampleNumber*self.numberOfChannel,
                           byref(read),
                           None)
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
        ### Make task retriggerable. Requires X-series (63XX) hardware.
        DAQmxSetTrigAttribute(self.taskHandle,
                              DAQmx_StartTrig_Retriggerable, True)

    def start_task(self):
        '''Start task.'''
        DAQmxStartTask(self.taskHandle)

    def stop_task(self):
        '''Stop task.'''
        DAQmxStopTask(self.taskHandle)