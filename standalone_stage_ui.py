'''
standalone_stage_ui
Giovanni Sartorello (srtgnn@gmail.com)
Control HLD-117 stage only
Created 2022-Feb-03
'''

import os
import platform
import sys
import matplotlib as mpl
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams
import time
from timeit import default_timer as timer, timeit
# from experiment.defaults import *
import experiment.defaults as defaults
from experiment.routines_multithread import experiment
from experiment.laser_windows import (laserInitializer,
                                      laserSettingWindow,
                                      laserStartupDialog)
from experiment.stage_windows import (stageInitializer,
                                      stageMotionWindow,
                                      stageStartupDialog)
from ui.plot_widgets import mplCanvas
# from instruments.mircat import laser
from instruments.ni_daq import MultiChannelAnalogInput as MultiAI
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtGui import QIntValidator, QIcon, QFont, QWindow
from PyQt5.QtWidgets import (QAction,
                             QApplication,
                             QDesktopWidget,
                             QDialog,
                             QFileDialog,
                             QGridLayout,
                             QLabel,
                             QLineEdit,
                             QMainWindow,
                             QMessageBox,
                             QPushButton,
                             QWidget,
                             QSizePolicy,
                             QTextEdit,
                             QVBoxLayout)

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
        ### Create GUI
        # self.make_gui()
        ### Create window with stage motion controls
        self.stageMotionWindow = stageMotionWindow(self)
        ### Show stage motions control window
        self.stage_motion_window()

    def stage_motion_window(self):
        '''Multiple acquisitions menu'''
        self.stageMotionWindow.show()

    def stage_set(self, stageInstance):
        '''Set laser instance'''
        self.stage = stageInstance

if __name__ == '__main__':
    APP = QApplication(sys.argv)
    GUI0 = mainWindow()
    sys.exit(APP.exec_())
