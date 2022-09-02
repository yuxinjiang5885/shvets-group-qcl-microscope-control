#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
keithley
Giovanni Sartorello (srtgnn@gmail.com)
Control Keithley 2450 SMU via VISA. Commands are sent in TSP.
Created 2019-Feb-27 for Python 3.7.2
'''

from datetime import datetime
import time
import visa

# Default buffer parameters. See 2450 reference 3-13, 3-33.
BUFFER_FILL = 'buffer.FILL_CONTINUOUS'
BUFFER_NAME = 'BUFF'
BUFFER_SIZE = 100000 # Max 6875000 for standard style
BUFFER_STYLE = 'buffer.STYLE_STANDARD'
MAX_CURRENT = 1.05 # A
MAX_VOLTAGE = 210 # V
MIN_CURRENT = -1.05 # A
MIN_VOLTAGE = -210 # V

class SMU():
    '''Control Keithley 2450 SMU'''

    def __init__(self, instrAddress):
        '''Open instrument at address <instrAddress> using the PyVISA resource
        manger. Query *IDN? and print output. Check command set and switch to
        TSP if necessary. If TSP has to be set, instrument is closed, and should
        be manually rebooted.'''
        self.address = instrAddress
        rm = visa.ResourceManager()
        self.smu = rm.open_resource(instrAddress)
        rm = None
        self.id = self.smu.query('*IDN?')
        idStrip = self.id.rstrip()
        idString = idStrip.split(',')
        idString.append(self.address)
        print('Open: {0} {1} @ {4}\nS/N: {2}\nFirmware version: {3}'
              .format(*idString))
        self.startupLang = self.smu.query('*LANG?').rstrip()
        print('Command set: %s' % self.startupLang)
        if self.startupLang != 'TSP': # Then switch to TSP
            self.smu.write('*LANG TSP')
            self.switchLang = self.smu.query('*LANG?')
            print('Warning: switched to {}. Please reboot the instrument.'
                                              .format(self.switchLang.rstrip()))
            self.close()
            self.ready = False
        else:
            self.ready = True

    def beep(self, s, freq):
        '''Generate a tone with frequency <freq> for <s> seconds.'''
        self.smu.write('beeper.beep({0}, {1})'.format(s, freq))

    def close(self):
        '''Close instrument.'''
        self.smu.close()
        print('Closed: {}'.format(self.address))

    def datetimeinstr(self, *dateArgs):
        '''Set the instrument's date and time with six numeric <dateArgs>
        inputs: year, month, day, hour, minute, second. With no arguments,
        return current date and time.'''
        if not dateArgs:
            pass
        elif len(dateArgs) == 6:
            self.smu.write('localnode.settime({}, {}, {}, {}, {}, {})'
                                  .format(*dateArgs))
            print('Date and time copied to instrument from localhost.')
            time.sleep(.2) # issues when setting, then reading date too quickly
        else:
            self.warning(dateArgs, '(year, month, day, hour, minute, second)')
        self.smu.write('time = localnode.gettime()\nprint(time)')
        dateTimeUTC = int(self.smu.read())
        return datetime.utcfromtimestamp(dateTimeUTC).strftime(('%Y-%m-%d '
                                                                '%H:%M:%S'))

    def delete_buffer(self, bufferName):
        '''Delete buffer.'''
        self.smu.write('buffer.delete({})'.format(bufferName))

    def make_buffer(self, bufferName=BUFFER_NAME, bufferSize=BUFFER_SIZE,
                    bufferStyle=BUFFER_STYLE, bufferFill=BUFFER_FILL):
        '''Create buffer "bufferName" with size "bufferSize", style
           "bufferStyle" and fill mode "bufferFill"'''
        instruction = '{0} = buffer.make({1:d}, {2})'.format(bufferName,
                                                             bufferSize,
                                                             bufferStyle)
        self.smu.write(instruction)
        instruction = '{0}.fillmode = {1}'.format(bufferName, bufferFill)
        self.smu.write(instruction)

    def measure_autorange(self, autoRange=None):
        '''With <autoRange> "on" or "off", set autorange on/off for the active
        measure function. With no argument, return current setting.'''
        if autoRange is None:
            pass
        elif autoRange in [True, 'on', 'On', 'ON', 'y', 'Y', 'Yes', 'YES']:
            self.smu.write('smu.measure.autorange = smu.ON')
        elif autoRange in [False, 'off', 'Off', 'OFF', 'n', 'N', 'No', 'NO']:
            self.smu.write('smu.measure.autorange = smu.OFF')
        self.smu.write('print(smu.measure.autorange)')
        return self.smu.read().rstrip()

    def measure_function(self, measureFunc=None):
        '''Set the active measure function <measureFunc> as "current",
        "resistance", or "voltage". With no argument, return active setting.'''
        if measureFunc is None:
            pass
        elif measureFunc in ['current', 'Current', 'CURRENT']:
            self.smu.write('smu.measure.func = smu.FUNC_DC_CURRENT')
        elif measureFunc in ['resistance', 'Resistance', 'RESISTANCE']:
            self.smu.write('smu.measure.func = smu.FUNC_RESISTANCE')
        elif measureFunc in ['voltage', 'Voltage', 'VOLTAGE']:
            self.smu.write('smu.measure.func = smu.FUNC_DC_VOLTAGE')
        else:
            self.warning(measureFunc, '"current", "resistance" or "voltage"')
        self.smu.write('print(smu.measure.func)')
        return self.smu.read().rstrip()

    def measure_sense_mode(self, measureMode=None):
        '''Set the active measure mode <measureMode> as "2"-wire or "4"-wire.
        With no argument, return active setting.'''
        if measureMode is None:
            pass
        elif measureMode in [2, '2', '2-wire']:
            self.smu.write('smu.measure.sense = smu.SENSE_2WIRE')
        elif measureMode in [4, '4', '4-wire']:
            self.smu.write('smu.measure.sense = smu.SENSE_4WIRE')
        else:
            self.warning(measureMode, '"2" or "4"')
        self.smu.write('print(smu.measure.sense)')
        return self.smu.read().rstrip()

    def read_buffer(self, bufferName=BUFFER_NAME):
        '''Read last item in current buffer.'''
        self.smu.write('print(smu.measure.read({}))'.format(bufferName))
        return float(self.smu.read().rstrip())

    def read_output(self):
        '''Directly read instrument output'''
        return self.smu.read().rstrip()

    def reset(self):
        '''Reset commands to their default settings and clear buffers.'''
        self.smu.write('reset()')

    def source_function(self, sourceFunc=None):
        '''Set the active source function <sourceFunc> as "current", or
        "voltage". With no argument, return active setting.'''
        if sourceFunc is None:
            pass
        elif sourceFunc in ['current', 'Current', 'CURRENT']:
            self.smu.write('smu.source.func = smu.FUNC_DC_CURRENT')
        elif sourceFunc in ['voltage', 'Voltage', 'VOLTAGE']:
            self.smu.write('smu.source.func = smu.FUNC_DC_VOLTAGE')
        else:
            self.warning(sourceFunc, '"current" or "voltage"')
        self.smu.write('print(smu.source.func)')
        return self.smu.read().rstrip()

    def source_level(self, sourceLevel=None):
        '''Set the active source function's level.
        "voltage". With no argument, return active setting as float.'''
        # Find out which source function is currently set
        sourceFunc = self.source_function()
        if sourceLevel is None:
            pass
        elif sourceFunc == 'smu.FUNC_DC_CURRENT':
            if MIN_CURRENT <= sourceLevel <= MAX_CURRENT:
                self.smu.write('smu.source.level = {}'.format(sourceLevel))
            else:
                self.warning(sourceLevel, ('a current between {} and {} A)')
                                              .format(MIN_CURRENT, MAX_CURRENT))
        elif sourceFunc == 'smu.FUNC_DC_VOLTAGE':
            if MIN_VOLTAGE <= sourceLevel <= MAX_VOLTAGE:
                self.smu.write('smu.source.level = {}'.format(sourceLevel))
            else:
                self.warning(sourceLevel, ('a voltage between {} and {} A)')
                                              .format(MIN_VOLTAGE, MAX_VOLTAGE))
        else:
            self.warning(sourceLevel, ('a voltage between {} and {} V, or a '
                                       'current between {} and {} A').format(
                            MIN_VOLTAGE, MAX_VOLTAGE, MIN_CURRENT, MAX_CURRENT))
        self.smu.write('print(smu.source.level)')
        return float(self.smu.read().rstrip())

    def source_output(self, switchOn=None):
        '''Turn source output on/off if "on" is True/False. With no argument,
        return active setting.'''
        if switchOn is None:
            pass
        elif switchOn in ['on', 'On', 'ON']:
            self.smu.write('smu.source.output = smu.ON')
        elif switchOn in ['off', 'Off', 'OFF']:
            self.smu.write('smu.source.output = smu.OFF')
        else:
            self.warning(switchOn, '"on" or "off"')
        self.smu.write('print(smu.source.output)')
        return self.smu.read().rstrip()

    def terminals(self, terminals):
        '''Switch to set of <terminals> "front" or "rear". With no argument,
        return active setting.'''
        if not terminals:
            pass
        elif terminals in ['front', 'Front', 'FRONT']:
            self.smu.write('smu.measure.terminals = smu.TERMINALS_FRONT')
        elif terminals in ['rear', 'Rear', 'REAR']:
            self.smu.write('smu.measure.terminals = smu.TERMINALS_REAR')
        else:
            self.warning(terminals, '"front" or "rear"')
        self.smu.write('print(smu.measure.terminals)')
        return self.smu.read().rstrip()

    def warning(self, inputPar, correct):
        '''Print a warning that <input> is incorrect, and "correct" should be
        used instead.'''
        print('Warning: input {} incorrect. Use {}.'.format(inputPar, correct))

    def write_command(self, commandString):
        '''Write "commandString" to instrument directly'''
        self.smu.write(commandString)
