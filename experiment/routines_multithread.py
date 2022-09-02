'''
routines_multithread
Giovanni Sartorello (srtgnn@gmail.com)
Experiment routines for MIRcat spectral scan UI
Python 3.10.5 on Windows 10
Created 2020-Oct-20
'''

import os
import platform
import sys
import matplotlib as mpl
import numpy as np
import matplotlib.pyplot as plt
import time
from ctypes import (byref, c_bool, c_float, c_uint, c_uint8, c_uint16, c_uint32)
from instruments.mircat import SDK
from . import defaults
from timeit import default_timer as timer
from instruments.ni_daq import MultiChannelAnalogInput as MultiAI
from instruments.daylight.MIRcatSDKConstants import MIRcatSDK_UNITS_CM1, MIRcatSDK_UNITS_MICRONS
# from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtCore import QObject, QThread, pyqtSignal

### Define narrow QCL ranges with unused wavelengths/numbers before and after.
### This leaves space to sweep a little before and after the requested range.
### This should guarantee all requested points are actually measured.
### If using pre-restricted values from "defaults", check the margin there.
WL_MAR_UM = 0.05 # Wavelength safety margin, um
WL_NRANGE_QCL1 = [defaults.MIN_WL_QCL1_UM + WL_MAR_UM, # Restricted
                  defaults.MAX_WL_QCL1_UM] # Already restricted in definitions
WL_NRANGE_QCL2 = [defaults.MIN_WL_QCL2_UM, # Already restricted in definitions
                  defaults.MAX_WL_QCL2_UM] # Already restricted in definitions
WL_NRANGE_QCL3 = [defaults.MIN_WL_QCL3_UM, # Already restricted in definitions
                  defaults.MAX_WL_QCL3_UM - WL_MAR_UM] # Restricted
WL_NRANGE_QCL4 = [defaults.MIN_WL_QCL4_UM + WL_MAR_UM, # Restricted
                  defaults.MAX_WL_QCL4_UM - WL_MAR_UM] # Restricted
WN_MAR_INVCM = 10 # Wavenumber safety margin, cm^-1
WN_NRANGE_QCL1 = [defaults.MIN_WN_QCL1_INVCM + WN_MAR_INVCM, # Restricted
                  defaults.MAX_WN_QCL1_INVCM] # Already restricted in definitions
WN_NRANGE_QCL2 = [defaults.MIN_WN_QCL2_INVCM, # Already restricted in definitions
                  defaults.MAX_WN_QCL2_INVCM] # Already restricted in definitions
WN_NRANGE_QCL3 = [defaults.MIN_WN_QCL3_INVCM, # Already restricted in definitions
                  defaults.MAX_WN_QCL3_INVCM - WN_MAR_INVCM] # Restricted
WN_NRANGE_QCL4 = [defaults.MIN_WN_QCL4_INVCM + WN_MAR_INVCM, # Restricted
                  defaults.MAX_WN_QCL4_INVCM - WN_MAR_INVCM] # Restricted


