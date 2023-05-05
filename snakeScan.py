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

''' Put this function under routines.experiments as one of the case of def scan(self):
'''
def snakeScan(self):
        '''Run a snake scan using the Prior's built-in function. One wavelength.'''
        ### Troubleshooting
        #SDK.MIRcatSDK_StopScanInProgress() # Make sure previous sweep has ended

        ### Preamble
        print('Snake scan started ...')
        print('One wavelength point per step, avg. of {:.0f} samples at {:.0f} Hz'
              .format(self.parameters.sampleNumber, self.parameters.sampleRate))
        startRun = timer()

        posx, posy, indx, indy, voltages, wavelengths = [], [], [], [], [], []
        dataIndexPattern = 0

        ### Iterate over scan patterns
        '''
        Progress: figuring out what's a scan pattern
        '''

        for p, sn, sr, sp, w, qcl, r, ind in zip(self.parameters.patterns,
                                                        self.parameters.sampleNumbers,
                                                        self.parameters.sampleRates,
                                                        self.parameters.speeds,
                                                        self.parameters.wlwnList,
                                                        self.parameters.qcl,
                                                        self.parameters.ranges,
                                                        self.parameters.patternIndices):

            ### Setup, start triggered acquisition task
            multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
            multipleAI.configure_triggered(defaults.PCI_SNAKE_TRIG,
                                        self.parameters.sampleNumber, self.parameters.sampleRate)
                                        ### Start task
            multipleAI.start_task()
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


                            ### Move stage to the start position
                            self.parameters.stage.goto(x, y)
                            ### Wait for stage to stop moving
                            while int(self.parameters.stage.busy()) > 0:
                                        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
                            (xStg, yStg) = self.parameters.stage.get_position()
                            ### Arm stage trigger
                            self.paramets.stage.arm_trigger()
                            ### Not implemented.

                            ### Start scan

                            ### Not implemented.

                            ### Triggered acquisition
                            rangeVoltages = []
                            try: # Failure here likely due to timeout because of skipped points
                                for x in range(0, len(r)):
                                    rangeVoltages.append(multipleAI.acquire_fast(self.parameters.sampleNumber))
                            except Exception as exc:
                                print('Sweep did not complete:\n{}'.format(exc))
                                print('Partial data may still be usable.')
                            voltages += rangeVoltages
                            '''
                            old step scan below:
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
                            '''
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

        '''
        I stopped here. 03.08.23
        '''
        '''
        ### From sweep()
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
            #SDK.MIRcatSDK_StopScanInProgress() # Make sure this sweep has ended
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
        '''