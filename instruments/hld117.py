'''
hld117
Giovanni Sartorello (srtgnn@gmail.com)
Prior Scientific HLD117 library
Created 2021-Nov-26 for Python 3.9.6 64-bit
'''

from ctypes import WinDLL, create_string_buffer
import os, sys, time
from inspect import currentframe, getfile
from os.path import abspath, join, split, realpath

### Look for modules in "instruments", https://stackoverflow.com/a/6098238
# mDir = realpath(abspath(split(getfile(currentframe()))[0]))
# if mDir not in sys.path:
#     sys.path.append(mDir)

### Look for modules in "prior"
# mSubdir = realpath(abspath(join(split(getfile(currentframe()))[0],'prior')))
# if mSubdir not in sys.path:
#     sys.path.append(mSubdir)

COM_PORT = 3 # Controller COM port
DLL_PATH = 'instruments/prior/PriorScientificSDK.dll' # Prior SDK DLL path

class stage():
    '''HLD117 stage class'''

    def __init__(self):
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

    def busy(self):
        '''Check whether stage is busy'''
        busy = self.message('controller.stage.busy.get')
        return busy[1]

    def connect(self):
        '''Connect controller'''
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
        # while self.busy() not in ['0']:
        #     time.sleep(0.1)
        self.message('controller.stage.goto-position {:.0f} {:.0f}'.format(x, y))

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
        else:
            self.message('controller.stage.joyxyz.off')

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
        return ret, self.rx.value.decode()

    # def servo(self, axes='both', enable=False):
    #     '''Enables servo function, which opposes forces applied to stage'''
    #     if enable:
    #         en = 1
    #     else:
    #         en = 0
    #     if axes in ['both', 'x']:
    #         encoder = self.message('controller.stage.encoder.x.enabled.get')
    #         if not encoder:
    #             print('Can\'t enable servo: axis x encoder not enabled')
    #             return
    #         self.message('controller.stage.servo.x.enabled.set {}'.format(en))
    #         _, enabled = self.message('controller.stage.servo.x.enabled.get')
    #         enabled = int(enabled)
    #         if enabled:
    #             print('Axis x servo enabled')
    #         else:
    #             print('Axis x servo disabled')
    #     if axes in ['both', 'y']:
    #         encoder = self.message('controller.stage.encoder.y.enabled.get')
    #         if not encoder:
    #             print('Can\'t enable servo: axis y encoder not enabled')
    #             return
    #         self.message('controller.stage.servo.y.enabled.set {}'.format(en))
    #         _, enabled = self.message('controller.stage.servo.y.enabled.get')
    #         enabled = int(enabled)
    #         if enabled:
    #             print(enabled)
    #             print('Axis y servo enabled')
    #         else:
    #             print('Axis y servo disabled')

    def reference(self):
        '''Move stage to reference position'''
        self.message('controller.stage.reference.set')

    # def center(self):
    #     '''Center stage'''
    #     self.message('controller.stage.position.set 0 0')
    #     self.message('controller.stage.position.get')



# def cmd(msg):
#     print(msg)
#     ret = SDKPrior.PriorScientificSDK_cmd(
#         sessionID, create_string_buffer(msg.encode()), rx
#     )
#     if ret:
#         print(f"Api error {ret}")
#     else:
#         print(f"OK {rx.value.decode()}")

#     input("Press ENTER to continue...")
#     return ret, rx.value.decode()


# ret = SDKPrior.PriorScientificSDK_Initialise()
# if ret:
#     print(f"Error initialising {ret}")
#     sys.exit()
# else:
#     print(f"Ok initialising {ret}")


# ret = SDKPrior.PriorScientificSDK_Version(rx)
# print(f"dll version api ret={ret}, version={rx.value.decode()}")


# sessionID = SDKPrior.PriorScientificSDK_OpenNewSession()
# if sessionID < 0:
#     print(f"Error getting sessionID {ret}")
# else:
#     print(f"SessionID = {sessionID}")


# ret = SDKPrior.PriorScientificSDK_cmd(
#     sessionID, create_string_buffer(b"dll.apitest 33 goodresponse"), rx
# )
# print(f"api response {ret}, rx = {rx.value.decode()}")
# input("Press ENTER to continue...")


# ret = SDKPrior.PriorScientificSDK_cmd(
#     sessionID, create_string_buffer(b"dll.apitest -300 stillgoodresponse"), rx
# )
# print(f"api response {ret}, rx = {rx.value.decode()}")
# input("Press ENTER to continue...")


# if realhw:
#     print("Connecting...")
#     # substitute 3 with your com port Id
#     cmd("controller.connect 3")

#     # test an illegal command
#     cmd("controller.stage.position.getx")

#     # get current XY position in default units of microns
#     cmd("controller.stage.position.get")

#     # re-define this current position as 1234,5678
#     cmd("controller.stage.position.set 1234 5678")

#     # check it worked
#     cmd("controller.stage.position.get")

#     # set it back to 0,0
#     cmd("controller.stage.position.set 0 0")
#     cmd("controller.stage.position.get")

#     # start a move to a new position, normally you would poll
#     # 'controller.stage.busy.get' until response = 0
#     cmd("controller.stage.goto-position 1234 5678")

#     # example velocity move of 10u/s in both x and y
#     cmd("controller.stage.move-at-velocity 10 10")

#     # see busy status
#     cmd("controller.stage.busy.get")

#     # stop velocity move
#     cmd("controller.stage.move-at-velocity 0 0")

#     # see busy status */
#     cmd("controller.stage.busy.get")

#     # see new position
#     cmd("controller.stage.position.get")

#     # disconnect cleanly from controller
#     cmd("controller.disconnect")

# else:
#     input("Press ENTER to continue...")