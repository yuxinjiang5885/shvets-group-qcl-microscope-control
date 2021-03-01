'''
routines
Giovanni Sartorello (srtgnn@gmail.com)
Experiment control classes for MIRcat spectral scan UI
Python 3.8.3 on Windows 10
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
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigCanvas
from matplotlib.figure import Figure
from instruments.daylight.MIRcatSDKConstants import MIRcatSDK_UNITS_CM1, MIRcatSDK_UNITS_MICRONS

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

class experiment(): # Directory management and multiple acquisitions

    def __init__(self):
        self.laser = [] # Placeholder value
        self.latestDir = 0 # Latest experiment directory, placeholder value
        self.notes = [] # Placeholder value
        self.qcl = [] # QCL modules to be used, placeholder value
        self.ranges = [] # Placeholder value
        self.reference = np.zeros((1, 2)) # Placeholder value
        self.sampleNumber = defaults.DEF_SAMPLES
        self.sampleRate = defaults.DEF_SAMPLERATE
        self.speed = 1 # Placeholder value, no unit
        self.step = 1 # Placeholder value, no unit
        self.sweeping = True # By default, use the sweep routine
        self.sweepLimits = [] # Placeholder value
        self.units = 'um' # By default, wavelengths in micrometers
        self.useRef = False # By default, do not use reference

    def repeat(self, GUIInstance):
        '''
        Run the same experiment again. Saves time compared to "run".
        Ineffective if "run" has not been used before for a given instance.
        '''
        ### Invert direction
        self.sweepLimits.reverse()
        self.ranges.reverse()
        self.qcl.reverse()
        for x, (l, r) in enumerate(zip(self.sweepLimits, self.ranges)):
            l.reverse()
            r.reverse()
        ### Go to main experiment directory
        workDir = defaults.DEF_DATA_DIRECTORY
        os.chdir(workDir)
        ### Get latest experiment number from previously created folder
        # print(self.latestDir) # Troubleshooting
        oldExpNo = int(self.latestDir[-3:])
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
        if self.sweeping:
            data = self.sweep()
        else: # Default to step-and-measure
            data = self.scan()
        if GUIInstance.repeatShowAction.isChecked():
            ### Reverse data for plotting
            if self.units == 'invcm':
                # plotData = np.flip(data, 0)
                plotData = data
            else:
                plotData = data
            ### Paint plots
            GUIInstance.spectrumCanvas.clear_plots()
            GUIInstance.spectrumCanvasT.clear_plots()
            # GUIInstance.spectrumCanvas.flush_events()
            try:
                GUIInstance.spectrumCanvas.axes.set_xlim(plotData[0, 0], plotData[-1, 0])
                # GUIInstance.spectrumCanvas.axes.set_ylim(min(data[:, 1]), max(data[-1, 0]))
                GUIInstance.spectrumCanvas.plot_line(plotData[:, 0], plotData[:, 3])
                if self.useRef:
                    if self.units == 'invcm':
                        plotData = np.flip(data, 0)
                        plotRef = np.flip(self.reference, 0)
                    else:
                        plotData = data
                        plotRef = self.reference
                    # GUIInstance.spectrumCanvasT.flush_events()
                    GUIInstance.spectrumCanvasT.axes.set_xlim(plotData[0, 0], plotData[-1, 0])
                    GUIInstance.spectrumCanvasT.plot_line(plotData[:, 0],
                                                        plotData[:, 3]/plotRef[:, 3])
            except Exception as exc:
                print('Failed to plot data:\n{}'.format(exc))
        return [data, self]

    def run(self, GUIInstance, wlUnits='um'):
        '''
        Run experiment. Replaces "start" routine. Works with "sweep".
        :param GUIInstance: GUI instance from the UI program.
        :param wlUnits: 'um' (micrometers) or 'invcm' (inverse cm).
        '''
        ### Get laser instance
        self.laser = GUIInstance.laser
        ### Make sure laser is armed
        if not GUIInstance.btn['Arm'][0].isChecked():
            print('Laser is not armed.')
            GUIInstance.btn['Start'][0].setChecked(False)
            # GUIInstance.btn['Stop'][0].setChecked(False)
            GUIInstance.btn['Sweep'][0].setChecked(False)
            return [[], self]
        ### Get experiment notes, if any
        self.notes = GUIInstance.notes.toPlainText()
        ### Check use of reference
        if GUIInstance.btn['RefEnable'][0].isChecked():
            self.useRef = True
        ### Load reference
        if self.useRef:
            try:
                dataPath = GUIInstance.refDir # Latest experiment directory
                dataPathParts = os.path.split(dataPath)
                fileName = '{}{}'.format(dataPathParts[-1], defaults.DEF_FILENAME)
                filePath = os.path.join(dataPath, fileName)
                self.reference = np.loadtxt(filePath)
            except Exception as exc:
                print('Failed to load reference:\n{}'.format(exc))
        ### Get scan parameters
        self.sweeping = GUIInstance.btn['Sweep'][0].isChecked()
        start = float(GUIInstance.inputField['WlStart'][0].text())
        end = float(GUIInstance.inputField['WlEnd'][0].text())
        self.step = float(GUIInstance.inputField['WlStep'][0].text())
        self.sampleNumber = int(GUIInstance.inputField['SamplesPerWl'][0].text())
        self.sampleRate = int(GUIInstance.inputField['SamplingRate'][0].text())
        self.speed = float(GUIInstance.inputField['Speed'][0].text())
        if GUIInstance.wlUnits == 'invcm':
            self.units = 'invcm'
        else: # Default to micrometers
            self.units = 'um'
        ### Check inputs
        if start == end: # Requested limits are equal
            print('Limits cannot be equal.')
            GUIInstance.btn['Start'][0].setChecked(False)
            # GUIInstance.btn['Stop'][0].setChecked(False)
            GUIInstance.btn['Sweep'][0].setChecked(False)
            return [[], self]
        ### Make "raw" range with requested values
        if start > end:
            start, end = end, start
        rawRange = np.arange(start, end, self.step)
        if len(rawRange) < 1: # Requested limits are out of QCL bounds
            print('Cannot sweep requested range.')
            GUIInstance.btn['Start'][0].setChecked(False)
            # GUIInstance.btn['Stop'][0].setChecked(False)
            GUIInstance.btn['Sweep'][0].setChecked(False)
            return [[], self]
        ### Make a separate range for each QCL
        ranges = [[], [], [], []] # Store allowed wavelengths/numbers per QCL
        if self.units == 'invcm':
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
                self.qcl.append(x+1) # QCLs are numbered 1--4
        ### Compile QCL ranges in class variable, if not empty
        for r in ranges:
            if len(r) > 0: # If not empty
                self.ranges.append(r)
        ### Compile sweep ranges, adding margins
        if self.sweeping:
            if self.units == 'invcm':
                for r in self.ranges:
                    r.reverse() # Default order is from higher energy down
                    self.sweepLimits.append([r[0] + WN_MAR_INVCM,
                                             r[-1] - WN_MAR_INVCM])
            else: # Default to micrometers
                for r in self.ranges:
                    self.sweepLimits.append([r[0] - WL_MAR_UM,
                                             r[-1] + WL_MAR_UM])
        # print(self.ranges)
        # print(self.sweepLimits)
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
        self.latestDir = expDir
        ### Save experiment notes to file
        if not len(self.notes) == 0:
            noteFile = open('notes.txt', 'w')
            noteFile.write(self.notes)
            noteFile.close()
        ### Write parameters to log
        logFile = open('experiment.log', 'w')
        logFile.write('QCL/Microscope experiment log\n')
        timeStr = time.strftime('%Y-%m-%d %H:%M:%S\n')
        logFile.write('{}'.format(timeStr))
        logFile.write('No. {:.0f}\n'.format(newExpNo))
        logFile.write('\n')
        for qclNo in self.qcl:
            qclCurr = self.laser.get_current(qclNo)
            qclRate = self.laser.get_pulse_rate(qclNo)
            qclWidth = self.laser.get_pulse_width(qclNo)
            logFile.write('QCL {:.0f}: {:.0f} mA, {:.0f} Hz, {:.0f} ns.\n'.format(
                                            qclNo, qclCurr, qclRate, qclWidth))
        logFile.write('\n')
        if self.sweepLimits:
            logFile.write('Type: sweep\n')
        else:
            logFile.write('Type: step-and-measure\n')
        logFile.write('\n')
        logFile.write('Target wavelengths/wavenumbers:\n')
        logFile.write('{}\n'.format(self.ranges))
        logFile.write('\n')
        logFile.write('Sweep limits:\n')
        logFile.write('{}\n'.format(self.sweepLimits))
        logFile.write('\n')
        logFile.close()
        ### Run a sweep or a step-and-measure scan
        data = []
        if self.sweeping:
            data = self.sweep()
        else: # Default to step-and-measure
            data = self.scan()
        ### Update QCL interface readings
        # GUIInstance.qcl(GUIInstance.activeQcl)
        # GUIInstance.update_qcl_reading(GUIInstance.activeQcl)
        ### Reverse data for plotting
        if self.units == 'invcm':
            # plotData = np.flip(data, 0)
            plotData = data
        else:
            plotData = data
        ### Paint plots
        GUIInstance.spectrumCanvas.clear_plots()
        GUIInstance.spectrumCanvasT.clear_plots()
        # GUIInstance.spectrumCanvas.flush_events()
        try:
            GUIInstance.spectrumCanvas.axes.set_xlim(plotData[0, 0], plotData[-1, 0])
            # GUIInstance.spectrumCanvas.axes.set_ylim(min(data[:, 1]), max(data[-1, 0]))
            GUIInstance.spectrumCanvas.plot_line(plotData[:, 0], plotData[:, 3])
            if self.useRef:
                if self.units == 'invcm':
                    plotData = np.flip(data, 0)
                    plotRef = np.flip(self.reference, 0)
                else:
                    plotData = data
                    plotRef = self.reference
                # GUIInstance.spectrumCanvasT.flush_events()
                GUIInstance.spectrumCanvasT.axes.set_xlim(plotData[0, 0], plotData[-1, 0])
                GUIInstance.spectrumCanvasT.plot_line(plotData[:, 0],
                                                      plotData[:, 3]/plotRef[:, 3])
        except Exception as exc:
            print('Failed to plot data:\n{}'.format(exc))
        ### Give current experiment number to UI instance
        GUIInstance.latestDir = expDir
        ### Save UI screenshot
        GUIInstance.repaint()
        GUIInstance.grab().save('screenshot.png', 'png')
        ### Uncheck UI buttons
        GUIInstance.btn['Start'][0].setChecked(False)
        # GUIInstance.btn['Stop'][0].setChecked(False)
        GUIInstance.btn['Sweep'][0].setChecked(False)
        return [data, self]

    def scan(self):
        '''Run a step-and measure scan.'''
        ### Preamble
        print('Scan started ...')
        print('One wavelength point per step, avg. of {:.0f} samples at {:.0f} Hz'
              .format(self.sampleNumber, self.sampleRate))
        startRun = timer()
        ### Setup acquisition
        multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
        multipleAI.configure(self.sampleNumber, self.sampleRate)
        ### Run multi-range scan
        numRanges = len(self.ranges)
        steps = 0
        voltages, wavelengths = [], []
        for x, r in enumerate(self.ranges):
            steps += len(r)
            wavelengths +=r
            qcl = self.qcl[x]
            print('Range {}/{}, using QCL module {}...'.format(
                                                           x+1, numRanges, qcl))
            ### Acquisition
            rangeVoltages = []
            try: # Failure here likely due to timeout because of skipped points
                for wl in r:
                    ### Tune
                    self.laser.tune(qcl, wl, self.units)
                    ### Acquire
                    rangeVoltages.append(multipleAI.acquire(self.sampleNumber))
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
                data[x, 1] = np.sum(v[0])/self.sampleNumber # Lock-in X
                data[x, 2] = np.sum(v[1])/self.sampleNumber # Lock-in Y
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
        ### Save data as text file
        currentDir = os.getcwd()
        if platform.system() == 'Windows':
            currentDirSplit = currentDir.split('\\')
        else:
            currentDirSplit = currentDir.split('/')
        currentFolder = currentDirSplit[-1]
        np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME), data)
        return data

    def sweep(self):
        '''
        Run a sweep using the MIRcat's built-in function.
        '''
        ### Preamble
        print('Sweep started ...')
        print('One wavelength point per step, avg. of {:.0f} samples at {:.0f} Hz'
              .format(self.sampleNumber, self.sampleRate))
        startRun = timer()
        ### Setup, start triggered acquisition task
        multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
        multipleAI.configure_triggered(defaults.PCI_TRIG,
                                       self.sampleNumber, self.sampleRate)
                                       ### Start task
        multipleAI.start_task()
        ### Run multi-range sweep
        numRanges = len(self.ranges)
        steps = 0
        voltages, wavelengths = [], []
        for x, (l, r) in enumerate(zip(self.sweepLimits, self.ranges)):
            steps += len(r)
            wavelengths +=r
            ### Print QCL module in use
            print('Range {}/{}, using QCL module {}...'.format(
                x+1, numRanges, self.qcl[x]))
            ### Set laser triggering (one TTL pulse per wl/wn) and start sweep
            print('Trigger: {:.2f} to {:.2f} {}, {:.2f} {} step.'.format(
                                r[0], r[-1], self.units, self.step, self.units))
            self.laser.set_wl_trigger_parameters(r[-1], r[0], self.step,
                                                                     self.units)
            ### Start sweep
            print('Sweep: {:.2f} to {:.2f} {}, {:.2f} {}/s.'.format(
                                l[0], l[-1],self.units, self.speed, self.units))
            self.laser.sweep_and_forget(l[0], l[-1], self.speed, self.units,
                                                                    self.qcl[x])
            ### Triggered acquisition
            rangeVoltages = []
            try: # Failure here likely due to timeout because of skipped points
                for x in range(0, len(r)):
                    rangeVoltages.append(multipleAI.acquire_fast(self.sampleNumber))
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
                data[x, 1] = np.sum(v[0])/self.sampleNumber # Lock-in X
                data[x, 2] = np.sum(v[1])/self.sampleNumber # Lock-in Y
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
        ### Save data as text file
        currentDir = os.getcwd()
        if platform.system() == 'Windows':
            currentDirSplit = currentDir.split('\\')
        else:
            currentDirSplit = currentDir.split('/')
        currentFolder = currentDirSplit[-1]
        np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME), data)
        return data
