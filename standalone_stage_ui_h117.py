'''
standalone_stage_ui_h117
Giovanni Sartorello (srtgnn@gmail.com)
Control H117 stage only
Created 2022-Sep-01
'''

import sys
import experiment.defaults as defaults
from ui.stage_windows import (stageInitializer, stageMotionWindow, stageStartupDialog)
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import (QApplication, QMainWindow)

MODEL = 'H117'
COM_PORT = defaults.H117_COM_PORT

class mainWindow(QMainWindow):
    '''Dummy application window.'''

    def __init__(self):
        super().__init__()
        ### Dummy variable, expected by the stage UI from the full QCL/stage UI
        self.stagePlotCanvas = []
        ### Initialize stage
        self.stage = []
        self.threadStg = QThread()
        self.stageWorker = stageInitializer(MODEL = MODEL, COM_PORT = COM_PORT)
        self.stageWorker.moveToThread(self.threadStg)
        self.threadStg.started.connect(self.stageWorker.stage_initialize)
        self.stageWorker.stageInitialized.connect(self.stageWorker.deleteLater)
        self.stageWorker.stageInstance.connect(self.stage_set)
        self.threadStg.finished.connect(self.threadStg.deleteLater)
        self.threadStg.start()
        ### Show stage startup dialog
        startupDialog2 = stageStartupDialog(COM_PORT = COM_PORT) # Closes when startup finishes
        self.stageWorker.stageInitialized.connect(lambda: startupDialog2.done(0))
        startupDialog2.exec()
        ### Connection check: WIP
        # if not connected:
        #     print('Could not connect to stage.')
        #     print('Is the COM port in "h117.py" correct?', end = '')
        #     print('Available ports are listed in Device Manager.')
        #     return
        ### Create window with stage motion controls
        self.stageMotionWindow = stageMotionWindow(mainGUI = self, model = MODEL)
        ### Show stage motions control window
        self.stage_motion_window()

    def stage_motion_window(self):
        '''Show actual stage motion control window'''
        self.stageMotionWindow.show()

    def stage_set(self, stageInstance):
        '''Set stage instance'''
        self.stage = stageInstance

if __name__ == '__main__':
    APP = QApplication(sys.argv)
    GUI0 = mainWindow()
    sys.exit(APP.exec())
