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
'''
'''
from instruments.mircat import whichQCL
import instruments.hld117 as hld117
from instruments.pi_scanner import piScanner, piScanner_widget
'''
'''
'''
08/07/2023 Po-Ting Shen
'''
import csv
'''
'''


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

        print("Start debug prints:")
        print("How many patterns?")
        print(len(self.parameters.patterns))
        print("How many wlwnList?")
        print(len(self.parameters.wlwnList))
        print("How many wlwn in wlwnList[0]?")
        print(len(self.parameters.wlwnList[0]))
        print('Units: '+self.parameters.units)

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

        print('Ranges: '+ str(self.parameters.ranges))
        print("End debug prints!")
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
        ### Write parameters to log
        logFile = open(defaults.LOG_FILENAME, 'w')
        logFile.write('QCL Microscope scanning imaging experiment log\n')
        timeStr = time.strftime('%Y-%m-%d %H:%M:%S\n')
        logFile.write('{}'.format(timeStr))
        logFile.write('No. {:.0f}\n'.format(newExpNo))
        logFile.write('Type: {}\n'.format(self.parameters.scanMode))
        logFile.write('\n')
        for ip, _ in enumerate(self.parameters.patterns):
            logFile.write('Pattern {:.0f}\n'.format(ip))
            logFile.write('\n')
            logFile.write('- QCL modules in use:\n')
            for qclNo in self.parameters.qcl[ip]:
                qclCurr = self.parameters.laser.get_current(qclNo)
                qclRate = self.parameters.laser.get_pulse_rate(qclNo)
                qclWidth = self.parameters.laser.get_pulse_width(qclNo)
                logFile.write('  QCL {:.0f}: {:.0f} mA, {:.0f} Hz, {:.0f} ns.\n'.format(
                                                qclNo, qclCurr, qclRate, qclWidth))
            logFile.write('- Target wavelengths/wavenumbers (um or cm^-1):\n')
            logFile.write('  {}\n'.format(self.parameters.ranges[ip]))
            logFile.write('- Scan parameters:\n')
            logFile.write('  x start/step/size (um): {}/{}/{}\n'.format(
                self.parameters.xParameters[ip][0],
                self.parameters.xParameters[ip][1],
                self.parameters.xParameters[ip][2]))
            logFile.write('  y start/step/size (um): {}/{}/{}\n'.format(
                self.parameters.yParameters[ip][0],
                self.parameters.yParameters[ip][1],
                self.parameters.yParameters[ip][2]))
            logFile.write('- Scan direction (stage axis): {}\n'.format(self.parameters.scanDir[ip]))
            logFile.write('- NI DAQ sample rate (Hz): {}\n'.format(self.parameters.sampleRates[ip]))
            logFile.write('- NI DAQ samples per voltage point: {}\n'.format(self.parameters.sampleNumbers[ip]))
            logFile.write('\n')
        logFile.close()
        ### Run scan
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
                                    # self.stageMoved.emit(xStg, yStg)
                                    print('Scanning: x {:.0f} μm, y {:.0f} μm'.format(
                                        xStg, yStg), end='\r')
                                    # print('Scanning: x {:.0f} μm, y {:.0f} μm'.format(
                                    #     xStg, yStg))
                                    ### Acquire
                                    measurements = multipleAI.acquire(sn)
                                    ### Append data
                                    self.parameters.data.Vtemp[dataIndexPattern][dataIndexWl].append(measurements)
                        except Exception as exc:
                            print('')
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
                                    ### Calculate each voltage sample R
                                    ### from voltage sample X & Y
                                    liR = 0
                                    for liX, liY in zip(v[iw][vpos][0], v[iw][vpos][1]):
                                        liR += np.sqrt(np.power(liX, 2) +
                                            np.power(liY, 2))
                                    liR = liR/sn
                                    ### Old method
                                    # liX = np.sum(v[iw][vpos][0])/sn # Lock-in X
                                    # liY = np.sum(v[iw][vpos][1])/sn # Lock-in Y
                                    # liR = (np.sqrt(np.power(liX, 2) +
                                    #         np.power(liY, 2))) # Lock-in R
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
                    print('')
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
                    for irw, rw in enumerate(r):
                        print('Range {}/{}, using QCL module {}...'.format(
                             irw+1, numRanges, qcl[irw]))
                        try:
                            ### Iterate over wavelengths
                            for wl in rw:
                                ### Get corresponding index in data variable
                                dataIndexWl = self.parameters.data.W[dataIndexPattern].index(wl)
                                ### Tune
                                self.parameters.laser.tune(qcl[irw], wl, self.parameters.units)
                                ### Split pattern in starting and target positions
                                targetSize0 = int(np.shape(fp)[0]/2)
                                targetSize1 = np.shape(fp)[1]
                                starting = np.zeros((targetSize0, targetSize1))
                                target = np.zeros((targetSize0, targetSize1))
                                for ixy, (x, y) in enumerate(zip(fp[:, 0], fp[:, 1])):
                                    j = int(np.floor(ixy/2))
                                    if ixy % 2 == 0:
                                        starting[j, 0] = x
                                        starting[j, 1] = y
                                    else:
                                        target[j, 0] = x
                                        target[j, 1] = y
                                ### Iterate over positions
                                for ixy, (x, y) in enumerate(zip(starting[:, 0], starting[:, 1])):
                                    ### Position stage for scan line
                                    self.parameters.stage.goto(x, y)
                                    ### Wait for stage to stop moving
                                    while int(self.parameters.stage.busy()) > 0:
                                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
                                    ### Emit line start position
                                    (xStg, yStg) = self.parameters.stage.get_position()
                                    # self.stageMoved.emit(xStg, yStg)
                                    print('Scanning line {:.0f}/{:.0f} starting at x {:.0f} μm, y {:.0f} μm'.format(
                                        ixy + 1, len(starting), xStg, yStg))
                                    ### Assign scan line end points
                                    xEnd = target[ixy, 0]
                                    yEnd = target[ixy, 1]
                                    ### Set conditions for stage stop
                                    ### Account for scans in negative direction
                                    if vx == 0:
                                        if yEnd > y:
                                            vy = np.abs(vy)
                                            continueCondition = lambda xStg, yStg: yStg < yEnd
                                        else:
                                            vy = -1 * np.abs(vy)
                                            continueCondition = lambda xStg, yStg: yStg > yEnd
                                    else: # Default to scanning along x
                                        if xEnd > x:
                                            vx = np.abs(vx)
                                            continueCondition = lambda xStg, yStg: xStg < xEnd
                                        else:
                                            vx = -1 * np.abs(vx)
                                            continueCondition = lambda xStg, yStg: xStg > xEnd
                                    ### Set position acquisition according to scan direction
                                    positions = []
                                    if vx == 0:
                                        appendPosition = lambda  xStg, yStg: positions.append(yStg)
                                    else:  # Default to scanning along x
                                        appendPosition = lambda  xStg, yStg: positions.append(xStg)
                                    ### Move stage
                                    self.parameters.stage.move_at_velocity(vx, vy)
                                    ### Acquire until endpoint is reached
                                    voltages = []
                                    while continueCondition(xStg, yStg):
                                        # startPos = timer()
                                        (xStg, yStg) = self.parameters.stage.get_position()
                                        # print(timer()-startPos)
                                        ### Acquire
                                        measurements = multipleAI.acquire(sn)
                                        # print(measurements)
                                        ### Append data
                                        voltages.append(measurements)
                                        appendPosition(xStg, yStg)
                                    ### Stop stage at end of line
                                    # self.parameters.stage.move_at_velocity(0, 0)
                                    self.parameters.stage.stop_smoothly()
                                    while int(self.parameters.stage.busy()) > 0:
                                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
                                    ### Format scan line voltages
                                    avgVoltages = []
                                    for m in voltages:
                                        if sn > 1:
                                            liR = 0
                                            for liX, liY in zip(m[0], m[1]):
                                                liR += np.sqrt(np.power(liX, 2) +
                                                    np.power(liY, 2))
                                            liR = liR/sn
                                        else:
                                            liX = m[0]
                                            liY = m[1]
                                            liR = np.sqrt(np.power(liX, 2) +
                                                np.power(liY, 2))
                                        avgVoltages.append(liR)
                                    ### Append scan line voltages
                                    self.parameters.data.Vtemp[dataIndexPattern][dataIndexWl].append(np.array(avgVoltages))
                                    ### Append scan line positions according to scan direction
                                    if vx == 0:
                                        self.parameters.data.Xtemp[dataIndexPattern][dataIndexWl].append(self.parameters.data.X[dataIndexPattern])
                                        self.parameters.data.Ytemp[dataIndexPattern][dataIndexWl].append(np.array(positions))
                                    else:
                                        self.parameters.data.Xtemp[dataIndexPattern][dataIndexWl].append(np.array(positions))
                                        self.parameters.data.Ytemp[dataIndexPattern][dataIndexWl].append(self.parameters.data.Y[dataIndexPattern])
                                ### Emit ending position
                                (xStg, yStg) = self.parameters.stage.get_position()
                                self.stageMoved.emit(xStg, yStg)
                        except Exception as exc:
                            self.parameters.stage.stop_smoothly()
                            print('Scan did not complete:\n{}'.format(exc))
                            print('Partial data may still be usable.')
                    ### Clear acquisition task
                    multipleAI.clear_task()
                    ### Increment pattern-counting index
                    dataIndexPattern += 1
                ### Format data
                try:
                    for iv, (v, sd) in enumerate(zip(self.parameters.data.Vtemp,
                    self.parameters.scanDir)):
                        for iw, w in enumerate(self.parameters.data.W[iv]):
                            ### Determine maximum number of rows for voltage matrix
                            lineLengths = []
                            for vr in v[iw]:
                                lineLengths.append(len(vr))
                            scanLineLength = max(lineLengths)
                            scanLineNumber = len(v[iw])
                            ### Write wavelength or wavenumber string for file names
                            if self.parameters.units in ['invcm']:
                                wStr = 'wm-{:05.0f}invcm'.format(w)
                            else:
                                wStr = 'wl-{:02.3f}um'.format(w)
                            ### Save raw and formatted voltages, according to scan direction
                            if sd in ['y']:
                                ### Open file for raw positions in binary mode
                                rawPositionsFileName = 'scan{:03.0f}_{}{}'.format(
                                    iv + 1,
                                    wStr,
                                    defaults.DEF_FILENAME_SCAN_IMAG_Y_RAW)
                                rawPositionsFile = open(rawPositionsFileName,'ab')
                                ### Open file for raw voltage data in binary mode
                                rawVoltageFileName = 'scan{:03.0f}_{}{}'.format(
                                    iv + 1,
                                    wStr,
                                    defaults.DEF_FILENAME_SCAN_IMAG_V_Y_RAW)
                                rawVoltageFile = open(rawVoltageFileName,'ab')
                                ### Format and save data
                                self.parameters.data.Xcont[iv][iw] = np.transpose(self.parameters.data.X)
                                Y = np.zeros((scanLineLength, 1))
                                for iy, y in enumerate(self.parameters.data.Ytemp[iv][iw][0]):
                                    Y[iy] = y
                                self.parameters.data.Ycont[iv][iw] = Y
                                V = np.zeros((scanLineNumber, scanLineLength))
                                for ix, vr in enumerate(v[iw]):
                                    ### Save this line of raw voltage data
                                    positionLine = self.parameters.data.Ytemp[iv][iw][ix]
                                    positionLine = np.transpose(positionLine[:,None])
                                    np.savetxt(rawPositionsFile, positionLine)
                                    ### Save this line of raw voltage data
                                    np.savetxt(rawVoltageFile, np.transpose(vr))
                                    ### Calculate line length difference from max
                                    lengthOffset = scanLineLength - len(vr)
                                    for iy, vPoint in enumerate(vr):
                                        ### Pattern changes direction every line
                                        ### Invert for odd indices
                                        if ix % 2 == 0:
                                            V[ix][iy] = vPoint
                                        else:
                                            iyInv = scanLineLength - iy - 1 - lengthOffset
                                            V[ix][iyInv] = vPoint
                                rawVoltageFile.close()
                                rawPositionsFile.close()
                            else:
                                ### Open file for raw positions in binary mode
                                rawPositionsFileName = 'scan{:03.0f}_{}{}'.format(
                                    iv + 1,
                                    wStr,
                                    defaults.DEF_FILENAME_SCAN_IMAG_X_RAW)
                                rawPositionsFile = open(rawPositionsFileName,'ab')
                                ### Open file for raw voltage data in binary mode
                                rawVoltageFileName = 'scan{:03.0f}_{}{}'.format(
                                    iv + 1,
                                    wStr,
                                    defaults.DEF_FILENAME_SCAN_IMAG_V_X_RAW)
                                rawVoltageFile = open(rawVoltageFileName,'ab')
                                X = np.zeros((scanLineLength, 1))
                                for ix, x in enumerate(self.parameters.data.Xtemp[iv][iw][0]):
                                    X[ix] = x
                                self.parameters.data.Xcont[iv][iw] = X
                                self.parameters.data.Ycont[iv][iw] = np.transpose(self.parameters.data.Y)
                                V = np.zeros((scanLineLength, scanLineNumber))
                                for iy, vr in enumerate(v[iw]):
                                    ### Save this line of raw voltage data
                                    positionLine = self.parameters.data.Xtemp[iv][iw][iy]
                                    positionLine = np.transpose(positionLine[:,None])
                                    np.savetxt(rawPositionsFile, positionLine)
                                    ### Save this line of raw voltage data
                                    np.savetxt(rawVoltageFile, np.transpose(vr))
                                    ### Calculate line length difference from max
                                    lengthOffset = scanLineLength - len(vr)
                                    for ix, vPoint in enumerate(vr):
                                        ### Pattern changes direction every line
                                        ### Invert for odd indices
                                        if iy % 2 == 0:
                                            V[ix][iy] = vPoint
                                        else:
                                            ixInv = scanLineLength - ix - 1 - lengthOffset
                                            V[ixInv][iy] = vPoint
                                rawVoltageFile.close()
                                rawPositionsFile.close()
                            self.parameters.data.V[iv][iw] = V
                            ### Save data for this pattern and wavelength
                            ### Save x/y position vectors
                            np.savetxt('scan{:03.0f}_{}{}'.format(
                                iv + 1,
                                wStr,
                                defaults.DEF_FILENAME_SCAN_IMAG_X),
                                self.parameters.data.Xcont[iv][iw])
                            np.savetxt('scan{:03.0f}_{}{}'.format(
                                iv + 1,
                                wStr,
                                defaults.DEF_FILENAME_SCAN_IMAG_Y),
                                self.parameters.data.Ycont[iv][iw])
                            ### Save voltage matrix
                            np.savetxt('scan{:03.0f}_{}{}'.format(
                                iv + 1,
                                wStr,
                                defaults.DEF_FILENAME_SCAN_IMAG_V),
                                self.parameters.data.V[iv][iw])
                            ### Save raw positions for scanning axis


                except Exception as exc:
                    print('Data formatting did not complete:\n{}'.format(exc))
                    print('Data was not saved.')
            case 'snakeScan':
                '''
                The followings are new functions implemented by Po-Ting Shen
                '''
                print('Not implemented.')
                return []
            case _:
                print('Invalid scan mode selected.')
                return []
        endRun = timer()
        ### Return to experiment folder
        os.chdir(currentDir)
        print('Scan complete (%.3f s).' % (endRun-startRun))
        logFile = open(defaults.LOG_FILENAME, 'a')
        logFile.write('Acquisition time: {:.1f} s.\n'.format(endRun-startRun))
        logFile.write('\n')
        logFile.close()
        # '''Save data as text file'''
        # currentDir = os.getcwd()
        # if platform.system() == 'Windows':
        #     currentDirSplit = currentDir.split('\\')
        # else:
        #     currentDirSplit = currentDir.split('/')
        # currentFolder = currentDirSplit[-1]
        # np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME_XY), data)
        return self.parameters.data


