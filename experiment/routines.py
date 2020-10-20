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
from . import defaults
from timeit import default_timer as timer
from instruments.ni_daq import MultiChannelAnalogInput as MultiAI
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigCanvas
from matplotlib.figure import Figure


class experiment(): # Directory management and multiple acquisitions

    def __init__(self):
        self.pci = pci_input()

    def start(self, GUIInstance, sweep=False):
        '''Handle experiment data directory, call scanning routine.'''
        ### Check inputs
        if GUIInstance.wlUnits == 'um':
            wlUnits = 'um'
            wlStart = float(GUIInstance.inputField['WlStart'][0].text())
            wlEnd = float(GUIInstance.inputField['WlEnd'][0].text())
            if wlStart >= wlEnd:
                print('The first wavelength must be smaller than the last.')
                GUIInstance.btn['Start'][0].setChecked(False)
                return
            if (wlStart < defaults.MIN_WL_QCL1_UM or
                wlEnd > defaults.MAX_WL_QCL4_UM):
                print('Scan range must be between {} and {} μm.'.format(
                      defaults.MIN_WL_QCL1_UM,
                      defaults.MAX_WL_QCL4_UM))
                GUIInstance.btn['Start'][0].setChecked(False)
                return
        elif GUIInstance.wlUnits == 'invcm':
            wlUnits = 'invcm'
            wlStart = float(GUIInstance.inputField['WlStart'][0].text())
            wlEnd = float(GUIInstance.inputField['WlEnd'][0].text())
            if wlStart <= wlEnd:
                print('The first wavenumber must be greater than the last.')
                GUIInstance.btn['Start'][0].setChecked(False)
                return
            if (wlStart > defaults.MIN_WL_QCL1_INVCM or
                wlEnd < defaults.MAX_WL_QCL4_INVCM):
                print('Scan range must be between {} and {} μm.'.format(
                      defaults.MIN_WL_QCL1_INVCM,
                      defaults.MAX_WL_QCL4_INVCM))
                GUIInstance.btn['Start'][0].setChecked(False)
                return
        else:
            print('Invalid wavelength unit.')
            GUIInstance.btn['Start'][0].setChecked(False)
            return
        ### Make sure laser is armed
        if not GUIInstance.btn['Arm'][0].isChecked():
            print('Laser is not armed.')
            GUIInstance.btn['Start'][0].setChecked(False)
            return
        ### Set up multiple acquisitions
        # if GUIElements['stop'].isChecked():
        #     break
        ### If in auto-enable mode, disable emission here
        if GUIInstance.btn['ScanAutoEnable'][0].isChecked():
            print('Scan auto-enable mode active: disabling emission.')
            GUIInstance.btn['Emission'][0].setChecked(False)
            GUIInstance.emission()
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
        GUIInstance.latestDir = expDir
        # GUIElements['expNo'].setText('%.0f' % newExpNo)
        if sweep:
            data = self.sweep(GUIInstance, wlUnits)
        else:
            data = self.scan(GUIInstance, wlUnits)
        GUIInstance.btn['Start'][0].setChecked(False)
        GUIInstance.btn['Stop'][0].setChecked(False)
        return data

    def scan(self, GUIInstance, wlUnits='um'):
        '''Scan and logging routine.'''
        currentDir = os.getcwd()
        ### Lock use of reference
        dataRef = np.zeros((1, 2))
        if GUIInstance.btn['RefEnable'][0].isChecked:
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

    def sweep(self, GUIInstance, wlUnits='um'):
        '''WORK IN PROGRESS/DO NOT USE'''
        '''Run a sweep using the MIRcat's built-in function.'''
        currentDir = os.getcwd()
        ### Lock use of reference
        dataRef = np.zeros((1, 2))
        if GUIInstance.btn['RefEnable'][0].isChecked:
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
        # Get parameters from UI
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
        # Configure triggered acquisition
        MultiAI.configure_triggered()

        # Run experiment

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