'''
hld117
Giovanni Sartorello (srtgnn@gmail.com)
Prior Scientific HLD117 library
Created 2021-Nov-26 for Python 3.9.6 64-bit
'''

from ctypes import WinDLL, create_string_buffer
import os, sys
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
            raise RuntimeError('DLL not found.')
        self.rx = create_string_buffer(1000)
        self.realHw = False
        ret = self.SDK.PriorScientificSDK_Initialise()
        if ret:
            print(f"Error initialising {ret}")
            sys.exit()
        else:
            print(f"Ok initialising {ret}")
        ret = self.SDK.PriorScientificSDK_Version(self.rx)
        print(f"dll version api ret={ret}, version={self.rx.value.decode()}")
        '''Open session'''
        self.session = self.SDK.PriorScientificSDK_OpenNewSession()
        if self.session < 0:
            print(f"Error getting sessionID {ret}")
        else:
            print(f"SessionID = {self.session}")
        '''API response tests'''
        ret = self.SDK.PriorScientificSDK_cmd(
            self.session, create_string_buffer(b"dll.apitest 33 goodresponse"), self.rx)
        print(f"api response {ret}, rx = {self.rx.value.decode()}")
        ret = self.SDK.PriorScientificSDK_cmd(
            self.session, create_string_buffer(b"dll.apitest -300 stillgoodresponse"), self.rx)
        print(f"api response {ret}, rx = {self.rx.value.decode()}")

    def connect(self):
        '''Connect controller'''
        self.message('controller.connect {:0f}'.format(COM_PORT))

    def disconnect(self):
        '''Disconnect controller'''
        self.message('controller.disconnect')

    def identify(self):
        '''Identify stage'''
        sn = self.message('controller.serialnumber.get')
        print('{}'.format(sn))

    def message(self, message):
        '''Send message to API, not to stage'''
        print('Sending: {}'.format(message))
        ret = self.SDK.PriorScientificSDK_cmd(
            self.session, create_string_buffer(message.encode()), self.rx)
        if ret:
            print('Failure to communicate: API error {}'.format(ret))
        # else:
        #     print('Success: {}'.format(self.rx.value.decode()))
        return ret, self.rx.value.decode()

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