class snakeScan(imagingScan):

    status_bar_msg = pyqtSignal(str)

    def __init__(self):
        super().__init__()
    '''
    ***Inherit run(), no need to change it
    '''
    def scan(self):
        '''
        Overwrite scan(). This is the snakescan routine that
        will be called in run().
        Run snakescan imaging experiment and output data.
        '''


        ### Prepare to save data
        rootDir = os.getcwd()
        # if platform.system() == 'Windows':
        #     currentDirSplit = currentDir.split('\\')
        # else:
        #     currentDirSplit = currentDir.split('/')
        scanImagDir = os.path.join(rootDir, defaults.DEF_SNAKE_SCAN_SUBFOLDER)
        os.mkdir(scanImagDir)
        os.chdir(scanImagDir)
        ### Preamble
        print('Scan started ...')

        '''
        Refer to prior_api_test.py for snake scan prototypes.
        '''
        ### Iterate over scan patterns
        for idx, pattern in enumerate(self.parameters.patterns):
            '''
            The nested structures, each line is at the same tier:
            pattern, wlwnList, data.W[idx], data.V[idx]...
            '''
            ### Make a folder for each pattern
            patternDir = os.path.join(scanImagDir,'pattern'+str(idx))
            os.mkdir(patternDir)
            os.chdir(patternDir)

            ### Go to origin of each pattern, set the position to zero
            self.parameters.stage.goto(self.parameters.xParameters[idx][0], self.parameters.yParameters[idx][0])
            while int(self.parameters.stage.busy()) > 0:
                time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
            ### This is to rezero the stage encoders.
            self.parameters.stage.set_position(x = 0 , y = 0)
            while int(self.parameters.stage.busy()) > 0:
                time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
            ### Iterate over wavelength/wavenumber in wlwnList
            for jdx, wlwn in enumerate(self.parameters.wlwnList[idx]):
                '''
                Tune laser to <wlwn>.
                '''
                self.parameters.laser.tune(qcl = whichQCL(wlwn,self.parameters.units),
                                           wl = wlwn,
                                           wlUnits = self.parameters.units)




                ###for autofocusing after tuning to each discrete frequency
                ###note: need to adjust the position, since the original x and y starting position has been set to zero
                xOrig = self.parameters.xParameters[idx][0]
                yOrig = self.parameters.yParameters[idx][0]

                # --- Run autofocus before any scan pattern or stage movement ---
                if self.parameters.pi_scanner.autofocus_on_imaging:
                    if hasattr(self.parameters, 'pi_scanner_widget'):
                        #store the original autofocus stage position (target_x, target_y)
                        target_x_orig = self.parameters.pi_scanner.target_x
                        target_y_orig = self.parameters.pi_scanner.target_y
                        #calculate the shifted positions, due to stage zeroing
                        target_x_modified = self.parameters.pi_scanner.target_x - xOrig
                        target_y_modified = self.parameters.pi_scanner.target_y - yOrig
                        #set the new positions to the widget (note this is connected to pi_scanner target_x and target_y)
                        self.parameters.pi_scanner_widget.set_target_x_signal.emit(str(target_x_modified))
                        self.parameters.pi_scanner_widget.set_target_y_signal.emit(str(target_y_modified))
                        #do the actual autofocus, which is in the scanner_widget
                        self.parameters.pi_scanner_widget.autofocus()
                        #then reset the target_x and target_y values
                        self.parameters.pi_scanner.target_x = target_x_orig
                        self.parameters.pi_scanner.target_y = target_y_orig
                        self.parameters.pi_scanner_widget.set_target_x_signal.emit(str(target_x_orig))
                        self.parameters.pi_scanner_widget.set_target_y_signal.emit(str(target_y_orig))

                    else:
                        self.parameters.pi_scanner_widget = piScanner_widget(self.parameters.pi_scanner, stage_instance=self.parameters.stage)

                        #store the original autofocus stage position (target_x, target_y)
                        target_x_orig = self.parameters.pi_scanner.target_x
                        target_y_orig = self.parameters.pi_scanner.target_y
                        #calculate the shifted positions, due to stage zeroing
                        target_x_modified = self.parameters.pi_scanner.target_x - xOrig
                        target_y_modified = self.parameters.pi_scanner.target_y - yOrig
                        #set the new positions to the widget (note this is connected to pi_scanner target_x and target_y)
                        self.parameters.pi_scanner_widget.set_target_x_signal.emit(str(target_x_modified))
                        self.parameters.pi_scanner_widget.set_target_y_signal.emit(str(target_y_modified))
                        #do the actual autofocus, which is in the scanner_widget
                        self.parameters.pi_scanner_widget.autofocus()
                        #then reset the target_x and target_y values
                        self.parameters.pi_scanner.target_x = target_x_orig
                        self.parameters.pi_scanner.target_y = target_y_orig
                        self.parameters.pi_scanner_widget.set_target_x_signal.emit(str(target_x_orig))
                        self.parameters.pi_scanner_widget.set_target_y_signal.emit(str(target_y_orig))

                        self.parameters.pi_scanner_widget.deleteLater()


                ### Setup, start triggered acquisition task
                multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
                multipleAI.configure_triggered(defaults.PCI_SNAKE_TRIG, self.parameters.sampleNumbers[idx], self.parameters.sampleRates[idx])
                #multipleAI.stream_to_disk()
                multipleAI.start_task()

                ### Move the stage position to (xOrig,yOrig)
                ### Change this
                ### Start snake scan!

                self.parameters.stage.goto(x = 0, y = 0)
                while int(self.parameters.stage.busy()) > 0:
                    time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

                self.parameters.stage.set_speed(self.parameters.speeds[idx])
                startRun = timer()

                ### Make some local variables to make the loop readable
                paths = pattern
                trigIndent = defaults.SNAKE_TRIG_INDENT
                stepSize = paths[0]['dX']
                xPixels = paths[0]['M']
                sampleNumber = self.parameters.sampleNumbers[idx]
                units = self.parameters.units

                for path in paths:
                    #print('Scanning line ' + str(2*path['i']+1) + ' (forward)', flush=True)
                    self.status_bar_msg.emit('Scan #' + str(idx)+ ': Emitting ' + str(wlwn) + ' '+ units + '...'
                                             + ' Scanning line ' + str(2*path['i']+1)
                                             + '/' + str(2*len(paths)) + ' (forward)')
                    self.parameters.stage.goto(int(path['X0']),int(path['Y0']))
                    self.parameters.stage.arm_trigger(F = hld117.HLD117_TRIG_RES*trigIndent, D = hld117.HLD117_TRIG_RES*stepSize, A = 'X', N = xPixels, P = 'P' , W = 1)
                    self.parameters.stage.goto(int(path['X1']),int(path['Y0']))
                    while int(self.parameters.stage.busy()) > 0:
                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

                    data_forward = multipleAI.read_line(xPixels*sampleNumber)
                    self.parameters.data.dataCh1[idx][jdx].append(data_forward[0])
                    self.parameters.data.dataCh2[idx][jdx].append(data_forward[1])


                    self.parameters.stage.goto(int(path['X1']),int(path['Y1']))
                    #print('Scanning line ' + str(2*path['i']+2) + ' (backward)', flush=True)
                    self.status_bar_msg.emit('Scan #' + str(idx)+ ': Emitting ' + str(wlwn) + ' '+ units + '...'
                                             + ' Scanning line ' + str(2*path['i']+2)
                                             + '/' + str(2*len(paths)) +' (backward)')
                    self.parameters.stage.arm_trigger(F = hld117.HLD117_TRIG_RES*(xPixels*stepSize + path['drift']), D = -hld117.HLD117_TRIG_RES*stepSize, A = 'X', N = xPixels, P = 'P' , W = 1)
                    self.parameters.stage.goto(int(path['X0'] + path['drift']),int(path['Y1']))
                    while int(self.parameters.stage.busy()) > 0:
                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

                    data_backward = multipleAI.read_line(xPixels*sampleNumber)
                    self.parameters.data.dataCh1[idx][jdx].append(data_backward[0])
                    self.parameters.data.dataCh2[idx][jdx].append(data_backward[1])

                endRun = timer()
                print('Scan complete (%.3f s).' % (endRun-startRun))

                ### End Snake scan

                ### Stop, clear triggered acquisition task
                multipleAI.stop_task() # Stop acquisition task
                multipleAI.clear_task()

                ### Go back to the origin of the pattern
                self.parameters.stage.set_speed(defaults.HLD117_MAX_SPEED)
                self.parameters.stage.goto(x = 0, y = 0)
                while int(self.parameters.stage.busy()) > 0:
                    time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

                ### Save csv for each <wlwn>
                self.parameters.data.finishSnakeScan(pattern_idx = idx, wlwn_idx = jdx,
                                                     wlUnits = self.parameters.units,
                                                     filepath = patternDir)
                ### Save X, Y coordinates of the scan for GUI
                xOrig = self.parameters.xParameters[idx][0]
                yOrig = self.parameters.yParameters[idx][0]
                xPixelRes = self.parameters.xParameters[idx][1]
                yPixelRes = self.parameters.yParameters[idx][1]
                xPixelNums = self.parameters.xParameters[idx][2]
                yPixelNums = self.parameters.yParameters[idx][2]
                self.parameters.data.X[idx][jdx] = list(np.linspace(xOrig + trigIndent, xOrig + trigIndent + xPixelNums*xPixelRes, xPixelNums))
                self.parameters.data.Y[idx][jdx] = list(np.linspace(yOrig + trigIndent, yOrig + trigIndent - yPixelNums*yPixelRes, yPixelNums))

            ### Reset the stage coordinates for each pattern
            self.parameters.stage.set_position(self.parameters.xParameters[idx][0],
                                                   self.parameters.yParameters[idx][0])
            while int(self.parameters.stage.busy()) > 0:
                time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

        ### Format all the data for GUI plots
        self.parameters.data.guiFormat()
        ### Reset the directory for screenshot.png
        os.chdir(rootDir)
        ### Save all the data in self.parameters.data.snakeScans[idx][jdx] in one .mat


        ### Disable laser for safety
        self.parameters.laser.disable()
        return self.parameters.data

