'''
joystick_test
Giovanni Sartorello (srtgnn@gmail.com)
Software joystick test
Adapted from https://stackoverflow.com/a/55899694
Created 2022-Apr-06
'''

import sys
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QApplication, QGridLayout, QMainWindow, QWidget
from ui.software_joystick import Joystick


class mainWindow(QMainWindow):
    '''Application window.'''

    def __init__(self):
        super().__init__()
        ### Initialize stage
        self.stage = []
        self.threadJoy = QThread()
        self.workerJoy = Joystick()
        self.workerJoy.moveToThread(self.threadJoy)
        self.threadJoy.started.connect(self.workerJoy.return_self)
        self.workerJoy.joystickWidget.connect(self.make_ui)
        self.workerJoy.joystickInput.connect(self.print_input)
        self.threadJoy.finished.connect(self.threadJoy.deleteLater)
        self.threadJoy.start()

    def make_ui(self, joystickWidget):
        cw = QWidget()
        ml = QGridLayout()
        cw.setLayout(ml)
        self.setCentralWidget(cw)
        ml.addWidget(joystickWidget,0,0)
        self.show()

    def print_input(self, joystickInput):
        print(joystickInput)

if __name__ == '__main__':
    APP = QApplication(sys.argv)
    GUI0 = mainWindow()
    sys.exit(APP.exec_())