'''
old_routines
Giovanni Sartorello (srtgnn@gmail.com)
Obsolete experiment routines
Version 2
Python 3.8.3 on Windows 10
Created 2020-Nov-30
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

class old_experiment(): # Directory management and multiple acquisitions

    def __init__(self):
        pass

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
            if (wlStart > defaults.MIN_WN_QCL1_INVCM or
                wlEnd < defaults.MAX_WN_QCL4_INVCM):
                print('Scan range must be between {} and {} μm.'.format(
                      defaults.MIN_WN_QCL1_INVCM,
                      defaults.MAX_WN_QCL4_INVCM))
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
        if GUIInstance.btn['Sweep'][0].isChecked():
            data = self.sweep_fast(GUIInstance, wlUnits)
            # data = self.sweep_fast_retrig(GUIInstance, wlUnits)
        else:
            data = self.scan(GUIInstance, wlUnits)
        GUIInstance.btn['Start'][0].setChecked(False)
        GUIInstance.btn['Stop'][0].setChecked(False)
        return data

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

    def sweep(self, GUIInstance, wlUnits='um'):
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
                fileName = '{}{}'.format(dataPathParts[-1],
                                                          defaults.DEF_FILENAME)
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
        ### Divert stdout to log file
        original = sys.stdout
        logFile = open('%s.log' % (currentFolder), 'w')
        # sys.stdout = logFile
        ### Write list of wavelengths, excuding ranges not covered by the QCLs
        wlRange = np.arange(wlStart, wlEnd + wlStep, wlStep)
        wlList = np.zeros(len(wlRange))
        if GUIInstance.wlUnits == 'um':
            minQclWl = defaults.WL_MINIMUMS_UM
            maxQclWl = defaults.WL_MAXIMUMS_UM
        elif GUIInstance.wlUnits == 'invcm': # Inverted for compatibility
            minQclWl = defaults.WL_MAXIMUMS_INVCM
            maxQclWl = defaults.WL_MINIMUMS_INVCM
        for wli, wl in enumerate(wlRange): # Only keep wavelengths within limits
            if (minQclWl[0] <= wl <= maxQclWl[0] or
                minQclWl[1] <= wl <= maxQclWl[1] or
                minQclWl[2] <= wl <= maxQclWl[2] or
                minQclWl[3] <= wl <= maxQclWl[3]):
                wlList[wli] = wl
        wlList = wlList[wlList != 0] # Remove zero values
        if GUIInstance.wlUnits == 'invcm': # Go from largest to smallest
            wlList = np.flip(wlList)
        print(wlList)
        stepNumber = len(wlList)
        if useRef and len(dataRef[:,0]) != stepNumber:
            print('Steps in reference and planned experiment do not match.')
            useRef = False
        # GUIElements['expStepTot'].setText('0 / %.0f' % stepNumber)
        data = np.zeros((stepNumber, 4)) # wl, X, Y, R
        print('Sweep started ...')
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
        ### Configure triggered acquisition
        multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
        multipleAI.configure_triggered(defaults.PCI_TRIG, sampleNumber, sampleRate)
        ### Set laser triggering (one TTL pulse per wl/wn) and start sweep
        speed = float(GUIInstance.inputField['Speed'][0].text())
        if GUIInstance.wlUnits == 'um':
            start = wlList[0] - wlStep # Start one before, to make sure
            end = wlList[-1] + wlStep  # End one after, to make sure
            interval = wlStep
            GUIInstance.laser.set_wl_trigger_parameters(start, end, interval, units='um')
            GUIInstance.laser.sweep_and_forget(wlList[0], wlList[-1] + wlStep, speed, units='um')
            print(GUIInstance.laser.get_wl_trigger_parameters()) # Troubleshooting
        elif GUIInstance.wlUnits == 'invcm':
            end = wlList[0] + wlStep # Start one before, to make sure
            start = wlList[-1] - wlStep  # End one after, to make sure
            interval = wlStep
            GUIInstance.laser.set_wl_trigger_parameters(start, end, interval, units='invcm')
            GUIInstance.laser.sweep_and_forget(wlList[0], wlList[-1], speed, units = 'invcm')
            print(GUIInstance.laser.get_wl_trigger_parameters()) # Troubleshooting
        ### Run experiment
        sweepRunning = True
        try:
            while sweepRunning:
                ### Check if all points already acquired
                if step > len(wlList):
                    scanInterrupted = True
                ### Check if "Stop" has been pressed
                if GUIInstance.btn['Stop'][0].isChecked(): # Stop if button pressed
                    scanInterrupted = True
                ### Stop the laser and break while loop
                if scanInterrupted:
                    SDK.MIRcatSDK_StopScanInProgress()
                    break
                ### Triggered acquisition
                voltages = multipleAI.acquire(sampleNumber)
                ### Get wavelength at trigger
                isScanInProgress = c_bool(True)
                isScanActive = c_bool(False)
                isScanPaused = c_bool(False)
                curScanNum = c_uint16()
                curScanPercent = c_uint16()
                curWW = c_float()
                isTECinProgress = c_bool()
                isMotionInProgress = c_bool()
                if GUIInstance.wlUnits == 'um':
                    units = MIRcatSDK_UNITS_MICRONS
                elif GUIInstance.wlUnits == 'invcm':
                    units = MIRcatSDK_UNITS_CM1
                else:
                    units = MIRcatSDK_UNITS_MICRONS
                SDK.MIRcatSDK_GetScanStatus(byref(isScanInProgress),
                                            byref(isScanActive),
                                            byref(isScanPaused),
                                            byref(curScanNum),
                                            byref(curScanPercent),
                                            byref(curWW),
                                            byref(units),
                                            byref(isTECinProgress),
                                            byref(isMotionInProgress))
                # Print current wavelength/wavenumber
                print(curWW.value) # troubleshooting
                ### Average voltages
                # data[step, 0] = curWW.value
                if GUIInstance.wlUnits == 'um':
                    current_wl = curWW.value
                elif GUIInstance.wlUnits == 'invcm':
                    current_wl = 1 / (curWW.value*1E-4)
                else:
                    current_wl = curWW.value
                # data[step, 0] = wlList[(np.abs(wlList - current_wl)).argmin()]
                data[step, 0] = current_wl
                data[step, 1] = np.sum(voltages[0])/sampleNumber # Lock-in X
                data[step, 2] = np.sum(voltages[1])/sampleNumber # Lock-in Y
                data[step, 3] = (np.sqrt(np.power(data[step, 1], 2) +
                                        np.power(data[step, 2], 2))) # Lock-in R
                GUIInstance.spectrumCanvas.flush_events()
                GUIInstance.spectrumCanvas.plot_line(data[:step+1, 0],
                                                     data[:step+1, 3])
                if useRef:
                    GUIInstance.spectrumCanvasT.flush_events()
                    GUIInstance.spectrumCanvasT.plot_line(data[:step+1, 0],
                                            data[:step+1, 3]/dataRef[:step+1, 3])
                step += 1
                GUIInstance.repaint()
                if not isScanActive:
                    sweepRunning = False
                    break
        except Exception as exc:
            print('Failed to run sweep:\n{}'.format(exc))
        end = timer()
        SDK.MIRcatSDK_StopScanInProgress() # Scan may otherwise hang
        GUIInstance.btn['Sweep'][0].setChecked(False)
        ### Clear triggered acquisition task
        multipleAI.clear_task()
        if scanInterrupted:
            print('Scan interrupted after %.3f s' % (end-startRun))
            data = data[0:step]
        else:
            print('Scan complete, took %.3f s' % (end-startRun))
        logFile.close()
        ### Return stdout to terminal
        sys.stdout = original
        ### Save data as text file
        np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME), data)
        ### Update QCL interface readings
        GUIInstance.qcl(GUIInstance.activeQcl)
        GUIInstance.update_qcl_reading(GUIInstance.activeQcl)
        GUIInstance.setUpdatesEnabled(True)
        GUIInstance.repaint()
        GUIInstance.grab().save('screenshot.png', 'png')
        return data

    def sweep_fast(self, GUIInstance, wlUnits='um'):
        '''Run a sweep using the MIRcat's built-in function.
           Fast version, skips wavelength checks.'''
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
        elif wlUnits == 'invcm':
            wlStart = float(GUIInstance.inputField['WlEnd'][0].text())
            wlEnd = float(GUIInstance.inputField['WlStart'][0].text())
        else:
            wlStart = float(GUIInstance.inputField['WlStart'][0].text())
            wlEnd = float(GUIInstance.inputField['WlEnd'][0].text())
        wlStep = float(GUIInstance.inputField['WlStep'][0].text())
        if platform.system() == 'Windows':
            currentDirSplit = currentDir.split('\\')
        else:
            currentDirSplit = currentDir.split('/')
        currentFolder = currentDirSplit[-1]
        ### Divert stdout to log file
        original = sys.stdout
        logFile = open('%s.log' % (currentFolder), 'w')
        # sys.stdout = logFile
        ### Write list of wavelengths, excuding ranges not covered by the QCLs
        wlRange = np.arange(wlStart, wlEnd + wlStep, wlStep)
        wlList = np.zeros(len(wlRange))
        if GUIInstance.wlUnits == 'um':
            minQclWl = defaults.WL_MINIMUMS_UM
            maxQclWl = defaults.WL_MAXIMUMS_UM
        elif GUIInstance.wlUnits == 'invcm': # Inverted, for compatibility in code
            minQclWl = defaults.WL_MAXIMUMS_INVCM
            maxQclWl = defaults.WL_MINIMUMS_INVCM
        else:
            minQclWl = defaults.WL_MINIMUMS_UM
            maxQclWl = defaults.WL_MAXIMUMS_UM
        for wli, wl in enumerate(wlRange): # Only keep wavelengths within limits
            if (minQclWl[0] <= wl <= maxQclWl[0] or
                minQclWl[1] <= wl <= maxQclWl[1] or
                minQclWl[2] <= wl <= maxQclWl[2] or
                minQclWl[3] <= wl <= maxQclWl[3]):
                wlList[wli] = wl
        wlList = wlList[wlList != 0] # Remove zero values
        if GUIInstance.wlUnits == 'invcm':
            ### Workaround for an issue with the last point:
            ### add one here, ignore it later.
            # wlListAlt = np.zeros(len(wlList))
            # wlListAlt[0] = wlList[0] - wlStep
            # wlListAlt[1:] = wlList
            ### Go from largest to smallest
            wlList = np.flip(wlList)
        print(wlList)
        stepNumber = len(wlList)
        if useRef and len(dataRef[:,0]) != stepNumber:
            print('Steps in reference and planned experiment do not match.')
            useRef = False
        # GUIElements['expStepTot'].setText('0 / %.0f' % stepNumber)
        data = np.zeros((stepNumber, 4)) # wl, X, Y, R
        print('Sweep started ...')
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
        ### Configure triggered acquisition
        multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
        multipleAI.configure_triggered(defaults.PCI_TRIG, sampleNumber, sampleRate)
        ### Set laser triggering (one TTL pulse per wl/wn) and start sweep
        speed = float(GUIInstance.inputField['Speed'][0].text())
        if GUIInstance.wlUnits == 'um':
            start = wlList[0] - wlStep # Start one before, to make sure
            end = wlList[-1] + wlStep  # End one after, to make sure
            interval = wlStep
            GUIInstance.laser.set_wl_trigger_parameters(start, end, interval, units='um')
            GUIInstance.laser.sweep_and_forget(wlList[0], wlList[-1] + wlStep, speed, units='um')
            # print(GUIInstance.laser.get_wl_trigger_parameters()) # Troubleshooting
        elif GUIInstance.wlUnits == 'invcm':
            end = wlList[0] + wlStep # Start one before, to make sure
            start = wlList[-1] - wlStep  # End one after, to make sure
            interval = wlStep
            GUIInstance.laser.set_wl_trigger_parameters(start, end, interval, units='invcm')
            GUIInstance.laser.sweep_and_forget(wlList[0], wlList[-1] - wlStep, speed, units = 'invcm')
            # print(GUIInstance.laser.get_wl_trigger_parameters()) # Troubleshooting
        ### Triggered acquisition
        voltages = []
        try: # Failure here most likely due to timeout because of skipped points
            for x in range(0, len(wlList)):
                voltages.append(multipleAI.acquire(sampleNumber))
        except Exception as exc:
            print('Sweep did not complete:\n{}'.format(exc))
            print('Partial data may still be usable.')
        ### Clear triggered acquisition task
        multipleAI.clear_task()
        try: # Failure here certain if points skipped above
            for x, wl in enumerate(wlList):
                data[x, 0] = wl
                data[x, 1] = np.sum(voltages[x][0])/sampleNumber # Lock-in X
                data[x, 2] = np.sum(voltages[x][1])/sampleNumber # Lock-in Y
                data[x, 3] = (np.sqrt(np.power(data[x, 1], 2) +
                                        np.power(data[x, 2], 2))) # Lock-in R
        except Exception as exc:
            print('Data formatting did not complete:\n{}'.format(exc))
            print('Partial data may still be usable.')
        data = data[data[:, 0] != 0] # Remove zero-wavelength values
        print('Requested {} points, acquired {}.'.format(len(wlList), len(data[:, 0])))
        GUIInstance.spectrumCanvas.flush_events()
        GUIInstance.spectrumCanvas.plot_line(data[:, 0], data[:, 3])
        if useRef:
            GUIInstance.spectrumCanvasT.flush_events()
            GUIInstance.spectrumCanvasT.plot_line(data[:, 0], data[:, 3]/dataRef[:, 3])
        GUIInstance.repaint()
        end = timer()
        SDK.MIRcatSDK_StopScanInProgress() # Scan may otherwise hang
        GUIInstance.btn['Sweep'][0].setChecked(False)
        if scanInterrupted:
            print('Scan interrupted after %.3f s' % (end-startRun))
            data = data[0:step]
        else:
            print('Scan complete, took %.3f s' % (end-startRun))
        logFile.close()
        ### Return stdout to terminal
        sys.stdout = original
        ### Save data as text file
        np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME), data)
        ### Update QCL interface readings
        GUIInstance.qcl(GUIInstance.activeQcl)
        GUIInstance.update_qcl_reading(GUIInstance.activeQcl)
        GUIInstance.setUpdatesEnabled(True)
        GUIInstance.repaint()
        GUIInstance.grab().save('screenshot.png', 'png')
        return data

    def sweep_fast_retrig(self, GUIInstance, wlUnits='um'):
        '''Run a sweep using the MIRcat's built-in function.
           Faster sweep using retriggerable analog inputs.
           Requires NI X-series (63XX) platforms.'''
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
        elif wlUnits == 'invcm':
            wlStart = float(GUIInstance.inputField['WlEnd'][0].text())
            wlEnd = float(GUIInstance.inputField['WlStart'][0].text())
        else:
            wlStart = float(GUIInstance.inputField['WlStart'][0].text())
            wlEnd = float(GUIInstance.inputField['WlEnd'][0].text())
        wlStep = float(GUIInstance.inputField['WlStep'][0].text())
        if platform.system() == 'Windows':
            currentDirSplit = currentDir.split('\\')
        else:
            currentDirSplit = currentDir.split('/')
        currentFolder = currentDirSplit[-1]
        ### Divert stdout to log file
        original = sys.stdout
        logFile = open('%s.log' % (currentFolder), 'w')
        # sys.stdout = logFile
        ### Write list of wavelengths, excuding ranges not covered by the QCLs
        wlRange = np.arange(wlStart, wlEnd + wlStep, wlStep)
        wlList = np.zeros(len(wlRange))
        if GUIInstance.wlUnits == 'um':
            minQclWl = defaults.WL_MINIMUMS_UM
            maxQclWl = defaults.WL_MAXIMUMS_UM
        elif GUIInstance.wlUnits == 'invcm': # Inverted, for compatibility in code
            minQclWl = defaults.WL_MAXIMUMS_INVCM
            maxQclWl = defaults.WL_MINIMUMS_INVCM
        else:
            minQclWl = defaults.WL_MINIMUMS_UM
            maxQclWl = defaults.WL_MAXIMUMS_UM
        for wli, wl in enumerate(wlRange): # Only keep wavelengths within limits
            if (minQclWl[0] <= wl <= maxQclWl[0] or
                minQclWl[1] <= wl <= maxQclWl[1] or
                minQclWl[2] <= wl <= maxQclWl[2] or
                minQclWl[3] <= wl <= maxQclWl[3]):
                wlList[wli] = wl
        wlList = wlList[wlList != 0] # Remove zero values
        if GUIInstance.wlUnits == 'invcm': # Go from largest to smallest
            wlList = np.flip(wlList)
        print(wlList)
        stepNumber = len(wlList)
        if useRef and len(dataRef[:,0]) != stepNumber:
            print('Steps in reference and planned experiment do not match.')
            useRef = False
        # GUIElements['expStepTot'].setText('0 / %.0f' % stepNumber)
        data = np.zeros((stepNumber, 4)) # wl, X, Y, R
        print('Sweep started ...')
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
        ### Configure triggered acquisition
        multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
        multipleAI.configure_triggered(defaults.PCI_TRIG, sampleNumber, sampleRate)
        ### Set laser triggering (one TTL pulse per wl/wn) and start sweep
        speed = float(GUIInstance.inputField['Speed'][0].text())
        if GUIInstance.wlUnits == 'um':
            start = wlList[0] - wlStep # Start one before, to make sure
            end = wlList[-1] + wlStep  # End one after, to make sure
            interval = wlStep
            GUIInstance.laser.set_wl_trigger_parameters(start, end, interval, units='um')
            GUIInstance.laser.sweep_and_forget(wlList[0], wlList[-1] + wlStep, speed, units='um')
            print(GUIInstance.laser.get_wl_trigger_parameters()) # Troubleshooting
        elif GUIInstance.wlUnits == 'invcm':
            end = wlList[0] + wlStep # Start one before, to make sure
            start = wlList[-1] - wlStep  # End one after, to make sure
            interval = wlStep
            GUIInstance.laser.set_wl_trigger_parameters(start, end, interval, units='invcm')
            GUIInstance.laser.sweep_and_forget(wlList[0], wlList[-1], speed, units = 'invcm')
            print(GUIInstance.laser.get_wl_trigger_parameters()) # Troubleshooting
        ### Triggered acquisition
        try: # Failure here most likely due to timeout because of skipped points
            voltages = multipleAI.acquire(sampleNumber*len(wlList))
            print(voltages)
        except Exception as exc:
            print('Sweep did not complete:\n{}'.format(exc))
            print('Partial data may still be usable.')
        ### Clear triggered acquisition task
        multipleAI.clear_task()
        try: # Failure here certain if points skipped above
            for x, wl in enumerate(wlList):
                vRange = [x * sampleNumber, x * sampleNumber + sampleNumber]
                print('Enumerate step {:.0f}, wl/wn {:.2f}, points {}'.format(x, wl, vRange))
                data[x, 0] = wl
                data[x, 1] = np.sum(voltages[1, vRange[0]:vRange[1]])/sampleNumber # Lock-in X
                data[x, 2] = np.sum(voltages[0, vRange[0]:vRange[1]])/sampleNumber # Lock-in Y
                data[x, 3] = (np.sqrt(np.power(data[x, 1], 2) +
                                        np.power(data[x, 2], 2))) # Lock-in R
        except Exception as exc:
            print('Data formatting did not complete:\n{}'.format(exc))
            print('Partial data may still be usable.')
        data = data[data[:, 0] != 0] # Remove zero-wavelength values
        print('Requested {} points, acquired {}.'.format(len(wlList), len(data[:, 0])))
        GUIInstance.spectrumCanvas.flush_events()
        GUIInstance.spectrumCanvas.plot_line(data[:, 0], data[:, 3])
        if useRef:
            GUIInstance.spectrumCanvasT.flush_events()
            GUIInstance.spectrumCanvasT.plot_line(data[:, 0], data[:, 3]/dataRef[:, 3])
        GUIInstance.repaint()
        end = timer()
        SDK.MIRcatSDK_StopScanInProgress() # Scan may otherwise hang
        GUIInstance.btn['Sweep'][0].setChecked(False)
        if scanInterrupted:
            print('Scan interrupted after %.3f s' % (end-startRun))
            data = data[0:step]
        else:
            print('Scan complete, took %.3f s' % (end-startRun))
        logFile.close()
        ### Return stdout to terminal
        sys.stdout = original
        ### Save data as text file
        np.savetxt('{}{}'.format(currentFolder, defaults.DEF_FILENAME), data)
        ### Update QCL interface readings
        GUIInstance.qcl(GUIInstance.activeQcl)
        GUIInstance.update_qcl_reading(GUIInstance.activeQcl)
        GUIInstance.setUpdatesEnabled(True)
        GUIInstance.repaint()
        GUIInstance.grab().save('screenshot.png', 'png')
        return data

    def sweep_backup(self):
        '''
        Run a sweep using the MIRcat's built-in function.
        '''
        ### Preamble
        print('Sweep started ...')
        print('One wavelength point per step, avg. of {:.0f} samples at {:.0f} Hz'
              .format(self.sampleNumber, self.sampleRate))
        startRun = timer()
        ### Setup triggered acquisition
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
                    rangeVoltages.append(multipleAI.acquire(self.sampleNumber))
            except Exception as exc:
                print('Sweep did not complete:\n{}'.format(exc))
                print('Partial data may still be usable.')
            voltages += rangeVoltages
            # print(wavelengths) # Troubleshooting
            # print(voltages) # Troubleshooting
            SDK.MIRcatSDK_StopScanInProgress() # Make sure this sweep has ended
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
