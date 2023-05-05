'''
ni_daq
Giovanni Sartorello (srtgnn@gmail.com)
Library of DAQmx tools for integrated setups
Version 4
Python 3.6 on Windows 10 64-bit
Created 2017-Sep-08
'''

from random import sample
import numpy as np
import weakref ### Added by Po-Ting on 3/17/23
from PyDAQmx.DAQmxConstants import (DAQmx_Val_Cfg_Default,
                                    DAQmx_Val_ContSamps,
                                    DAQmx_Val_CountUp,
                                    DAQmx_Val_FiniteSamps,
                                    DAQmx_Val_GroupByChannel,
                                    DAQmx_StartTrig_Retriggerable,
                                    DAQmx_Val_Rising,
                                    DAQmx_Val_Volts,
                                    DAQmx_Val_Log,
                                    DAQmx_Val_LogAndRead,
                                    DAQmx_Val_Off,    ### Added by Po-Ting on 3/17/23
                                    DAQmx_Val_Create,
                                    DAQmx_Val_Open,
                                    DAQmx_Val_CreateOrReplace,
                                    DAQmx_Val_Acquired_Into_Buffer) ### Added by Po-Ting on 3/17/23
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
                                    DAQmxWaitUntilTaskDone,
                                    DAQmxConfigureLogging,
                                    DAQmxRegisterEveryNSamplesEvent,
                                    DAQmxEveryNSamplesEventCallbackPtr)
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
        '''Create one task handle per Channel'''
        for name in self.physicalChannel:
            DAQmxCreateAIVoltageChan(self.taskHandle,
                                     name,
                                     '',
                                     DAQmx_Val_Cfg_Default,
                                     self.limit[name][0],
                                     self.limit[name][1],
                                     DAQmx_Val_Volts,
                                     None)
        if sampleNumber > 1:
            DAQmxCfgSampClkTiming(self.taskHandle,
                                '',
                                sampleRate,
                                DAQmx_Val_Rising,
                                DAQmx_Val_FiniteSamps,
                                sampleNumber)
        else: ### Workaround for when a single sample is requested
            DAQmxCfgSampClkTiming(self.taskHandle,
                                '',
                                sampleRate,
                                DAQmx_Val_Rising,
                                DAQmx_Val_ContSamps,
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

    '''
    New methods added by Po-Ting Shen
    03/17/2023
    '''


    def stream_to_disk(self,filePath = 'C:\Data\Test Data Stream\demo', groupName = 'test'):
        '''
        Logging the data to drive to prevent buffer overflow.
        '''
        DAQmxConfigureLogging(self.taskHandle, filePath, DAQmx_Val_LogAndRead, groupName, DAQmx_Val_CreateOrReplace)

    def register_callback_event_every_N_samples(self, totalSamples, samplePerChannel):
        '''
        Working progress.
        <totalSamples> = channel number * sampleNumber per channel (DEF_SAMPLES_SNAKESCAN * pixel number limit) < 2000 (buffer limit)
        '''
        # Class of the data object
        # one cannot create a weakref to a list directly
        # but the following works well
        class MyList(list):
            pass

        # list where the data are stored
        data = MyList()
        id_data = weakref.create_callbackdata_id(data)

        def callback_wrapper(callback_function_py):
            return DAQmxEveryNSamplesEventCallbackPtr(callback_function_py)

        def read_callback(taskHandle, everyNsamplesEventType, samplePerChannel, totalSamples, callbackData_ptr):
            '''
            Read N samples from the buffer.
            '''
            callbackdata = weakref.get_callbackdata_from_id(callbackData_ptr)
            read = int32()
            data = np.zeros((self.numberOfChannel, samplePerChannel), dtype=np.float64)
            DAQmxReadAnalogF64(taskHandle,
                               totalSamples,
                               DAQMX_TIMEOUT,
                               DAQmx_Val_GroupByChannel,
                               data,
                               totalSamples,
                               byref(read),None)
            callbackdata.extend(data.tolist())
            print('Acquired total ' + str(data.size) + ' samples.')
            return 0 # The function should return an integer

        # Convert the python function to a C function callback
        DAQmxCallback = callback_wrapper(read_callback(self.taskHandle,
                                                        everyNsamplesEventType = DAQmx_Val_Acquired_Into_Buffer,
                                                        samplePerChannel = samplePerChannel,
                                                        totalSamples = totalSamples,
                                                        callbackData_ptr = id_data))
        # Register the event with DAQmxCallback
        DAQmxRegisterEveryNSamplesEvent(self.taskHandle, DAQmx_Val_Acquired_Into_Buffer, totalSamples, 0, DAQmxCallback, id_data)

    def read_line(self, lineSampleNumber):
        data = np.zeros((self.numberOfChannel, lineSampleNumber), dtype=np.float64)
        read = int32()
        DAQmxReadAnalogF64(self.taskHandle,
                           lineSampleNumber,
                           DAQMX_TIMEOUT,
                           DAQmx_Val_GroupByChannel,
                           data,
                           lineSampleNumber*self.numberOfChannel,
                           byref(read),
                           None)
        print('Acquired ' + str(data.size) +' samples from the buffer.')
        #print(data[0])
        #print(data[1])
        return data