class experiment(QObject):
    '''Directory management, calls scan and sweep routines.
       Runs in a separate thread.'''
    acquisitionTimer = pyqtSignal(int)
    finished = pyqtSignal()
    finishedOne = pyqtSignal(int)
    finishedMulti = pyqtSignal()
    outData = pyqtSignal(np.ndarray) # Return data to UI for plotting
    outParams = pyqtSignal(object) # Return parameters for re-use with "repeat"
    startedOne = pyqtSignal(int)
    stopped = False

    def __init__(self):
        '''Parameters must be set by caller for any method to work.'''
        super().__init__()
        self.parameters = [] # Parameters from caller, placeholder value

    def multiple(self):
        '''Multiple acquisitions'''
        startRun = timer()
        ### Use sweep for multiple acquistions
        self.parameters.sweeping = True
        while not self.stopped:
            print('Acquisition {:.0f}'.format(self.parameters.acquisitions + 1))
            self.startedOne.emit(self.parameters.acquisitions)
            if self.parameters.acquisitions == 0:
                self.run() # For the first acquisition, use "run"
            else:
                # self.repeat() # For subsequent acquisitions, use "repeat"
                self.run() # For the first acquisition, use "run"
            self.parameters.acquisitions += 1
            self.finishedOne.emit(self.parameters.acquisitions)
            ### Troubleshooting
            # MAX_N_ACQ = 3 # Troubleshooting
            # if self.parameters.acquisitions > MAX_N_ACQ:
            #     print('Exceeded maximum number of acquisitions')
            #     self.stopped = True
            ### Wait interval before starting next acquisition
            while timer() - startRun < self.parameters.acquisitions * self.parameters.timeInterval and not self.stopped:
                self.acquisitionTimer.emit(timer() - startRun)
                # print('Waiting. Elapsed: {:.0f} s.'.format(timer() - startRun))
                time.sleep(1)
        self.stopped = False
        self.parameters.acquisitions = 0
        self.finishedMulti.emit()

    def repeat(self):
        '''
        Run the same experiment again. Saves time compared to "run".
        Ineffective if "run" has not been used before for a given instance.
        '''
        ### Invert direction
        self.parameters.sweepLimits.reverse()
        self.parameters.ranges.reverse()
        self.parameters.qcl.reverse()
        for x, (l, r) in enumerate(zip(self.parameters.sweepLimits, self.parameters.ranges)):
            l.reverse()
            r.reverse()
        ### Go to main experiment directory
        workDir = defaults.DEF_DATA_DIRECTORY
        os.chdir(workDir)
        ### Get latest experiment number from previously created folder
        # print(self.latestDir) # Troubleshooting
        oldExpNo = int(self.parameters.latestDir[-3:])
        ### Create new experiment folder
        newExpNo = oldExpNo + 1;
        expNoStr = '%03.0f' % (newExpNo)
        dateStr = time.strftime('%Y-%m-%d')
        expFolder = dateStr + '_' + expNoStr
        expDir = os.path.join(workDir, expFolder)
        ### Proper use of "repeat" should make this check unnecessary
        while os.path.exists(expDir):
            newExpNo += 1;
            expNoStr = '%03.0f' % (newExpNo)
            expFolder = dateStr + '_' + expNoStr
            expDir = os.path.join(workDir, expFolder)
        ### Create experiment folder and chdir to it
        os.mkdir(expDir)
        os.chdir(expDir)
        ### Save experiment notes to file
        # if not len(self.notes) == 0:
        #     noteFile = open('notes.txt', 'w')
        #     noteFile.write(self.notes)
        #     noteFile.close()
        ### Run a sweep or a step-and-measure scan
        data = []
        if self.parameters.sweeping:
            data = self.sweep()
        else: # Default to step-and-measure
            data = self.scan()
        self.outData.emit(data)
        self.outParams.emit(self.parameters)
        self.finished.emit()

    def run(self):
        '''Run experiment, calling "scan" or "sweep".'''
        ### Zero previous ranges and limits, if any
        self.parameters.sweepLimits = []
        self.parameters.ranges = []
        self.parameters.qcl = []
        ### Make "raw" range with requested values
        if self.parameters.start > self.parameters.end:
            self.parameters.start, self.parameters.end = self.parameters.end, self.parameters.start
        rawRange = np.arange(self.parameters.start, self.parameters.end, self.parameters.step)
        if len(rawRange) < 1: # Requested limits are out of QCL bounds
            print('Cannot sweep requested range.')
            return [[], self]
        ### Make a separate range for each QCL
        ranges = [[], [], [], []] # Store allowed wavelengths/numbers per QCL
        if self.parameters.units == 'invcm':
            for wn in rawRange:
                if WN_NRANGE_QCL1[0] >= wn >= WN_NRANGE_QCL1[1]:
                    ranges[0].append(wn)
                elif WN_NRANGE_QCL2[0] > wn >= WN_NRANGE_QCL2[1]:
                    ranges[1].append(wn)
                elif WN_NRANGE_QCL3[0] > wn >= WN_NRANGE_QCL3[1]:
                    ranges[2].append(wn)
                elif WN_NRANGE_QCL4[0] >= wn >= WN_NRANGE_QCL4[1]:
                    ranges[3].append(wn)
        else: # Default to micrometers
            for wl in rawRange:
                if WL_NRANGE_QCL1[0] <= wl <= WL_NRANGE_QCL1[1]:
                    ranges[0].append(wl)
                elif WL_NRANGE_QCL2[0] < wl <= WL_NRANGE_QCL2[1]:
                    ranges[1].append(wl)
                elif WL_NRANGE_QCL3[0] < wl <= WL_NRANGE_QCL3[1]:
                    ranges[2].append(wl)
                elif WL_NRANGE_QCL4[0] <= wl <= WL_NRANGE_QCL4[1]:
                    ranges[3].append(wl)
        ### Determine which QCL modules need to be used
        for x, r in enumerate(ranges):
            if r != []: # if this range is not empty
                self.parameters.qcl.append(x+1) # QCLs are numbered 1--4
        ### Compile QCL ranges in class variable, if not empty
        for r in ranges:
            if len(r) > 0: # If not empty
                self.parameters.ranges.append(r)
        ### Compile sweep ranges, adding margins
        if self.parameters.sweeping:
            if self.parameters.units == 'invcm':
                for r in self.parameters.ranges:
                    r.reverse() # Default order is from higher energy down
                    self.parameters.sweepLimits.append([r[0] + WN_MAR_INVCM,
                                             r[-1] - WN_MAR_INVCM])
            else: # Default to micrometers
                for r in self.parameters.ranges:
                    self.parameters.sweepLimits.append([r[0] - WL_MAR_UM,
                                             r[-1] + WL_MAR_UM])
        ### Create individual experiment folder
        workDir = defaults.DEF_DATA_DIRECTORY
        os.chdir(workDir)
        newExpNo = 1;
        expNoStr = '%03.0f' % (newExpNo)
        dateStr = time.strftime('%Y-%m-%d')
        expFolder = dateStr + '_' + expNoStr
        expDir = os.path.join(workDir, expFolder)
        while os.path.exists(expDir):
            newExpNo += 1;
            expNoStr = '%03.0f' % (newExpNo)
            expFolder = dateStr + '_' + expNoStr
            expDir = os.path.join(workDir, expFolder)
        os.mkdir(expDir)
        os.chdir(expDir)
        self.parameters.latestDir = expDir
        ### Save experiment notes to file
        if not len(self.parameters.notes) == 0:
            noteFile = open('notes.txt', 'w')
            noteFile.write(self.parameters.notes)
            noteFile.close()
        ### Write parameters to log
        logFile = open('experiment.log', 'w')
        logFile.write('QCL/Microscope experiment log\n')
        timeStr = time.strftime('%Y-%m-%d %H:%M:%S\n')
        logFile.write('{}'.format(timeStr))
        logFile.write('No. {:.0f}\n'.format(newExpNo))
        logFile.write('\n')
        for qclNo in self.parameters.qcl:
            qclCurr = self.parameters.laser.get_current(qclNo)
            qclRate = self.parameters.laser.get_pulse_rate(qclNo)
            qclWidth = self.parameters.laser.get_pulse_width(qclNo)
            logFile.write('QCL {:.0f}: {:.0f} mA, {:.0f} Hz, {:.0f} ns.\n'.format(
                                            qclNo, qclCurr, qclRate, qclWidth))
        logFile.write('\n')
        if self.parameters.sweeping:
            logFile.write('Type: sweep\n')
        else:
            logFile.write('Type: step-and-measure\n')
        logFile.write('\n')
        logFile.write('Target wavelengths/wavenumbers:\n')
        logFile.write('{}\n'.format(self.parameters.ranges))
        logFile.write('\n')
        logFile.write('Sweep limits:\n')
        logFile.write('{}\n'.format(self.parameters.sweepLimits))
        logFile.write('\n')
        logFile.close()
        ### Run a sweep or a step-and-measure scan
        data = []
        if self.parameters.sweeping:
            data = self.sweep()
        else: # Default to step-and-measure
            data = self.scan()
        self.outData.emit(data)
        self.outParams.emit(self.parameters)
        self.finished.emit()

    def scan(self):
        '''Run a step-and measure scan by tuning to each wavelength/number.'''
        ### Preamble
        print('Scan started ...')
        print('One wavelength point per step, avg. of {:.0f} samples at {:.0f} Hz'
              .format(self.parameters.sampleNumber, self.parameters.sampleRate))
        startRun = timer()
        ### Setup acquisition
        multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
        multipleAI.configure(self.parameters.sampleNumber, self.parameters.sampleRate)
        ### Run multi-range scan
        numRanges = len(self.parameters.ranges)
        steps = 0
        voltages, wavelengths = [], []
        for x, r in enumerate(self.parameters.ranges):
            steps += len(r)
            wavelengths +=r
            qcl = self.parameters.qcl[x]
            print('Range {}/{}, using QCL module {}...'.format(
                                                           x+1, numRanges, qcl))
            ### Acquisition
            rangeVoltages = []
            try: # Failure here likely due to timeout because of skipped points
                for wl in r:
                    ### Tune
                    self.parameters.laser.tune(qcl, wl, self.parameters.units)
                    ### Acquire
                    rangeVoltages.append(multipleAI.acquire(self.parameters.sampleNumber))
            except Exception as exc:
                print('Scan did not complete:\n{}'.format(exc))
                print('Partial data may still be usable.')
            voltages += rangeVoltages
        ### Clear triggered acquisition task
        multipleAI.clear_task()
        ### Format data
        data = np.zeros((steps, 4)) # wl, X, Y, R
        try:
            for x, v in enumerate(voltages):
                data[x, 0] = wavelengths[x]
                data[x, 1] = np.sum(v[0])/self.parameters.sampleNumber # Lock-in X
                data[x, 2] = np.sum(v[1])/self.parameters.sampleNumber # Lock-in Y
                data[x, 3] = (np.sqrt(np.power(data[x, 1], 2) +
                                      np.power(data[x, 2], 2))) # Lock-in R
        except Exception as exc:
            print('Data formatting did not complete:\n{}'.format(exc))
            print('Data was not saved.')
        data = data[data[:, 0] != 0] # Remove zero-wavelength values
        endRun = timer()
        print('Acquired {} of {} requested points.'.format(len(data[:, 0]),
                                                              len(wavelengths)))
        print('Scan complete (%.3f s).' % (endRun-startRun))
        ### Flip data order if it was reversed by repeat
        if (self.parameters.units == 'um' and data[0, 0] > data[-1, 0]
             or self.parameters.units == 'invcm' and data[0, 0] < data[-1, 0]):
            data = np.flip(data, 0)
        ### Save data as text file
        currentDir = os.getcwd()
        if platform.system() == 'Windows':
            currentDirSplit = currentDir.split('\\')
        else:
            currentDirSplit = currentDir.split('/')
        currentFolder = currentDirSplit[-1]
        np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME), data)
        return data

    def stop(self):
        '''Set stop flag. For use with "multiple" only.'''
        self.stopped = True

    def sweep(self):
        '''Run a sweep using the MIRcat's built-in function.'''
        ### Troubleshooting
        SDK.MIRcatSDK_StopScanInProgress() # Make sure previous sweep has ended
        ### Preamble
        print('Sweep started ...')
        print('One wavelength point per step, avg. of {:.0f} samples at {:.0f} Hz'
              .format(self.parameters.sampleNumber, self.parameters.sampleRate))
        startRun = timer()
        ### Setup, start triggered acquisition task
        multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
        multipleAI.configure_triggered(defaults.PCI_TRIG,
                                       self.parameters.sampleNumber, self.parameters.sampleRate)
                                       ### Start task
        multipleAI.start_task()
        ### Run multi-range sweep
        numRanges = len(self.parameters.ranges)
        steps = 0
        voltages, wavelengths = [], []
        for x, (l, r) in enumerate(zip(self.parameters.sweepLimits, self.parameters.ranges)):
            steps += len(r)
            wavelengths +=r
            ### Print QCL module in use
            print('Range {}/{}, using QCL module {}...'.format(
                x+1, numRanges, self.parameters.qcl[x]))
            ### Set laser triggering (one TTL pulse per wl/wn) and start sweep
            print('Trigger: {:.2f} to {:.2f} {}, {:.2f} {} step.'.format(
                                r[0], r[-1], self.parameters.units, self.parameters.step, self.parameters.units))
            self.parameters.laser.set_wl_trigger_parameters(r[-1], r[0], self.parameters.step,
                                                                     self.parameters.units)
            ### Start sweep
            print('Sweep: {:.2f} to {:.2f} {}, {:.2f} {}/s.'.format(
                                l[0], l[-1],self.parameters.units, self.parameters.speed, self.parameters.units))
            self.parameters.laser.sweep_and_forget(l[0], l[-1], self.parameters.speed, self.parameters.units,
                                                                    self.parameters.qcl[x])
            ### Triggered acquisition
            rangeVoltages = []
            try: # Failure here likely due to timeout because of skipped points
                for x in range(0, len(r)):
                    rangeVoltages.append(multipleAI.acquire_fast(self.parameters.sampleNumber))
            except Exception as exc:
                print('Sweep did not complete:\n{}'.format(exc))
                print('Partial data may still be usable.')
            voltages += rangeVoltages
            # print(wavelengths) # Troubleshooting
            # print(voltages) # Troubleshooting
            SDK.MIRcatSDK_StopScanInProgress() # Make sure this sweep has ended
        ### Stop, clear triggered acquisition task
        multipleAI.stop_task() # Stop acquisition task
        multipleAI.clear_task()
        ### Format data
        data = np.zeros((steps, 4)) # wl, X, Y, R
        try: # Failure here certain if points skipped above
            for x, v in enumerate(voltages):
                data[x, 0] = wavelengths[x]
                data[x, 1] = np.sum(v[0])/self.parameters.sampleNumber # Lock-in X
                data[x, 2] = np.sum(v[1])/self.parameters.sampleNumber # Lock-in Y
                data[x, 3] = (np.sqrt(np.power(data[x, 1], 2) +
                                      np.power(data[x, 2], 2))) # Lock-in R
        except Exception as exc:
            print('Data formatting did not complete:\n{}'.format(exc))
            print('Data was not saved.')
        data = data[data[:, 0] != 0] # Remove zero-wavelength values
        endRun = timer()
        print('Acquired {} of {} requested points.'.format(len(data[:, 0]),
                                                              len(wavelengths)))
        print('Sweep complete (%.3f s).' % (endRun-startRun))
        ### Flip data order if it was reversed by repeat
        if (self.parameters.units == 'um' and data[0, 0] > data[-1, 0]
             or self.parameters.units == 'invcm' and data[0, 0] < data[-1, 0]):
            data = np.flip(data, 0)
        ### Save data as text file
        currentDir = os.getcwd()
        if platform.system() == 'Windows':
            currentDirSplit = currentDir.split('\\')
        else:
            currentDirSplit = currentDir.split('/')
        currentFolder = currentDirSplit[-1]
        np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME), data)
        return data


