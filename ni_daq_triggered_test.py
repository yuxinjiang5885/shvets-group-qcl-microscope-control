'''
ni_daq_triggered_test
Giovanni Sartorello (srtgnn@gmail.com)
Tests triggered acquisition with multiple AI channel
Version 1
Pythion 3.8.3
'''
PCI_CH_X = b'Dev1/ai0'
PCI_CH_Y = b'Dev1/ai1'
PCI_TRIG = b'/Dev1/PFI12'

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
from PyDAQmx.DAQmxTypes import int32, TaskHandle

sampleRate = 1000
sampleNumber = 10
channels = [PCI_CH_X, PCI_CH_Y]
limits = dict([(name, (-10.0,10.0)) for name in channels])

taskHandle = TaskHandle()
DAQmxCreateTask("", byref(taskHandle))

for name in channels:
    DAQmxCreateAIVoltageChan(taskHandle,
                            name,
                            '',
                            DAQmx_Val_Cfg_Default,
                            limits[name][0],
                            limits[name][1],
                            DAQmx_Val_Volts,
                            None)
DAQmxCfgSampClkTiming(taskHandle,
                     '',
                     sampleRate,
                     DAQmx_Val_Rising,
                     DAQmx_Val_FiniteSamps,
                     sampleNumber)
DAQmxCfgDigEdgeStartTrig(taskHandle,
                         PCI_TRIG,
                         DAQmx_Val_Rising);
DAQmxStartTask(taskHandle)
data = np.zeros((len(channels), sampleNumber), dtype=np.float64)
read = int32()
DAQmxReadAnalogF64(taskHandle,
                   sampleNumber,
                   10.0,
                   DAQmx_Val_GroupByChannel,
                   data,
                   sampleNumber*len(channels),
                   byref(read),
                   None)
DAQmxClearTask(taskHandle)
print(data)