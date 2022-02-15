'''
standalone_stage_ui
Giovanni Sartorello (srtgnn@gmail.com)
Control HLD-117 stage only
Created 2022-Feb-03
'''

import sys
import experiment.defaults as defaults
from experiment.stage_windows import (stageInitializer,
                                      stageMotionWindow,
                                      stageStartupDialog)
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import (QApplication,
                             QMainWindow)

class mainWindow(QMainWindow):
    '''Dummy application window.'''

    def __init__(self):
        super().__init__()
        ### Initialize stage
        self.stage = []
        self.threadStg = QThread()
        self.stageWorker = stageInitializer()
        self.stageWorker.moveToThread(self.threadStg)
        self.threadStg.started.connect(self.stageWorker.stage_initialize)
        self.stageWorker.stageInitialized.connect(self.threadStg.quit)
        self.stageWorker.stageInitialized.connect(self.stageWorker.deleteLater)
        self.stageWorker.stageInstance.connect(self.stage_set)
        self.threadStg.finished.connect(self.threadStg.deleteLater)
        self.threadStg.start()
        ### Show stage startup dialog
        startupDialog2 = stageStartupDialog() # Closes when startup finishes
        self.stageWorker.stageInitialized.connect(lambda: startupDialog2.done(0))
        startupDialog2.exec()
        ### Create window with stage motion controls
        self.stageMotionWindow = stageMotionWindow(self)
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
    sys.exit(APP.exec_())
