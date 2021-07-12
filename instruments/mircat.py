#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
mircat
Giovanni Sartorello (srtgnn@gmail.com)
Control MIRcat QCL laser via VISA.
Created 2019-Mar-12 for Python 3.7.2
'''

### Basic imports
import inspect, os, sys, time
from ctypes import (byref, CDLL, c_bool, c_float, c_uint, c_uint8, c_uint16,
                    c_uint32)
from inspect import currentframe, getfile
from os.path import abspath, join, split, realpath
from timeit import default_timer as timer

### Look for modules in "instruments", https://stackoverflow.com/a/6098238
mDir = realpath(abspath(split(getfile(currentframe()))[0]))
if mDir not in sys.path:
    sys.path.append(mDir)

### Look for modules in "daylight"
mSubdir = realpath(abspath(join(split(getfile(currentframe()))[0],'daylight')))
if mSubdir not in sys.path:
    sys.path.append(mSubdir)
from daylight.MIRcatSDKConstants import (MIRcatSDK_PROC_TRIG_MODE_INTERNAL,
                                         MIRcatSDK_PULSE_MODE_INTERNAL,
                                         MIRcatSDK_UNITS_CM1,
                                         MIRcatSDK_UNITS_MICRONS)
from daylight.MIRcatSDKHelpers import ArmAndWaitForTemp

### Import Daylight's MIRcat DLL
SDK_NAME = 'MIRcatSDK.dll'
sdkPath = os.path.join(mSubdir, SDK_NAME)
SDK = CDLL(sdkPath)

### Default values for wavelength triggering.
### These were found via MIRcatSDK_GetWlTrigParams and units are unknown.
DEFAULT_DWELL_TIME = 100000
DEFAULT_AFTER_OFF_TIME = 100000

class laser():
    '''Control MIRcat QCL laser.'''

    def __init__(self):
        '''Initialize laser.'''
        # Get API info and connect
        self.get_api_info(silent=False)
        self.connect()
        # Get number of installed QCL modules
        self.numQcls = c_uint8(0)
        self.get_qcl_no(silent=False)
        # Check interlock status
        self.isInterlockSet = c_bool(False)
        self.check_interlock()
        # Check key switch position
        self.isKeySwitchSet = c_bool(False)
        self.check_key_switch()
        # Other class variables
        self.isArmed = c_bool(False)
        self.isEmitting = c_bool(False)
        self.isTuned = c_bool(False)

    def arm(self):
        '''Arm laser.'''
        print('Arming ...')
        SDK.MIRcatSDK_IsLaserArmed(byref(self.isArmed)) # Check first
        if not self.isArmed.value:
            SDK.MIRcatSDK_ArmDisarmLaser()
        while not self.isArmed.value:
            SDK.MIRcatSDK_IsLaserArmed(byref(self.isArmed))
            time.sleep(1) # DLS default wait: 1 s
        print('Laser armed.')

    def arm_and_stabilize(self): # DEPRECATED
        '''Arm laser and wait for temperatures to stabilize.'''
        '''To be removed. Use arm() then stabilize() instead.'''
        print('Arming ...')
        ArmAndWaitForTemp(SDK, self.numQcls)
        print('Laser armed.')
        self.isArmed = c_bool(True)

    def check_interlock(self):
        '''Check interlock status, exit the program if not set.'''
        ret = SDK.MIRcatSDK_IsInterlockedStatusSet(byref(self.isInterlockSet))
        if self.isInterlockSet.value:
            print('Interlock set.')
        else:
            print('Interlock not set ({}). Exiting ...'.format(ret))
            self.exit_program()

    def check_key_switch(self):
        '''Check key switch position, exit the program if off.'''
        ret = SDK.MIRcatSDK_IsKeySwitchStatusSet(byref(self.isKeySwitchSet))
        if self.isInterlockSet.value:
            print('Key switch position: on.')
        else:
            print('Key switch position: off ({}). Exiting ...'.format(ret))
            self.exit_program()

    def connect(self):
        '''Initialize API and connect to laser.'''
        ret = SDK.MIRcatSDK_Initialize()
        if ret == 0:
            print('MIRcatSDK API initialized. Laser connected.')
        else:
            print('MIRcatSDK API: failed to initialize ({}).'.format(ret))
            self.exit_program()

    def disable(self):
        '''Disable laser emission.'''
        SDK.MIRcatSDK_IsEmissionOn(byref(self.isEmitting)) # Check first
        if not self.isEmitting.value: # No need to disable
            print('Laser emission already disabled.')
            return
        ret = SDK.MIRcatSDK_TurnEmissionOff()
        SDK.MIRcatSDK_IsEmissionOn(byref(self.isEmitting))
        if not self.isEmitting.value:
            print('Laser emission disabled.')
        else:
            print('Could not disable laser emisson ({}).'.format(ret))

    def disarm(self):
        '''Disarm laser.'''
        SDK.MIRcatSDK_IsLaserArmed(byref(self.isArmed)) # Check first
        if not self.isArmed: # No need to disarm
            print('Laser already disarmed.')
            return
        ret = SDK.MIRcatSDK_DisarmLaser()
        SDK.MIRcatSDK_IsLaserArmed(byref(self.isArmed))
        if not self.isArmed.value:
            print('Laser disarmed.')
        else:
            print('Failed to disarm laser ({}).'.format(ret))

    def disconnect(self):
        '''Deinitialize API and disconnect from laser.'''
        ret = SDK.MIRcatSDK_DeInitialize()
        if ret == 0:
            print('MIRcatSDK API deinitialized. Laser disconnected.')
        else:
            print('MIRcatSDK API: failed to deinitialize ({}).'.format(ret))

    def enable(self):
        '''Enable laser emission.'''
        SDK.MIRcatSDK_IsLaserArmed(byref(self.isArmed)) # Check arming
        if not self.isArmed.value:
            print('Arm laser first.')
            return
        SDK.MIRcatSDK_IsTuned(byref(self.isTuned)) # Check tuning
        if not self.isTuned.value:
            print('Tune laser first.')
            return
        SDK.MIRcatSDK_IsEmissionOn(byref(self.isEmitting)) # Check emission
        if self.isEmitting.value: # No need to enable
            print('Laser emission already enabled.')
            return
        ret = SDK.MIRcatSDK_TurnEmissionOn()
        while not self.isEmitting.value:
            SDK.MIRcatSDK_IsEmissionOn(byref(self.isEmitting))
            time.sleep(0.5) # DLS default wait: 0.5 s
        print('Laser emission enabled.')

    def exit_program(self):
        '''Disconnect the laser and close the program.'''
        self.disconnect()
        sys.exit(0)

    def get_api_info(self, silent=True):
        '''Get and display API version.'''
        major = c_uint16()
        minor = c_uint16()
        patch = c_uint16()
        ret = SDK.MIRcatSDK_GetAPIVersion(byref(major), byref(minor),
                                          byref(patch))
        # Note: "silent" does not apply to dependencies
        if ret == 0 and not silent:
            print('MIRcatSDK API version: {0}.{1}.{2}'.format(major.value,
                  minor.value, patch.value))
        elif ret != 0:
            print('MIRcatSDK API: failed to get info ({}).'.format(ret))
            self.exit_program()

    def get_current(self, tec):
        '''Return the current of TEC "tec" in mA.'''
        tecCur = c_uint16(0)
        SDK.MIRcatSDK_GetTecCurrent(c_uint8(tec), byref(tecCur))
        return tecCur.value

    def get_pulse_rate(self, qcl):
        '''Return the pulse rate of QCL "qcl" in Hz.'''
        rate_Hz = c_float(0)
        SDK.MIRcatSDK_GetQCLPulseRate(c_uint8(qcl), byref(rate_Hz))
        return rate_Hz.value

    def get_pulse_width(self, qcl):
        '''Return the pulse width of QCL "qcl" in ns.'''
        width_ns = c_float(0)
        SDK.MIRcatSDK_GetQCLPulseWidth(c_uint8(qcl), byref(width_ns))
        return width_ns.value

    def get_temperature(self, qcl):
        '''Return the temperature of QCL "qcl"'''
        qclTemp = c_float(0)
        SDK.MIRcatSDK_GetQCLTemperature(c_uint8(qcl), byref(qclTemp))
        return qclTemp.value

    def get_qcl_no(self, silent=True):
        '''Get number of installed QCL modules.'''
        SDK.MIRcatSDK_GetNumInstalledQcls(byref(self.numQcls))
        if not silent:
            print('Installed QCL modules: {}.'.format(self.numQcls.value))

    def get_wavelength(self):
        '''Get actual wavelength from laser.'''
        wlRead = c_float()
        units = c_uint8()
        lightValid = c_bool()
        SDK.MIRcatSDK_GetActualWW(byref(wlRead), byref(units),
                                  byref(lightValid))
        return wlRead.value

    def get_wl_trigger_parameters(self):
        '''Get the wavelength trigger parameters.'''
        pbPulseMode = c_uint8()
        pbProcTrigMode = c_uint8()
        pfWlTrigStart = c_float()
        pfWlTrigStop = c_float()
        pfWlTrigInterval = c_float()
        pbUnits = c_uint8()
        pDwellTime = c_uint32()
        pAfterOffTime = c_uint32()
        SDK.MIRcatSDK_GetWlTrigParams(byref(pbPulseMode),
                                      byref(pbProcTrigMode),
                                      byref(pfWlTrigStart),
                                      byref(pfWlTrigStop),
                                      byref(pfWlTrigInterval),
                                      byref(pbUnits),
                                      byref(pDwellTime),
                                      byref(pAfterOffTime))
        return([pfWlTrigStart.value,
                pfWlTrigStop.value,
                pfWlTrigInterval.value,
                pDwellTime.value,
                pAfterOffTime.value])

    def set_qcl_parameters(self, qcl, pulseRate_Hz, pulseWidth_ns, current_mA):
        '''Set qcl module parameters.'''
        bQcl = c_uint8(qcl)
        fPulseRateInHz = c_float(pulseRate_Hz)
        fPulseWidthInNanoSec = c_float(pulseWidth_ns)
        fCurrentInMilliAmps = c_float(current_mA)
        SDK.MIRcatSDK_SetQCLParams(bQcl,
                                   fPulseRateInHz,
                                   fPulseWidthInNanoSec,
                                   fCurrentInMilliAmps);

    def set_wl_trigger_parameters(self, start, end, interval, units = 'um'):
        '''Set the wavelength trigger parameters.'''
        pbPulseMode = MIRcatSDK_PULSE_MODE_INTERNAL
        pbProcTrigMode = MIRcatSDK_PROC_TRIG_MODE_INTERNAL
        pfWlTrigStart = c_float(start)
        pfWlTrigStop = c_float(end)
        pfWlTrigInterval = c_float(interval)
        if units == 'invcm':
            pbUnits = MIRcatSDK_UNITS_CM1
        elif units == 'um':
            pbUnits = MIRcatSDK_UNITS_MICRONS
        else:
            print('Trigger settings: unknown units. Defaulting to micrometers.')
            pbUnits = MIRcatSDK_UNITS_MICRONS
        pDwellTime = c_uint32(DEFAULT_DWELL_TIME)
        pAfterOffTime = c_uint32(DEFAULT_AFTER_OFF_TIME)
        SDK.MIRcatSDK_SetWlTrigParams(pbPulseMode,
                                      pbProcTrigMode,
                                      pfWlTrigStart,
                                      pfWlTrigStop,
                                      pfWlTrigInterval,
                                      pbUnits,
                                      pDwellTime,
                                      pAfterOffTime)

    def stabilize(self):
        '''Wait until TEC temperatures are stable.
           Always run after arming and before tuning.'''
        print('Waiting for TEC temperatures to stabilize ...')
        atTemp = c_bool(False)
        tecCur = c_uint16(0)
        qclTemp = c_float(0)
        while not atTemp.value:
            for x in range(1, self.numQcls.value + 1):
                SDK.MIRcatSDK_GetQCLTemperature(c_uint8(x), byref(qclTemp))
                SDK.MIRcatSDK_GetTecCurrent(c_uint8(x), byref(tecCur))
                print('QCL {}: {:.2f} °C, {} mA. '.format(x, qclTemp.value,
                      tecCur.value), end='')
            print('', end='\r')
            SDK.MIRcatSDK_AreTECsAtSetTemperature(byref(atTemp))
        print()
        print('All TECs at temperature.')

    def sweep(self, wl_start_um, wl_end_um, wl_step_um):
        '''Sweep between two wavelengths using the laser's built-in function.
           Refer to MIRcat SDK documentation for details of the variables'''
        # Send sweep command
        wlUnit = MIRcatSDK_UNITS_MICRONS
        SDK.MIRcatSDK_StartSweepScan(c_float(wl_start_um),
                                     c_float(wl_end_um),
                                     c_float(wl_step_um),
                                     wlUnit, c_uint16(1), c_bool(False), c_uint8(0))
        # Check scan status
        isScanInProgress = c_bool(True)
        isScanActive = c_bool(False)
        isScanPaused = c_bool(False)
        curScanNum = c_uint16()
        curScanPercent = c_uint16()
        curWW = c_float()
        isTECinProgress = c_bool()
        isMotionInProgress = c_bool()
        units = wlUnit
        start = timer()
        while isScanInProgress.value:
            time.sleep(1)
            SDK.MIRcatSDK_GetScanStatus(byref(isScanInProgress),
                                        byref(isScanActive),
                                        byref(isScanPaused),
                                        byref(curScanNum),
                                        byref(curScanPercent),
                                        byref(curWW),
                                        byref(units),
                                        byref(isTECinProgress),
                                        byref(isMotionInProgress))
            print('Sweep in progress ({:.3f} s).'.format(timer()-start),
                                                        end=' ', flush=True)
            # print('Scan in progress/active/paused: {}/{}/{}'.format(
            #     isScanInProgress.value, isScanActive.value, isScanPaused.value))
            print('Sweep step {} ({} %).'.format(curScanNum.value, curScanPercent.value))
        print('Sweep complete ({} s).'.format(timer() - start))

    def sweep_and_forget(self, start, end, speed=0.5, units='um', qcl=0):
        '''Launch a sweep, but do not monitor it.
           Intended for use with a separate monitoring routine.
           :param start: Start wavelength (um) or wavenumber (cm^-1)
           :param end: End wavelength (um) or wavenumber (cm^-1)
           :param speed: Sweeping speed (um/s or cm^-1/s)
           :param units: "um" for um or "invcm" for cm^-1
           :param qcl: Preferred QCL module (1--4) or no preference (0)'''
        ### Give time for the routine to start the acquisition
        if units == 'invcm': # Wavenumbers in inverse cm
            wlUnits = MIRcatSDK_UNITS_CM1
        elif units == 'um': # Wavelenghts in microns
            wlUnits = MIRcatSDK_UNITS_MICRONS
        else:
            print('Unknown units {}, defaulting to micrometers.'.format(units))
            wlUnits = MIRcatSDK_UNITS_MICRONS
        SDK.MIRcatSDK_StartSweepScan(c_float(start), # Sweep start
                                     c_float(end),   # Sweep end
                                     c_float(speed), # Sweep speed
                                     wlUnits,        # Sweep units
                                     c_uint16(1),    # Iterations
                                     c_bool(False),  # Bidirectional
                                     c_uint8(qcl))   # Preferred QCL

    # def sweep_and_forget_um(self, wl_start_um, wl_end_um, wl_speed_ums=1.):
    #     '''Launch a sweep, but do not monitor it.
    #        Wavelength in microns.
    #        Intended for use with a separate monitoring routine.'''
    #     ### Send sweep command
    #     wlUnit = MIRcatSDK_UNITS_MICRONS
    #     SDK.MIRcatSDK_StartSweepScan(c_float(wl_start_um),
    #                                  c_float(wl_end_um),
    #                                  c_float(wl_speed_ums),
    #                                  wlUnit, c_uint16(1), c_bool(False),
    #                                  c_uint8(0))

    # def sweep_and_forget_invcm(self, wn_start_invcm, wn_end_invcm, wn_speed_invcms=1.):
    #     '''Launch a sweep, but do not monitor it.
    #        Wavenumber in inverse centimeters.
    #        Intended for use with a separate monitoring routine.'''
    #        ### Send sweep command
    #     wnUnit = MIRcatSDK_UNITS_CM1
    #     SDK.MIRcatSDK_StartSweepScan(c_float(wn_start_invcm),
    #                                  c_float(wn_end_invcm),
    #                                  c_float(wn_speed_invcms),
    #                                  wnUnit, c_uint16(1), c_bool(False),
    #                                  c_uint8(0))

    def tune(self, qcl, wl, wlUnits='um'):
        '''Tune QCL "qcl" wavelength to "wl", in units "wlUnits".
           Does not check for wavelength validity.
           Refer to MIRcat SDK documentation for details of the variables'''
        # Check QCL validity
        if qcl < 1 or qcl > self.numQcls.value:
            print('QCL {} invalid (choose 1--{}).'.format(qcl, self.numQcls))
            return
        # Set wavelength unit
        if wlUnits in ['um']:
            sdkWlUnits = MIRcatSDK_UNITS_MICRONS
            unitString = 'μm'
        elif wlUnits in ['invcm']:
            sdkWlUnits = MIRcatSDK_UNITS_CM1
            unitString = 'cm⁻¹'
        else:
            sdkWlUnits = MIRcatSDK_UNITS_MICRONS
            unitString = 'μm'
        # Send tune command
        SDK.MIRcatSDK_TuneToWW(c_float(wl), sdkWlUnits, c_uint8(qcl))
        # Check tune setting
        wlTune = c_float()
        units = c_uint8()
        qclTune = c_uint8()
        SDK.MIRcatSDK_GetTuneWW(byref(wlTune), byref(units), byref(qclTune))
        print('Tuning QCL {} to {:.3f} {}.'.format(qclTune.value, wlTune.value, unitString))
        # Verify tuning
        self.isTuned = c_bool(False)
        start = timer()
        while not self.isTuned.value:
            print('Tuning in progress ({:.3f} s).'.format(timer()-start),
                  end='\r') # overwrite line
            time.sleep(0.05) # refresh interval (DLS default: 0.05 s)
            SDK.MIRcatSDK_IsTuned(byref(self.isTuned))
        print() # clear line
        # Read tuned wavelength
        wlRead = self.get_wavelength()
        # print('Tuned QCL {} to {:.3f} {}.'.format(qclTune.value, wlRead, unitString))
        print('Tuned QCL {} to {:.3f} μm.'.format(qclTune.value, wlRead))


