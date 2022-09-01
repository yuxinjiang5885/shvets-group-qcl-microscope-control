'''
hld117
Giovanni Sartorello (srtgnn@gmail.com)
Prior Scientific HLD117 library
Created 2021-Nov-26 for Python 3.9.6 64-bit
'''

from ctypes import WinDLL, create_string_buffer
import os, sys, time
from experiment import defaults

### Look for modules in "instruments", https://stackoverflow.com/a/6098238
# mDir = realpath(abspath(split(getfile(currentframe()))[0]))
# if mDir not in sys.path:
#     sys.path.append(mDir)

### Look for modules in "prior"
# mSubdir = realpath(abspath(join(split(getfile(currentframe()))[0],'prior')))
# if mSubdir not in sys.path:
#     sys.path.append(mSubdir)

DLL_PATH = 'instruments/prior/PriorScientificSDK.dll' # Prior SDK DLL path

'''Stage parameters'''

### HLD117
HLD117_DEFAULT_SPEED = defaults.HLD117_MAX_SPEED # Default stage speed, um/s
HLD117_DEFAULT_ACC = defaults.HLD117_MAX_ACC # Default stage acceleration, um/s^2
HLD117_SPEEDS = [10, 100, 1000, 10000, defaults.HLD117_MAX_SPEED] # Select stage speeds, um/s
HLD117_ACCS = [defaults.HLD117_MAX_ACC] # Select stage accelerations, um/s^2

### H117
H117_DEFAULT_SPEED = defaults.H117_MAX_SPEED # Default stage speed, um/s
H117_DEFAULT_ACC = defaults.H117_MAX_ACC # Default stage acceleration, um/s^2
H117_SPEEDS = [10, 100, 1000, 10000, defaults.H117_MAX_SPEED] # Select stage speeds, um/s
H117_ACCS = [defaults.H117_MAX_ACC] # Select stage accelerations, um/s^2

### Common
STEPS = [10, 100, 1000, 10000] # Select stage steps, um

