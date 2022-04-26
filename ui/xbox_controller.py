'''
gamepad
Giovanni Sartorello (srtgnn@gmail.com)
Read Xbox gamepad
Created 2022-Apr-14
Adapted from https://stackoverflow.com/a/66867816
'''

from inputs import get_gamepad
import math
import threading

class xboxController(object):
    MAX_TRIG_VAL = math.pow(2, 8)
    MAX_JOY_VAL = math.pow(2, 15)
    reading = True

    def __init__(self):
        self.LeftJoystickY = 0
        self.LeftJoystickX = 0
        self.LeftThumb = 0
        self.RightJoystickX = 0
        self.RightJoystickY = 0
        self.RightThumb = 0
        self.hatX = 0
        self.hatY = 0
        self.LeftTrigger = 0
        self.RightTrigger = 0
        self.LeftBumper = 0
        self.RightBumper = 0
        self.A = 0
        self.X = 0
        self.Y = 0
        self.B = 0
        self.Back = 0
        self.Start = 0
        # self.LeftDPad = 0
        # self.RightDPad = 0
        # self.UpDPad = 0
        # self.DownDPad = 0
        self._monitor_thread = threading.Thread(target=self._monitor_controller, args=())
        self._monitor_thread.daemon = True
        self._monitor_thread.start()

    def read(self): # return the buttons/triggers that you care about in this methode
        return[self.LeftJoystickX,
               self.LeftJoystickY,
               self.LeftThumb,
               self.RightJoystickX,
               self.RightJoystickY,
               self.RightThumb,
               self.hatX,
               self.hatY,
               self.A,
               self.B,
               self.X,
               self.Y,
               self.LeftBumper,
               self.RightBumper,
               self.LeftTrigger,
               self.RightTrigger,
               self.Back,
               self.Start]

    def stop(self):
        self.reading = False

    def _monitor_controller(self):
        '''These assignments are for the Xbox Core Controller'''
        while self.reading:
            events = get_gamepad()
            for event in events:
                if event.code == 'ABS_Y':
                    self.LeftJoystickY = event.state / self.MAX_JOY_VAL # normalize between -1 and 1
                elif event.code == 'ABS_X':
                    self.LeftJoystickX = event.state / self.MAX_JOY_VAL # normalize between -1 and 1
                elif event.code == 'ABS_RY':
                    self.RightJoystickY = event.state / self.MAX_JOY_VAL # normalize between -1 and 1
                elif event.code == 'ABS_RX':
                    self.RightJoystickX = event.state / self.MAX_JOY_VAL # normalize between -1 and 1
                elif event.code == 'ABS_Z':
                    self.LeftTrigger = event.state / self.MAX_TRIG_VAL # normalize between 0 and 1
                elif event.code == 'ABS_RZ':
                    self.RightTrigger = event.state / self.MAX_TRIG_VAL # normalize between 0 and 1
                elif event.code == 'BTN_TL':
                    self.LeftBumper = event.state
                elif event.code == 'BTN_TR':
                    self.RightBumper = event.state
                elif event.code == 'BTN_SOUTH':
                    self.A = event.state
                elif event.code == 'BTN_NORTH':
                    self.X = event.state
                elif event.code == 'BTN_WEST':
                    self.Y = event.state
                elif event.code == 'BTN_EAST':
                    self.B = event.state
                elif event.code == 'BTN_THUMBL':
                    self.LeftThumb = event.state
                elif event.code == 'BTN_THUMBR':
                    self.RightThumb = event.state
                elif event.code == 'BTN_SELECT':
                    self.Back = event.state
                elif event.code == 'BTN_START':
                    self.Start = event.state
                elif event.code == 'ABS_HAT0X':
                    self.hatX = event.state
                elif event.code == 'ABS_HAT0Y':
                    self.hatY = event.state
                # elif event.code == 'ABS_BTN_DPAD_LEFT':
                #     self.LeftDPad = event.state
                # elif event.code == 'BTN_DPAD_RIGHT':
                #     self.RightDPad = event.state
                # elif event.code == 'BTN_DPAD_UP':
                #     self.UpDPad = event.state
                # elif event.code == 'BTN_DPAD_DOWN':
                #     self.DownDPad = event.state