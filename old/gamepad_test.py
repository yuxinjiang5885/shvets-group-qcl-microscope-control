'''
gamepad_test
From https://stackoverflow.com/a/66867816
'''

from ui.xbox_controller import xboxController

if __name__ == '__main__':
    gamepad = xboxController()
    while True:
        print(gamepad.read())