class imagingScan(QObject):
    '''Manages directiories and scanning imaging routines.
       Runs in a separate thread.'''
    # acquisitionTimer = pyqtSignal(int)
    finished = pyqtSignal()
    # finishedOne = pyqtSignal(int)
    # finishedMulti = pyqtSignal()
    # outData = pyqtSignal(np.ndarray) # Return data to UI for plotting
    outData = pyqtSignal(object) # Return data to UI for plotting
    outParams = pyqtSignal(object) # Return parameters for re-use with "re"
    stageMoved = pyqtSignal(float, float)
    # startedOne = pyqtSignal(int)
    # stopped = False

    def __init__(self):
        '''Parameters must be set by caller for any method to work.'''
        super().__init__()
        self.parameters = [] # Parameters from caller, placeholder value

    def run(self):
        '''Run experiment, calling "scan".'''
        ### Zero previous ranges and limits, if any
        # self.parameters.sweepLimits = []
        self.parameters.ranges = []
        self.parameters.qcl = []
        for p, sn, sr, sp, w in zip(self.parameters.patterns,
                                    self.parameters.sampleNumbers,
                                    self.parameters.sampleRates,
                                    self.parameters.speeds,
                                    self.parameters.wlwnList):
            ### Make a separate range for each QCL
            ranges = [[], [], [], []] # Store allowed wavelengths/numbers per QCL
            if self.parameters.units == 'invcm':
                for wn in w:
                    if WN_NRANGE_QCL1[0] >= wn >= WN_NRANGE_QCL1[1]:
                        ranges[0].append(wn)
                    elif WN_NRANGE_QCL2[0] > wn >= WN_NRANGE_QCL2[1]:
                        ranges[1].append(wn)
                    elif WN_NRANGE_QCL3[0] > wn >= WN_NRANGE_QCL3[1]:
                        ranges[2].append(wn)
                    elif WN_NRANGE_QCL4[0] >= wn >= WN_NRANGE_QCL4[1]:
                        ranges[3].append(wn)
            else: # Default to micrometers
                for wl in w:
                    if WL_NRANGE_QCL1[0] <= wl <= WL_NRANGE_QCL1[1]:
                        ranges[0].append(wl)
                    elif WL_NRANGE_QCL2[0] < wl <= WL_NRANGE_QCL2[1]:
                        ranges[1].append(wl)
                    elif WL_NRANGE_QCL3[0] < wl <= WL_NRANGE_QCL3[1]:
                        ranges[2].append(wl)
                    elif WL_NRANGE_QCL4[0] <= wl <= WL_NRANGE_QCL4[1]:
                        ranges[3].append(wl)
            ### Determine which QCL modules need to be used
            targetQcls, targetRanges = [], []
            for x, r in enumerate(ranges):
                if r != []: # if this range is not empty
                    targetQcls.append(x+1) # QCLs are numbered 1--4
            ### Compile QCL ranges in class variable, if not empty
            for r in ranges:
                if len(r) > 0: # If not empty
                    targetRanges.append(r)
            self.parameters.qcl.append(targetQcls)
            self.parameters.ranges.append(targetRanges)
        ### Compile sweep ranges, adding margins
        # if self.parameters.sweeping:
        #     if self.parameters.units == 'invcm':
        #         for r in self.parameters.ranges:
        #             r.reverse() # Default order is from higher energy down
        #             self.parameters.sweepLimits.append([r[0] + WN_MAR_INVCM,
        #                                      r[-1] - WN_MAR_INVCM])
        #     else: # Default to micrometers
        #         for r in self.parameters.ranges:
        #             self.parameters.sweepLimits.append([r[0] - WL_MAR_UM,
        #                                      r[-1] + WL_MAR_UM])
        ### Create individual experiment folder
        workDir = defaults.DEF_DATA_DIRECTORY
        os.chdir(workDir)
        newExpNo = 1;
        expNoStr = '%03.0f' % (newExpNo)
        dateStr = time.strftime('%Y-%m-%d')
        expFolder = dateStr + '_' + expNoStr
        expDir = os.path.join(workDir, expFolder)
        while os.path.exists(expDir):
            newExpNo += 1;
            expNoStr = '%03.0f' % (newExpNo)
            expFolder = dateStr + '_' + expNoStr
            expDir = os.path.join(workDir, expFolder)
        os.mkdir(expDir)
        os.chdir(expDir)
        self.parameters.latestDir = expDir
        ### Save experiment notes to file
        # if not len(self.parameters.notes) == 0:
        #     noteFile = open('notes.txt', 'w')
        #     noteFile.write(self.parameters.notes)
        #     noteFile.close()
        ### Write parameters to log
        logFile = open('experiment.log', 'w')
        logFile.write('QCL/Microscope scanning imaging experiment log\n')
        timeStr = time.strftime('%Y-%m-%d %H:%M:%S\n')
        logFile.write('{}'.format(timeStr))
        logFile.write('No. {:.0f}\n'.format(newExpNo))
        logFile.write('\n')
        # for qclNo in self.parameters.qcl:
        #     qclCurr = self.parameters.laser.get_current(qclNo)
        #     qclRate = self.parameters.laser.get_pulse_rate(qclNo)
        #     qclWidth = self.parameters.laser.get_pulse_width(qclNo)
        #     logFile.write('QCL {:.0f}: {:.0f} mA, {:.0f} Hz, {:.0f} ns.\n'.format(
        #                                     qclNo, qclCurr, qclRate, qclWidth))
        logFile.write('\n')
        # if self.parameters.sweeping:
        #     logFile.write('Type: sweep\n')
        # else:
        #     logFile.write('Type: step-and-measure\n')
        # logFile.write('\n')
        # logFile.write('Target wavelengths/wavenumbers:\n')
        # logFile.write('{}\n'.format(self.parameters.ranges))
        # logFile.write('\n')
        # logFile.write('Sweep limits:\n')
        # logFile.write('{}\n'.format(self.parameters.sweepLimits))
        # logFile.write('\n')
        # logFile.close()
        ### Run a sweep or a step-and-measure scan
        data = []
        # if self.parameters.sweeping:
        #     data = self.sweep()
        # else: # Default to step-and-measure
        #     data = self.scan()
        self.parameters.data = self.scan()
        self.outData.emit(self.parameters.data)
        self.outParams.emit(self.parameters)
        self.finished.emit()

    def scan(self):
        '''Run scanning imaging experiment and output data.'''
        ### Prepare to save data
        currentDir = os.getcwd()
        # if platform.system() == 'Windows':
        #     currentDirSplit = currentDir.split('\\')
        # else:
        #     currentDirSplit = currentDir.split('/')
        scanImagDir = os.path.join(currentDir, defaults.DEF_SCAN_IMAG_SUBFOLDER)
        os.mkdir(scanImagDir)
        os.chdir(scanImagDir)
        ### Preamble
        print('Scan started ...')
        # print('One wavelength point per step, avg. of {:.0f} samples at {:.0f} Hz'
        #       .format(self.parameters.sampleNumber, self.parameters.sampleRate))
        startRun = timer()
        match self.parameters.scanMode:
            case 'step_one':
                '''Step scan: one wavelength per (x,y) position'''
                posx, posy, indx, indy, voltages, wavelengths = [], [], [], [], [], []
                dataIndexPattern = 0
                ### Iterate over scan patterns
                for p, sn, sr, sp, w, qcl, r, ind in zip(self.parameters.patterns,
                                                        self.parameters.sampleNumbers,
                                                        self.parameters.sampleRates,
                                                        self.parameters.speeds,
                                                        self.parameters.wlwnList,
                                                        self.parameters.qcl,
                                                        self.parameters.ranges,
                                                        self.parameters.patternIndices):
                    ### Setup acquisition
                    multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
                    multipleAI.configure(sn, sr)
                    ### Iterate over QCL ranges
                    numRanges = len(r)
                    for i, rw in enumerate(r):
                        print('Range {}/{}, using QCL module {}...'.format(
                            i+1, numRanges, qcl[i]))
                        try:
                            ### Iterate over wavelengths
                            for wl in rw:
                                ### Get corresponding index in data variable
                                dataIndexWl = self.parameters.data.W[dataIndexPattern].index(wl)
                                ### Tune
                                self.parameters.laser.tune(qcl[i], wl, self.parameters.units)
                                ### Iterate over positions
                                for x, y, ix, iy in zip(p[:, 0], p[:, 1], ind[:, 0], ind[:, 1]):
                                    ### Move stage
                                    self.parameters.stage.goto(x, y)
                                    ### Wait for stage to stop moving
                                    while int(self.parameters.stage.busy()) > 0:
                                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
                                    (xStg, yStg) = self.parameters.stage.get_position()
                                    # print('{}/{} patterns, '.format(), end ='')
                                    # print('{}/{} wavelengths, '.format(), end ='')
                                    self.stageMoved.emit(xStg, yStg)
                                    print('Scanning: x {:.0f} μm, y {:.0f} μm'.format(
                                        xStg, yStg), end='\r')
                                    ### Acquire
                                    measurements = multipleAI.acquire(sn)
                                    ### Append data
                                    self.parameters.data.Vtemp[dataIndexPattern][dataIndexWl].append(measurements)
                        except Exception as exc:
                            print('Scan did not complete:\n{}'.format(exc))
                            print('Partial data may still be usable.')
                    ### Clear acquisition task
                    multipleAI.clear_task()
                    ### Increment pattern-counting index
                    dataIndexPattern += 1
                ### Format data
                try:
                    for iv, v in enumerate(self.parameters.data.Vtemp):
                        ### Save X, Y positions for this pattern
                        np.savetxt('scan{:03.0f}{}'.format(
                            iv + 1,
                            defaults.DEF_FILENAME_SCAN_IMAG_X),
                            self.parameters.data.X[iv])
                        np.savetxt('scan{:03.0f}{}'.format(
                            iv + 1,
                            defaults.DEF_FILENAME_SCAN_IMAG_Y),
                            self.parameters.data.Y[iv])
                        for iw, w in enumerate(self.parameters.data.W[iv]):
                            vpos = 0
                            for ix, iy in zip(self.parameters.data.indices[iv][:, 0],
                                self.parameters.data.indices[iv][:, 1]):
                                    liX = np.sum(v[iw][vpos][0])/sn # Lock-in X
                                    liY = np.sum(v[iw][vpos][1])/sn # Lock-in Y
                                    liR = (np.sqrt(np.power(liX, 2) +
                                            np.power(liY, 2))) # Lock-in R
                                    self.parameters.data.V[iv][iw][ix][iy] = liR
                                    vpos += 1
                            if self.parameters.units in ['invcm']:
                                wStr = 'wm-{:05.0f}invcm'.format(w)
                            else:
                                wStr = 'wl-{:02.3f}um'.format(w)
                            np.savetxt('scan{:03.0f}_{}{}'.format(
                                iv + 1,
                                wStr,
                                defaults.DEF_FILENAME_SCAN_IMAG_V),
                                self.parameters.data.V[iv][iw])
                except Exception as exc:
                    print('Data formatting did not complete:\n{}'.format(exc))
                    print('Data was not saved.')
                    # data = data[data[:, 0] != 0] # Remove zero-wavelength values
                    # print('Acquired {} of {} requested points.'.format(len(data[:, 0]),
                    #                                             len(wavelengths)))
            case 'step_all':
                '''Step scan: all wavelengths at each (x,y) position'''
                print('Not implemented.')
                return []
            case 'step_sweep':
                '''Step scan: QCL sweep at each (x,y) position'''
                print('Not implemented.')
                return []
            case 'continuous_one':
                '''Continuous scan: one wavelength per (x,y) position'''
                posx, posy, indx, indy, voltages, wavelengths = [], [], [], [], [], []
                dataIndexPattern = 0
                ### Iterate over scan patterns
                for fp, sn, sr, w, qcl, r, ind, sd in zip(self.parameters.fastPatterns,
                                                        self.parameters.sampleNumbers,
                                                        self.parameters.sampleRates,
                                                        self.parameters.wlwnList,
                                                        self.parameters.qcl,
                                                        self.parameters.ranges,
                                                        self.parameters.patternIndices,
                                                        self.parameters.scanDir):
                    ### Assign stage speeds for scan lines
                    if sd in ['x', 'X']:
                        vx = self.parameters.stage.get_speed()
                        vy = 0
                    elif sd in ['y', 'Y']: # default to scanning along x
                        vx = 0
                        vy = self.parameters.stage.get_speed()
                    else: # default to scanning along x
                        vx = self.parameters.stage.get_speed()
                        vy = 0
                    ### Setup acquisition
                    multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
                    multipleAI.configure(sn, sr)
                    ### Iterate over QCL ranges
                    numRanges = len(r)
                    for i, rw in enumerate(r):
                        print('Range {}/{}, using QCL module {}...'.format(
                             i+1, numRanges, qcl[i]))
                        try:
                            ### Iterate over wavelengths
                            for wl in rw:
                                ### Get corresponding index in data variable
                                dataIndexWl = self.parameters.data.W[dataIndexPattern].index(wl)
                                ### Tune
                                self.parameters.laser.tune(qcl[i], wl, self.parameters.units)
                                ### Split pattern in starting and target positions
                                targetSize0 = int(np.shape(fp)[0]/2)
                                targetSize1 = np.shape(fp)[1]
                                starting = np.zeros((targetSize0, targetSize1))
                                target = np.zeros((targetSize0, targetSize1))
                                for i, (x, y) in enumerate(zip(fp[:, 0], fp[:, 1])):
                                    j = int(np.floor(i/2))
                                    if i % 2 == 0:
                                        starting[j, 0] = x
                                        starting[j, 1] = y
                                    else:
                                        target[j, 0] = x
                                        target[j, 1] = y
                                ### Iterate over positions
                                for i, (x, y) in enumerate(zip(starting[:, 0], starting[:, 1])):
                                    ### Position stage for scan line
                                    self.parameters.stage.goto(x, y)
                                    ### Wait for stage to stop moving
                                    while int(self.parameters.stage.busy()) > 0:
                                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
                                    ### Emit line start position
                                    (xStg, yStg) = self.parameters.stage.get_position()
                                    self.stageMoved.emit(xStg, yStg)
                                    print('Scanning line {:.0f}/{:.0f} starting at x {:.0f} μm, y {:.0f} μm'.format(
                                        i + 1, len(starting), xStg, yStg))
                                    ### Assign scan line end points
                                    xEnd = target[i, 0]
                                    yEnd = target[i, 1]
                                    ### Set conditions for stage stop
                                    ### Account for scans in negative direction
                                    if vx == 0:
                                        if yEnd > y:
                                            vy = np.abs(vy)
                                            continueCondition = lambda xStg, yStg: yStg < yEnd
                                        else:
                                            vy = -1 * np.abs(vy)
                                            continueCondition = lambda xStg, yStg: yStg > yEnd
                                    if vy == 0:
                                        if xEnd > x:
                                            vx = np.abs(vx)
                                            continueCondition = lambda xStg, yStg: xStg < xEnd
                                        else:
                                            vx = -1 * np.abs(vx)
                                            continueCondition = lambda xStg, yStg: xStg > xEnd
                                    ### Move stage
                                    self.parameters.stage.move_at_velocity(vx, vy)
                                    ### Acquire until endpoint is reached
                                    while continueCondition(xStg, yStg):
                                        (xStg, yStg) = self.parameters.stage.get_position()
                                        ### Acquire
                                        measurements = multipleAI.acquire(sn)
                                        ### Append data
                                        self.parameters.data.Vtemp[dataIndexPattern][dataIndexWl].append(measurements)
                                    ### Stop stage at end of line
                                    # self.parameters.stage.move_at_velocity(0, 0)
                                    self.parameters.stage.stop_smoothly()
                                    while int(self.parameters.stage.busy()) > 0:
                                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
                                ### Emit ending position
                                (xStg, yStg) = self.parameters.stage.get_position()
                                self.stageMoved.emit(xStg, yStg)
                        except Exception as exc:
                            print('Scan did not complete:\n{}'.format(exc))
                            print('Partial data may still be usable.')
                    ### Clear acquisition task
                    multipleAI.clear_task()
                    ### Increment pattern-counting index
                    dataIndexPattern += 1
                ### Format data
                try:
                    for iv, v in enumerate(self.parameters.data.Vtemp):
                        ### Save X, Y positions for this pattern
                        np.savetxt('scan{:03.0f}{}'.format(
                            iv + 1,
                            defaults.DEF_FILENAME_SCAN_IMAG_X),
                            self.parameters.data.X[iv])
                        np.savetxt('scan{:03.0f}{}'.format(
                            iv + 1,
                            defaults.DEF_FILENAME_SCAN_IMAG_Y),
                            self.parameters.data.Y[iv])
                        for iw, w in enumerate(self.parameters.data.W[iv]):
                            vpos = 0
                            for ix, iy in zip(self.parameters.data.indices[iv][:, 0],
                                self.parameters.data.indices[iv][:, 1]):
                                    liX = np.sum(v[iw][vpos][0])/sn # Lock-in X
                                    liY = np.sum(v[iw][vpos][1])/sn # Lock-in Y
                                    liR = (np.sqrt(np.power(liX, 2) +
                                            np.power(liY, 2))) # Lock-in R
                                    self.parameters.data.V[iv][iw][ix][iy] = liR
                                    vpos += 1
                            if self.parameters.units in ['invcm']:
                                wStr = 'wm-{:05.0f}invcm'.format(w)
                            else:
                                wStr = 'wl-{:02.3f}um'.format(w)
                            np.savetxt('scan{:03.0f}_{}{}'.format(
                                iv + 1,
                                wStr,
                                defaults.DEF_FILENAME_SCAN_IMAG_V),
                                self.parameters.data.V[iv][iw])
                except Exception as exc:
                    print('Data formatting did not complete:\n{}'.format(exc))
                    print('Data was not saved.')
            case 'continuous_sweep':
                print('Not implemented.')
                return []
            case _:
                print('Invalid scan mode selected.')
                return []
        endRun = timer()
        print('Scan complete (%.3f s).' % (endRun-startRun))
        # '''Save data as text file'''
        ### Return to experiment folder
        os.chdir(currentDir)
        # currentDir = os.getcwd()
        # if platform.system() == 'Windows':
        #     currentDirSplit = currentDir.split('\\')
        # else:
        #     currentDirSplit = currentDir.split('/')
        # currentFolder = currentDirSplit[-1]
        # np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME_XY), data)
        return self.parameters.data