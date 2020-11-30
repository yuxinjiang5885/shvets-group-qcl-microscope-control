'''
routines
Giovanni Sartorello (srtgnn@gmail.com)
Experiment control classes for MIRcat spectral scan UI
Version 1
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

    def repeat(self):
        '''
        Run the same experiment again. Saves time compared to "run".
        Ineffective if "run" has not been used before for a given instance.
        '''
        ### Go to main experiment directory
        workDir = defaults.DEF_DATA_DIRECTORY
        os.chdir(workDir)
        ### Get latest experiment number from previously created folder
        oldExpNo = int(self.latestdir[-3:])
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
        if not len(self.notes) == 0:
            noteFile = open('notes.txt', 'w')
            noteFile.write(self.notes)
            noteFile.close()
        ### Run a sweep or a step-and-measure scan
        if self.sweep:
            data = self.sweep()
        else: # Default to step-and-measure
            # data = self.scan() # Requires a new version of "scan"
            pass
        return 0

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
            GUIInstance.btn['Stop'][0].setChecked(False)
            GUIInstance.btn['Sweep'][0].setChecked(False)
            return
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
            GUIInstance.btn['Stop'][0].setChecked(False)
            GUIInstance.btn['Sweep'][0].setChecked(False)
            return
        ### Make "raw" range with requested values
        if start > end:
            start, end = end, start
        rawRange = np.arange(start, end, self.step)
        if len(rawRange) < 1: # Requested limits are out of QCL bounds
            print('Cannot sweep requested range.')
            GUIInstance.btn['Start'][0].setChecked(False)
            GUIInstance.btn['Stop'][0].setChecked(False)
            GUIInstance.btn['Sweep'][0].setChecked(False)
            return
        ### Make a separate range for each QCL
        ranges = [[], [], [], []] # Store allowed wavelengths/numbers per QCL
        if self.units == 'invcm':
            for wn in rawRange:
                if WN_NRANGE_QCL1[0] >= wn >= WN_NRANGE_QCL1[1]:
                    ranges[0].append(wn)
                elif WN_NRANGE_QCL2[0] >= wn >= WN_NRANGE_QCL2[1]:
                    ranges[1].append(wn)
                elif WN_NRANGE_QCL3[0] >= wn >= WN_NRANGE_QCL3[1]:
                    ranges[2].append(wn)
                elif WN_NRANGE_QCL4[0] >= wn >= WN_NRANGE_QCL4[1]:
                    ranges[3].append(wn)
        else: # Default to micrometers
            for wl in rawRange:
                if WL_NRANGE_QCL1[0] <= wl <= WL_NRANGE_QCL1[1]:
                    ranges[0].append(wl)
                elif WL_NRANGE_QCL2[0] <= wl <= WL_NRANGE_QCL2[1]:
                    ranges[1].append(wl)
                elif WL_NRANGE_QCL3[0] <= wl <= WL_NRANGE_QCL3[1]:
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
        if self.sweep:
            if self.units == 'invcm':
                for r in self.ranges:
                    self.sweepLimits.append((r[0] - WN_MAR_INVCM,
                                             r[-1] + WN_MAR_INVCM))
            else: # Default to micrometers
                for r in self.ranges:
                    self.sweepLimits.append((r[0] - WL_MAR_UM,
                                             r[-1] + WL_MAR_UM))
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
        ### Run a sweep or a step-and-measure scan
        if self.sweeping:
            data = self.sweep()
        else: # Default to step-and-measure
            data = self.scan(GUIInstance, self.units)
        ### Update QCL interface readings
        # GUIInstance.qcl(GUIInstance.activeQcl)
        # GUIInstance.update_qcl_reading(GUIInstance.activeQcl)
        ### Reverse data for plotting
        if self.units == 'invcm':
            plotData = np.flip(data, 0)
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
        GUIInstance.btn['Stop'][0].setChecked(False)
        GUIInstance.btn['Sweep'][0].setChecked(False)
        return 0

    def scan(self, GUIInstance, wlUnits='um'):
        '''Run a step-and measure scan.'''
        self.pci = pci_input()
        currentDir = os.getcwd()
        ### Lock use of reference
        dataRef = np.zeros((1, 2))
        if GUIInstance.btn['RefEnable'][0].isChecked():
            useRef = True
        else:
            useRef = False
        if useRef:
            try:
                dataPath = GUIInstance.refDir # Latest experiment directory
                dataPathParts = os.path.split(dataPath)
                fileName = '{}{}'.format(dataPathParts[-1], defaults.DEF_FILENAME)
                filePath = os.path.join(dataPath, fileName)
                dataRef = np.loadtxt(filePath)
            except Exception as exc:
                print('Failed to load reference:\n{}'.format(exc))
        ### Get parameters from UI
        sampleNumber = int(GUIInstance.inputField['SamplesPerWl'][0].text())
        sampleRate = int(GUIInstance.inputField['SamplingRate'][0].text())
        if wlUnits == 'um':
            wlStart = float(GUIInstance.inputField['WlStart'][0].text())
            wlEnd = float(GUIInstance.inputField['WlEnd'][0].text())
        if wlUnits == 'invcm':
            wlStart = float(GUIInstance.inputField['WlEnd'][0].text())
            wlEnd = float(GUIInstance.inputField['WlStart'][0].text())
        wlStep = float(GUIInstance.inputField['WlStep'][0].text())
        if platform.system() == 'Windows':
            currentDirSplit = currentDir.split('\\')
        else:
            currentDirSplit = currentDir.split('/')
        currentFolder = currentDirSplit[-1]
        # Divert stdout to log file
        original = sys.stdout
        logFile = open('%s.log' % (currentFolder), 'w')
        # sys.stdout = logFile
        # Write list of wavelengths, excuding ranges not covered by the QCLs
        wlRange = np.arange(wlStart, wlEnd + wlStep, wlStep)
        wlList = np.zeros(len(wlRange))
        if GUIInstance.wlUnits == 'um':
            minQclWl = defaults.WL_MINIMUMS_UM
            maxQclWl = defaults.WL_MAXIMUMS_UM
        elif GUIInstance.wlUnits == 'invcm': # Inverted, for compatibility in code
            minQclWl = defaults.WL_MAXIMUMS_INVCM
            maxQclWl = defaults.WL_MINIMUMS_INVCM
        for wli, wl in enumerate(wlRange):
            if (minQclWl[0] <= wl <= maxQclWl[0] or
                minQclWl[1] <= wl <= maxQclWl[1] or
                minQclWl[2] <= wl <= maxQclWl[2] or
                minQclWl[3] <= wl <= maxQclWl[3]):
                wlList[wli] = wl
        wlList = wlList[wlList != 0] # Remove zero values
        if GUIInstance.wlUnits == 'invcm':
            wlList = np.flip(wlList)
        stepNumber = len(wlList)
        if useRef and len(dataRef[:,0]) != stepNumber:
            print('Steps in reference and planned experiment do not match.')
            useRef = False
        # GUIElements['expStepTot'].setText('0 / %.0f' % stepNumber)
        data = np.zeros((stepNumber, 4)) # wl, X, Y, R
        print('Scan started ...')
        GUIInstance.spectrumCanvas.clear_plots()
        GUIInstance.spectrumCanvas.axes.set_xlim(wlList[0], wlList[-1])
        if useRef:
            GUIInstance.spectrumCanvasT.clear_plots()
            GUIInstance.spectrumCanvasT.axes.set_xlim(wlList[0], wlList[-1])
        GUIInstance.repaint()
        startRun = timer()
        step = 0
        scanInterrupted = False
        print('One wavelength point per step, avg. of %.0f samples at %.0f Hz'
              % (sampleNumber, sampleRate))
        for step in range(0, stepNumber): # First step at initial pos
            startStep = timer()
            # Check if "Stop" has been pressed
            if GUIInstance.btn['Stop'][0].isChecked(): # Stop if button pressed
                scanInterrupted = True
            if scanInterrupted:
                break
            # Select QCL
            wavelength = wlList[step]
            data[step, 0] = wavelength
            if minQclWl[0] <= wavelength <= maxQclWl[0]:
                GUIInstance.qcl_fast(1)
            elif minQclWl[1] <= wavelength <= maxQclWl[1]:
                GUIInstance.qcl_fast(2)
            elif minQclWl[2] <= wavelength <= maxQclWl[2]:
                GUIInstance.qcl_fast(3)
            elif minQclWl[3] <= wavelength <= maxQclWl[3]:
                GUIInstance.qcl_fast(4)
            else:
                print('Invalid vavelength: {:.3f}'.format(wavelength))
                continue
            # Tune to wavelength
            GUIInstance.tune_fast(wavelength)
            if GUIInstance.btn['ScanAutoEnable'][0].isChecked():
                # In auto-enable mode, turn on for every wavelength
                GUIInstance.btn['Emission'][0].setChecked(True)
                GUIInstance.emission()
            voltages = self.pci.get_voltages(sampleNumber, sampleRate)
            data[step, 1] = voltages[0] # Lock-in X
            data[step, 2] = voltages[1] # Lock-in Y
            data[step, 3] = (np.sqrt(np.power(data[step, 1], 2) +
                                     np.power(data[step, 2], 2))) # Lock-in R
            GUIInstance.spectrumCanvas.flush_events()
            GUIInstance.spectrumCanvas.plot_line(data[:step+1, 0],
                                                 data[:step+1, 3])
            if useRef:
                GUIInstance.spectrumCanvasT.flush_events()
                GUIInstance.spectrumCanvasT.plot_line(data[:step+1, 0],
                                                 data[:step+1, 3]/dataRef[:step+1, 3])
            print('Step {:.0f} ({:.1f} um): {:.3f} s'.format(step, wavelength,
                                                        (timer()-startStep)))
            if GUIInstance.btn['ScanAutoEnable'][0].isChecked():
                # In auto-enable mode, turn off for every wavelength
                GUIInstance.btn['Emission'][0].setChecked(False)
                GUIInstance.emission()
            GUIInstance.repaint()
        end = timer()
        if scanInterrupted:
            print('Scan interrupted after %.3f s' % (end-startRun))
            data = data[0:step]
        else:
            print('Scan complete, took %.3f s' % (end-startRun))
        logFile.close()
        # Return stdout to terminal
        sys.stdout = original
        # Save data as text file
        np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME), data)
        # Update QCL interface readings
        GUIInstance.qcl(GUIInstance.activeQcl)
        GUIInstance.update_qcl_reading(GUIInstance.activeQcl)
        GUIInstance.setUpdatesEnabled(True)
        GUIInstance.repaint()
        GUIInstance.grab().save('screenshot.png', 'png')
        return data

    def sweep(self):
        '''
        Run a sweep using the MIRcat's built-in function.
        Latest iteration of fast sweep routine, with no wavelength check.
        Use with "run", not "start".
        There is no need to directly select QCLs. If QCL ranges were properly
        compiled by "run", there will be no QCL swith within a range.
        '''
        ### Preamble
        print('Sweep started ...')
        print('One wavelength point per step, avg. of {:.0f} samples at {:.0f} Hz'
              .format(self.sampleNumber, self.sampleRate))
        startRun = timer()
        ### Configure triggered acquisition
        multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
        multipleAI.configure_triggered(defaults.PCI_TRIG,
                                       self.sampleNumber, self.sampleRate)
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
            self.laser.set_wl_trigger_parameters(r[0], r[-1], self.step,
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
                    rangeVoltages.append(multipleAI.acquire(self.sampleNumber))
            except Exception as exc:
                print('Sweep did not complete:\n{}'.format(exc))
                print('Partial data may still be usable.')
            voltages += rangeVoltages
            # print(wavelengths) # Troubleshooting
            # print(voltages) # Troubleshooting
            SDK.MIRcatSDK_StopScanInProgress() # Make sure this sweep has ended
        ### Make sure scans are done
        SDK.MIRcatSDK_StopScanInProgress()
        ### Clear triggered acquisition task
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


class pci_input():
    '''Get voltage from NI PCI analog inputs.'''

    def __init__(self): # Prepare NI-DAQ task
        self.multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])

    def collect(self, sampleNumber, sampleRate): # Get samples fromDAQ device
        self.multipleAI.configure(sampleNumber, sampleRate)
        voltages = self.multipleAI.acquire(sampleNumber)
        self.multipleAI.clear_task()
        return voltages

    def get_voltages(self, sampleNumber, sampleRate): # Collect and average
        daqVoltages = self.collect(sampleNumber, sampleRate)
        PCI_X = np.sum(daqVoltages[0])/sampleNumber
        PCI_Y = np.sum(daqVoltages[1])/sampleNumber
        return [PCI_X, PCI_Y]