class stage():
    '''HLD117 stage class'''

    def __init__(self, model = 'HLD117'):
        '''Initialize Prior SDK DLL'''
        if os.path.exists(DLL_PATH):
            self.SDK = WinDLL(DLL_PATH)
        else:
            raise RuntimeError('Stage controller DLL not found.')
        self.rx = create_string_buffer(1000)
        self.realHw = False
        ret = self.SDK.PriorScientificSDK_Initialise()
        if ret:
            print('Could not initialize stage controller: {}'.format(ret))
            sys.exit()
        else:
            print('Stage controller initialized ({})'.format(ret))
        self.SDK.PriorScientificSDK_Version(self.rx)
        ver = self.rx.value.decode()
        print('Stage controller SDK version {}'.format(ver))
        '''Open session'''
        self.session = self.SDK.PriorScientificSDK_OpenNewSession()
        if self.session < 0:
            print('Could not get stage controller session ID: {}'.format(ret))
        else:
            print('Stage controller session ID: {}'.format(self.session))
        '''API response tests'''
        # ret = self.SDK.PriorScientificSDK_cmd(
        #     self.session, create_string_buffer(b"dll.apitest 33 goodresponse"), self.rx)
        # print(f"api response {ret}, rx = {self.rx.value.decode()}")
        # ret = self.SDK.PriorScientificSDK_cmd(
        #     self.session, create_string_buffer(b"dll.apitest -300 stillgoodresponse"), self.rx)
        # print(f"api response {ret}, rx = {self.rx.value.decode()}")
        '''Stage parameters'''
        if model in ['H117', 'h117']:
            self.defaultSpeed = H117_DEFAULT_SPEED
            self.defaultAcc = H117_DEFAULT_ACC
            self.speeds = H117_SPEEDS
            self.steps = STEPS
            self.accs = H117_ACCS
        else:
            self.defaultSpeed = HLD117_DEFAULT_SPEED
            self.defaultAcc = HLD117_DEFAULT_ACC
            self.speeds = HLD117_SPEEDS
            self.steps = STEPS
            self.accs = HLD117_ACCS

    def busy(self):
        '''Check whether stage is busy:
           “0” idle, “1” X moving, “2” Y moving, “3” both X&Y moving'''
        busy = self.message('controller.stage.busy.get')
        return busy[1]

    def connect(self, COM_PORT = defaults.STAGE_DEF_COM_PORT):
        '''Connect controller'''
        print('Connecting to stage on COM port {}'.format(COM_PORT))
        self.message('controller.connect {:0f}'.format(COM_PORT))

    def disconnect(self):
        '''Disconnect controller'''
        self.message('controller.disconnect')

    # def encoder(self, axes='both', enable=True):
    #     '''Enable axis encoders (enables closed-loop operation)'''
    #     if enable:
    #         en = 1
    #     else:
    #         en = 0
    #     if axes in ['both', 'x']:
    #         _, fitted = self.message('controller.stage.encoder.x.fitted.get')
    #         fitted = int(fitted)
    #         if fitted:
    #             print('Axis x encoder fitted')
    #         else:
    #             print('Axis x encoder not fitted')
    #             return
    #         self.message('controller.stage.encoder.x.enabled.set {}'.format(en))
    #         enabled = self.message('controller.stage.encoder.x.enabled.get')
    #         if enabled:
    #             print('Axis x encoder enabled')
    #         else:
    #             print('Axis x encoder disabled')
    #     if axes in ['both', 'y']:
    #         _, fitted = self.message('controller.stage.encoder.y.fitted.get')
    #         fitted = int(fitted)
    #         if fitted:
    #             print('Axis y encoder fitted')
    #         else:
    #             print('Axis y encoder not fitted')
    #             return
    #         self.message('controller.stage.encoder.y.enabled.set {}'.format(en))
    #         _, enabled = self.message('controller.stage.encoder.y.enabled.get')
    #         enabled = int(enabled)
    #         if enabled:
    #             print('Axis y encoder enabled')
    #         else:
    #             print('Axis y encoder disabled')

    def get_acc(self):
        '''Get current stage maximum set acceleration'''
        acc = self.message('controller.stage.acc.get')
        return(float(acc[1]))

    def get_position(self):
        '''Get current stage position'''
        count = 0
        while self.busy() not in ['0']:
            time.sleep(0.1)
            count += 1
            if count > 50:
                print('Failed to get position: stage is still busy.')
                return(0, 0)
        position = self.message('controller.stage.position.get')
        (x,y) = position[1].split(',')
        return(float(x), float(y))

    def get_speed(self):
        '''Get current stage maximum set point-to-point movement speed'''
        speed = self.message('controller.stage.speed.get')
        return(float(speed[1]))

    def goto(self, x=0, y=0):
        '''Go to specified position.'''
        self.message('controller.stage.goto-position {:.1f} {:.1f}'.format(x, y))

    def identify(self):
        '''Identify controller'''
        _, model = self.message('controller.model.get')
        _, sn = self.message('controller.serialnumber.get')
        print('Stage controller: {} S/N {}'.format(model, sn))
        # _, name = self.message('controller.stage.name.get')
        # print('Stage: {} S/N {}'.format(name, sn))

    # def limits(self):
    #     '''Get stage limit switches status'''
    #     limits = self.message('controller.stage.limits.get')
    #     print(limits)

    def joystick(self, enable=True):
        '''Enable/disable joystick'''
        if enable:
            self.message('controller.stage.joyxyz.on')
            print('Stage joystick enabled')
        else:
            self.message('controller.stage.joyxyz.off')
            print('Stage joystick disabled')

    # def flag(self, flag):
    #     '''Controller shutdown check'''
    #     flag = self.message('controller.flag.get')
    #     if not flag:
    #         print('Controller was shut down since last use.')
    #     self.message('controller.flag.set 1')

    def message(self, message, verbose=False):
        '''Send message to API'''
        if verbose:
            print('Sending: {}'.format(message))
        ret = self.SDK.PriorScientificSDK_cmd(
            self.session, create_string_buffer(message.encode()), self.rx)
        if ret:
            print('Failure to communicate: API error {}'.format(ret))
        # else:
        #     print('Success: {}'.format(self.rx.value.decode()))
        return ret, self.rx.value.decode()\

    def move_at_velocity(self, vx=0, vy=0):
        '''Move at constant velocity.'''
        self.message('controller.stage.move-at-velocity {:.0f} {:.0f}'.format(vx, vy))

    def move_rel(self, x=0, y=0):
        '''Move relative to current position.'''
        self.message('controller.stage.move-relative {:.1f} {:.1f}'.format(x, y))

    def reference(self):
        '''Move stage to reference position'''
        self.message('controller.stage.reference.set')

    def set_acc(self, a = 0):
        '''Set the maximum acceleration during a point to point move
           or velocity move'''
        if a == 0:
            a = self.defaultAcc
            print('Switched to default acceleration')
        self.message('controller.stage.acc.set {:.0f}'.format(a))

    def set_speed(self, v = 0):
        '''Set the maximum speed during a point to point move'''
        if v == 0:
            v = self.defaultSpeed
            print('Switched to default velocity')
        self.message('controller.stage.speed.set {:.0f}'.format(v))

    def stop_smoothly(self):
        '''Stop stage smoothly, maintaining positional accuracy.'''
        self.message('controller.stop.smoothly')