class repeatSnakeScan(imagingScan):

    status_bar_msg = pyqtSignal(str)

    def __init__(self):
        super().__init__()
    '''
    ***Inherit run(), no need to change it
    '''
    def writeTimeStamps(self):
        '''
        Helper: Save time stamps to .csv
        '''
        data = self.parameters.timeStamps
        # extract keys and values from dictionary
        keys = list(data.keys())
        values = list(data.values())

        # write to CSV file
        with open('time_stamps.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(keys)  # write header
            writer.writerows(zip(*values))  # write data rows

    def scan(self):
        '''
        Overwrite scan(). This is the snakescan routine that
        will be called in run().
        Repeat snakescan imaging on scan 0 and output data.
        Note to self: Copied from snakeScan. Not changed yet. (08/07/23)
        '''

        ### Prepare to save data
        rootDir = os.getcwd()
        # if platform.system() == 'Windows':
        #     currentDirSplit = currentDir.split('\\')
        # else:
        #     currentDirSplit = currentDir.split('/')
        scanImagDir = os.path.join(rootDir, defaults.DEF_SNAKE_SCAN_SUBFOLDER)
        os.mkdir(scanImagDir)
        os.chdir(scanImagDir)
        ### Preamble
        print('Scan started ...')

        '''
        Refer to prior_api_test.py for snake scan prototypes.
        '''
        ### Go to origin of scan 0, set the position to zero
        self.parameters.stage.goto(self.parameters.xParameters[0][0], self.parameters.yParameters[0][0])
        while int(self.parameters.stage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
        ### This is to rezero the stage encoders.
        self.parameters.stage.set_position(x = 0 , y = 0)
        while int(self.parameters.stage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

        ### Iterate over scan patterns (repetitions)
        for idx, pattern in enumerate(self.parameters.patterns):
            '''
            The nested structures, each line is at the same tier:
            pattern, wlwnList, data.W[idx], data.V[idx]...
            '''
            ### Make a folder for each pattern
            patternDir = os.path.join(scanImagDir,'pattern'+str(idx))
            os.mkdir(patternDir)
            os.chdir(patternDir)


            ### Iterate over wavelength/wavenumber in wlwnList
            for jdx, wlwn in enumerate(self.parameters.wlwnList[idx]):
                '''
                Tune laser to <wlwn>.
                '''
                ###for autofocusing after tuning to each discrete frequency
                self.parameters.laser.tune(qcl = whichQCL(wlwn,self.parameters.units),
                                           wl = wlwn,
                                           wlUnits = self.parameters.units)



                ###note: need to adjust the position, since the original x and y starting position has been set to zero
                xOrig = self.parameters.xParameters[idx][0]
                yOrig = self.parameters.yParameters[idx][0]

                # --- Run autofocus before any scan pattern or stage movement ---
                if self.parameters.pi_scanner.autofocus_on_imaging:
                    if hasattr(self.parameters, 'pi_scanner_widget'):
                        #store the original autofocus stage position (target_x, target_y)
                        target_x_orig = self.parameters.pi_scanner.target_x
                        target_y_orig = self.parameters.pi_scanner.target_y
                        #calculate the shifted positions, due to stage zeroing
                        target_x_modified = self.parameters.pi_scanner.target_x - xOrig
                        target_y_modified = self.parameters.pi_scanner.target_y - yOrig
                        #set the new positions to the widget (note this is connected to pi_scanner target_x and target_y)
                        self.parameters.pi_scanner_widget.set_target_x_signal.emit(str(target_x_modified))
                        self.parameters.pi_scanner_widget.set_target_y_signal.emit(str(target_y_modified))
                        #do the actual autofocus, which is in the scanner_widget
                        self.parameters.pi_scanner_widget.autofocus()
                        #then reset the target_x and target_y values
                        self.parameters.pi_scanner.target_x = target_x_orig
                        self.parameters.pi_scanner.target_y = target_y_orig
                        self.parameters.pi_scanner_widget.set_target_x_signal.emit(str(target_x_orig))
                        self.parameters.pi_scanner_widget.set_target_y_signal.emit(str(target_y_orig))
                    else:
                        self.parameters.pi_scanner_widget = piScanner_widget(self.parameters.pi_scanner, stage_instance=self.parameters.stage)

                        #store the original autofocus stage position (target_x, target_y)
                        target_x_orig = self.parameters.pi_scanner.target_x
                        target_y_orig = self.parameters.pi_scanner.target_y
                        #calculate the shifted positions, due to stage zeroing
                        target_x_modified = self.parameters.pi_scanner.target_x - xOrig
                        target_y_modified = self.parameters.pi_scanner.target_y - yOrig
                        #set the new positions to the widget (note this is connected to pi_scanner target_x and target_y)
                        self.parameters.pi_scanner_widget.set_target_x_signal.emit(str(target_x_modified))
                        self.parameters.pi_scanner_widget.set_target_y_signal.emit(str(target_y_modified))
                        #do the actual autofocus, which is in the scanner_widget
                        self.parameters.pi_scanner_widget.autofocus()
                        #then reset the target_x and target_y values
                        self.parameters.pi_scanner.target_x = target_x_orig
                        self.parameters.pi_scanner.target_y = target_y_orig
                        self.parameters.pi_scanner_widget.set_target_x_signal.emit(str(target_x_orig))
                        self.parameters.pi_scanner_widget.set_target_y_signal.emit(str(target_y_orig))

                        self.parameters.pi_scanner_widget.deleteLater()


                ### Setup, start triggered acquisition task
                multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
                multipleAI.configure_triggered(defaults.PCI_SNAKE_TRIG, self.parameters.sampleNumbers[idx], self.parameters.sampleRates[idx])
                #multipleAI.stream_to_disk()
                multipleAI.start_task()

                ### Move the stage position to (xOrig,yOrig)
                ### Change this
                ### Start snake scan!

                self.parameters.stage.goto(x = 0, y = 0)
                while int(self.parameters.stage.busy()) > 0:
                    time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

                self.parameters.stage.set_speed(self.parameters.speeds[idx])
                startRun = timer()

                ### Make some local variables to make the loop readable
                paths = pattern
                trigIndent = defaults.SNAKE_TRIG_INDENT
                stepSize = paths[0]['dX']
                xPixels = paths[0]['M']
                sampleNumber = self.parameters.sampleNumbers[idx]
                units = self.parameters.units

                for path in paths:
                    #print('Scanning line ' + str(2*path['i']+1) + ' (forward)', flush=True)
                    self.status_bar_msg.emit('Scan #' + str(idx)+ ': Emitting ' + str(wlwn) + ' '+ units + '...'
                                             + ' Scanning line ' + str(2*path['i']+1)
                                             + '/' + str(2*len(paths)) + ' (forward)')
                    self.parameters.stage.goto(int(path['X0']),int(path['Y0']))
                    self.parameters.stage.arm_trigger(F = hld117.HLD117_TRIG_RES*trigIndent, D = hld117.HLD117_TRIG_RES*stepSize, A = 'X', N = xPixels, P = 'P' , W = 1)
                    self.parameters.stage.goto(int(path['X1']),int(path['Y0']))
                    while int(self.parameters.stage.busy()) > 0:
                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

                    data_forward = multipleAI.read_line(xPixels*sampleNumber)
                    self.parameters.data.dataCh1[idx][jdx].append(data_forward[0])
                    self.parameters.data.dataCh2[idx][jdx].append(data_forward[1])


                    self.parameters.stage.goto(int(path['X1']),int(path['Y1']))
                    #print('Scanning line ' + str(2*path['i']+2) + ' (backward)', flush=True)
                    self.status_bar_msg.emit('Scan #' + str(idx)+ ': Emitting ' + str(wlwn) + ' '+ units + '...'
                                             + ' Scanning line ' + str(2*path['i']+2)
                                             + '/' + str(2*len(paths)) +' (backward)')
                    self.parameters.stage.arm_trigger(F = hld117.HLD117_TRIG_RES*(xPixels*stepSize + path['drift']), D = -hld117.HLD117_TRIG_RES*stepSize, A = 'X', N = xPixels, P = 'P' , W = 1)
                    self.parameters.stage.goto(int(path['X0'] + path['drift']),int(path['Y1']))
                    while int(self.parameters.stage.busy()) > 0:
                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

                    data_backward = multipleAI.read_line(xPixels*sampleNumber)
                    self.parameters.data.dataCh1[idx][jdx].append(data_backward[0])
                    self.parameters.data.dataCh2[idx][jdx].append(data_backward[1])

                endRun = timer()
                print('Scan complete (%.3f s).' % (endRun-startRun))

                ### Generate timestamp for self.parameters.timeStamps

                timeStamp = int(time.time())
                key = '{}'.format(wlwn)
                self.parameters.timeStamps[key].append(timeStamp)

                ### End Snake scan

                ### Stop, clear triggered acquisition task
                multipleAI.stop_task() # Stop acquisition task
                multipleAI.clear_task()

                ### Go back to the origin of the pattern
                self.parameters.stage.set_speed(defaults.HLD117_MAX_SPEED)
                self.parameters.stage.goto(x = 0, y = 0)
                while int(self.parameters.stage.busy()) > 0:
                    time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

                ### Save csv for each <wlwn>
                self.parameters.data.finishSnakeScan(pattern_idx = idx, wlwn_idx = jdx,
                                                     wlUnits = self.parameters.units,
                                                     filepath = patternDir)
                ### Save X, Y coordinates of the scan for GUI
                xOrig = self.parameters.xParameters[idx][0]
                yOrig = self.parameters.yParameters[idx][0]
                xPixelRes = self.parameters.xParameters[idx][1]
                yPixelRes = self.parameters.yParameters[idx][1]
                xPixelNums = self.parameters.xParameters[idx][2]
                yPixelNums = self.parameters.yParameters[idx][2]
                self.parameters.data.X[idx][jdx] = list(np.linspace(xOrig + trigIndent, xOrig + trigIndent + xPixelNums*xPixelRes, xPixelNums))
                self.parameters.data.Y[idx][jdx] = list(np.linspace(yOrig + trigIndent, yOrig + trigIndent - yPixelNums*yPixelRes, yPixelNums))

        ### Reset the stage coordinates after the completion
        self.parameters.stage.set_position(self.parameters.xParameters[0][0],
                                                   self.parameters.yParameters[0][0])
        while int(self.parameters.stage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

        ### Format all the data for GUI plots
        self.parameters.data.guiFormat()
        ### Reset the directory for screenshot.png, save all data to .mat
        # and timeStamps to .csv
        os.chdir(rootDir)
        self.parameters.data.saveMat(wlUnits = self.parameters.units)
        self.writeTimeStamps()

        ### Disable laser for safety
        self.parameters.laser.disable()
        return self.parameters.data





