'''
qcl_spectral_scan_ui_multithread
Giovanni Sartorello (srtgnn@gmail.com)
UI for QCL scanning spectroscopy experiments
Multi-threaded version of "qcl_spectral_scan_ui"
Python 3.9.6 on Windows 10
Created 2021-Mar-03
'''

import os
import sys
import re
import matplotlib as mpl
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import rcParams
import numpy as np
import experiment.defaults as defaults
from experiment.routines_multithread import experiment, imagingScan
from ui.laser_windows import (laserInitializer,
                              laserSettingWindow,
                              laserStartupDialog)
from ui.stage_windows import (stageInitializer,
                              stageMotionWindow,
                              stageStartupDialog)
from ui.scan_windows import scanBrowser
from ui.plot_widgets import mplCanvas
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QThread
from PyQt6.QtGui import QAction, QIcon, QFont
from PyQt6.QtWidgets import (QApplication,
                             QComboBox,
                             QGridLayout,
                             QLabel,
                             QLineEdit,
                             QMainWindow,
                             QMessageBox,
                             QPushButton,
                             QSlider,
                             QWidget,
                             QSizePolicy,
                             QTabWidget,
                             QTextEdit)
rcParams.update({'figure.autolayout': True}) # Essential for plots to fit figure


class experimentParameters():
    '''Holds experiment parameters'''

    def __init__(self):
        self.acquisitions = 0 # Number of acquisitions
        self.acq_time_interval_s = 300 # Interval between acquisitions, s
        self.end = 100 # Placeholder value, no unit
        self.laser = [] # Placeholder value
        self.latestDir = 0 # Latest experiment directory, placeholder value
        self.notes = [] # Placeholder value
        self.qcl = [] # QCL modules to be used, placeholder value
        self.ranges = [] # Placeholder value
        self.refDir = '' # Reference experiment directory
        self.reference = np.zeros((1, 2)) # Placeholder value
        self.sampleNumber = defaults.DEF_SAMPLES
        self.sampleRate = defaults.DEF_SAMPLERATE
        self.speed = 1 # Placeholder value, no unit
        self.start = 0 # Placeholder value, no unit
        self.step = 1 # Placeholder value, no unit
        self.sweeping = True # By default, use the sweep routine
        self.sweepLimits = [] # Placeholder value
        self.units = 'um' # By default, wavelengths in micrometers
        self.useRef = False # By default, do not use reference


class hyperspectralSlice():
    '''Holds a wavelength slice of scanning imaging data'''

    def __init__(self):
        self.wavelength = 0
        self.X = []
        self.Y = []
        self.Z = []


class mainWindow(QMainWindow):
    '''Main application window and instrument controls.'''

    def __init__(self):
        super().__init__()
        ### Initialize laser
        self.laser = []
        self.threadLas = QThread()
        self.laserWorker = laserInitializer()
        self.laserWorker.moveToThread(self.threadLas)
        self.threadLas.started.connect(self.laserWorker.laser_initialize)
        self.laserWorker.laserInitialized.connect(self.threadLas.quit)
        self.laserWorker.laserInitialized.connect(self.laserWorker.deleteLater)
        self.laserWorker.laserInstance.connect(self.laser_set)
        self.threadLas.finished.connect(self.threadLas.deleteLater)
        self.threadLas.start()
        ### Show laser startup dialog
        startupDialog = laserStartupDialog() # Closes when startup finishes
        self.laserWorker.laserInitialized.connect(lambda: startupDialog.done(0))
        startupDialog.exec()
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
        ### Prepare text for "about" dialog
        try:
            self.aboutText = ''
            aboutFile = 'docs/mircat_ui_multithread_about.html'
            with open(aboutFile) as f:
                self.aboutText = f.read()
        except Exception as exc:
            print('Failed to load "about" contents:\n{}'.format(exc))
        ### Set class parameters to be passed to run and repeat routines
        self.parameters = experimentParameters()
        self.scanImagParameters = scanningImagingParameters()
        # self.useRef = False # By default, do not use reference
        self.wlUnits = 'um' # Wavelength/number units
        ### Thread and worker placeholders
        # self.thread = [] # Placeholder for last-used thread
        # self.worker = [] # Placeholder for last-used worker
        ### Create GUI
        self.make_gui()
        ### Create separate windows for multiple acquisitions, laser and stage
        self.laserMenu = laserSettingWindow(self)
        self.multiMenu = multipleAcquisitionsWindow(self)
        self.multiMenu.btn['Start'][0].clicked.connect(lambda: self.multiple())
        self.stageMotionWindow = stageMotionWindow(self)
        self.statusbar.showMessage('Ready')

    def about(self):
        '''Show dialog when "about" is clicked.'''
        QMessageBox.about(self, 'About', self.aboutText)

    def arm(self):
        '''Arm or disarm laser laser'''
        self.lock_controls(lock=True)
        self.statusbar.showMessage('Busy')
        self.repaint()
        if self.btn['Arm'][0].isChecked():
                if self.activeQcl == 0:
                    self.statusbar.showMessage('No QCL selected',
                                               defaults.MSG_TIMEOUT)
                    self.btn['Arm'][0].setChecked(False)
                    self.lock_controls(lock=False)
                    return
                else:
                    self.btn['Arm'][0].setText('Arming ...')
                    self.statusbar.showMessage('Arming ...')
                    # Always stabilize after arming and before tuning
                    self.laser.arm()
                    self.laser.stabilize()
                    self.btn['Arm'][0].setText('DISARM')
                    self.update_qcl_reading(self.activeQcl)
        else:
            if self.btn['Emission'][0].isChecked():
                # If laser is still emitting, disable it first
                self.btn['Emission'][0].setChecked(False)
                self.emission() # With button unchecked, this disables emission
            self.btn['Arm'][0].setText('Arm')
            self.laser.disarm()
        self.lock_controls(lock=False)
        self.statusbar.showMessage('Ready')

    def center_window(self):
        '''Center main application window on screen'''
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def closeEvent(self, event): # Redefined from parent QMainWindow
        '''Show warning dialog on close.'''
        self.stage.disconnect()
        event.accept()
        # reply = QMessageBox.question(self, 'Quit confirmation',
        #                              "Are you sure you want to quit?",
        #                              QMessageBox.Yes | QMessageBox.No,
        #                              QMessageBox.No)
        # if reply == QMessageBox.Yes:
        #     event.accept()
        #     self.laser.disable()
        #     self.laser.disarm()
        #     self.laser.disconnect()
        # else:
        #     event.ignore()

    def construct_pattern(self, xOrig = defaults.IMAG_SCAN_ORIGIN_X_UM,
                                yOrig = defaults.IMAG_SCAN_ORIGIN_Y_UM,
                                xSizeN = defaults.IMAG_SCAN_SIZE_X_UM,
                                ySizeN = defaults.IMAG_SCAN_SIZE_Y_UM,
                                xStep = defaults.IMAG_SCAN_STEP_X_UM,
                                yStep = defaults.IMAG_SCAN_STEP_Y_UM,
                                invert = 'even'):
        '''Construct raster pattern for scanning imaging'''
        patternx = []
        indexx = []
        patterny = []
        indexy = []
        for xs in range(0, xSizeN):
            if (invert in ['even', 'Even'] and (xs % 2 == 0)) or \
               (invert in ['odd', 'Odd'] and (xs % 2 == 0)):
                yRange = range(ySizeN - 1, -1, -1)
            else:
                yRange = range(0, ySizeN)
            for ys in yRange:
                x = xs * xStep + xOrig
                y = ys * yStep + yOrig
                patternx.append(x)
                indexx.append(xs)
                patterny.append(y)
                indexy.append(ys)
        return(np.transpose(np.array((patternx, patterny))),
               np.transpose(np.array((indexx, indexy))))

    def emission(self):
        '''Enable or disable laser emission.'''
        self.lock_controls(lock=True)
        if self.btn['Emission'][0].isChecked():
            if not self.btn['Arm'][0].isChecked():
                self.btn['Emission'][0].setChecked(False)
                self.statusbar.showMessage('Not armed', defaults.MSG_TIMEOUT)
            else:
                self.btn['Emission'][0].setText('DISABLE')
                self.laser.enable()
        else:
            self.btn['Emission'][0].setText('Enable')
            self.laser.disable()
        self.lock_controls(lock=False)

    def laser_off(self):
        '''Turn laser off.'''
        pass

    def laser_set(self, laserInstance):
        '''Set laser instance'''
        self.laser = laserInstance

    def laser_settings_menu(self):
        '''Multiple acquisitions menu'''
        self.laserMenu.show()
        self.laserMenu.update_readings()

    def lock_controls(self, lock=True):
        '''Disable all buttons while operations are performed.'''
        enabled = not lock # For the sake of clarity
        for _, k in self.btn.items():
            k[0].setEnabled(enabled)

    def make_gui(self):
        '''Create main GUI window.'''
        self.setGeometry(0, 0, 1200, 900)
        self.center_window()
        font = QFont()
        font.setFamily(defaults.FONT_FAMILY)
        font.setPointSize(defaults.FONT_SIZE_MEDIUM)
        # self.setWindowModality(Qt.ApplicationModal)
        ### Set title and icon
        self.setWindowTitle('QCL Scanning and Imaging UI')
        self.setWindowIcon(QIcon('icons/mircat.ico'))
        ### Create bars
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(defaults.STYLE_MENUBAR)
        self.statusbar = self.statusBar()
        self.statusbar.setStyleSheet(defaults.STYLE_STATUSBAR)
        self.statusbar.showMessage('Initializing ...')
        ### "Actions" menu
        exitAction = QAction(QIcon(None), 'Quit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.setStatusTip('Quit application')
        exitAction.triggered.connect(lambda: self.close())
        changeUnits = QAction(QIcon(None), 'Change units', self)
        changeUnits.setShortcut('Ctrl+U')
        changeUnits.setStatusTip('Change units')
        changeUnits.triggered.connect(lambda: self.wl_units())
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.setStyleSheet(defaults.STYLE_MENU)
        fileMenu.addAction(exitAction)
        fileMenu.addAction(changeUnits)
        ### "Laser" menu
        laserSettings = QAction(QIcon(None), 'Laser settings', self)
        laserSettings.setShortcut('Ctrl+L')
        laserSettings.setStatusTip('Quit application')
        laserSettings.triggered.connect(lambda: self.laser_settings_menu())
        laserOff = QAction(QIcon(None), 'Laser off', self)
        laserOff.setShortcut('Ctrl+Alt+O')
        laserOff.setStatusTip('Power down laser (Not Implemented)')
        laserOff.triggered.connect(lambda: print('Action not implemented'))
        laserMenu = self.menubar.addMenu('Laser')
        laserMenu.setStyleSheet(defaults.STYLE_MENU)
        laserMenu.addAction(laserSettings)
        laserMenu.addAction(laserOff)
        ### "Multiple" menu
        multipleMenu = self.menubar.addMenu('Multiple')
        multipleMenu.setStyleSheet(defaults.STYLE_MENU)
        multipleAcqMenu = QAction(QIcon(None), 'Timed multiple acquisitions', self)
        multipleAcqMenu.setShortcut('Ctrl+M')
        multipleAcqMenu.setStatusTip('Open timed multiple acquisitions window')
        multipleMenu.addAction(multipleAcqMenu)
        multipleAcqMenu.triggered.connect(lambda: self.multiple_acq_menu())
        ### "Stage" menu
        stageMenu = self.menubar.addMenu('Stage')
        stageMenu.setStyleSheet(defaults.STYLE_MENU)
        stageMotion = QAction(QIcon(None), 'Stage motion', self)
        stageMotion.setShortcut('Ctrl+S')
        stageMotion.setStatusTip('Open stage motion window')
        stageMenu.addAction(stageMotion)
        stageMotion.triggered.connect(lambda: self.stage_motion_window())
        ### "Options" menu
        optionsMenu = self.menubar.addMenu('Options')
        optionsMenu.setStyleSheet(defaults.STYLE_MENU)
        self.repeatShow = QAction(QIcon(None),
                          'Plot data when using "Repeat"', self, checkable=True)
        self.repeatShow.setChecked(True) # Checked by default
        self.repeatShow.setStatusTip('Update plots when using "Repeat"')
        optionsMenu.addAction(self.repeatShow)
        self.darkMode = QAction(QIcon(None), 'Dark mode', self, checkable=True, checked=True)
        self.darkMode.setShortcut('Ctrl+D')
        self.darkMode.setStatusTip('Dark mode for plots')
        optionsMenu.addAction(self.darkMode)
        self.darkMode.triggered.connect(lambda: self.plot_dark_mode())
        ### "About" menu
        aboutAction = QAction(QIcon(None), 'About', self)
        aboutAction.setStatusTip('About')
        aboutAction.triggered.connect(self.about)
        helpMenu = self.menubar.addMenu('Help')
        helpMenu.setStyleSheet(defaults.STYLE_MENU)
        helpMenu.addAction(aboutAction)
        ### Configure main grid layout for tabs widget
        self.container = QWidget()
        self.container.setStyleSheet(defaults.STYLE_CONTAINER)
        self.setCentralWidget(self.container)
        self.grid = QGridLayout()
        self.container.setLayout(self.grid)
        self.grid.setSpacing(10)
        ### Tabs widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(defaults.STYLE_TABS)
        self.tabs.setFont(font)
        self.grid.addWidget(self.tabs, 0, 0, 1, 1)
        ### Single acquisition tab - Base layout
        self.tabSingle = QWidget()
        self.tabSingle.setStyleSheet(defaults.STYLE_CONTAINER)
        self.tabs.addTab(self.tabSingle, 'Single')
        ### Single acquisition tab - Grid layouy
        # self.containerSingle = QWidget()
        # self.containerSingle.setStyleSheet(defaults.STYLE_CONTAINER)
        # self.grid.addWidget(self.stgControls, 0, 0, 1, 1)
        # self.setCentralWidget(self.containerSingle)
        self.tabSingleGrid = QGridLayout()
        # self.containerSingle.setLayout(self.tabSingleGrid)
        self.tabSingle.setLayout(self.tabSingleGrid)
        self.tabSingleGrid.setSpacing(10)
        for row in range(0, defaults.NUMBER_OF_ROWS): # Set row spacing
            # self.tabSingleGrid.setRowMinimumHeight(row, ROW_HEIGHT)
            if row in [0]:
                self.tabSingleGrid.setRowStretch(row, 8)
            else:
                self.tabSingleGrid.setRowStretch(row, 1)
        for col in range(0, defaults.NUMBER_OF_COLS): # Set column spacing
            if col in [1, 3, 5]: # QCL settings
                self.tabSingleGrid.setColumnStretch(col, 2)
            if col in [2, 4, 6]: # Scl setting labels
                self.tabSingleGrid.setColumnStretch(col, 1)
            # elif col in [3]:
            #     self.tabSingleGrid.setColumnStretch(col, 4)
            else:
                self.tabSingleGrid.setColumnStretch(col, 20)
        ### Plot: latest spectrum
        self.plotCanvas = mplCanvas(width=4, height=3)
        self.plotCanvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.plotCanvas.axes.set_xlabel('Wavelength (μm)')
        self.plotCanvas.axes.set_ylabel('Lock-in Mag. (V)')
        self.plotCanvas.axes.set_title('Latest Spectrum')
        self.tabSingleGrid.addWidget(self.plotCanvas, 0, 0, 1, 5)
        ### Plot: current reference
        self.plotCanvasRef = mplCanvas(width=4, height=3)
        self.plotCanvasRef.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.plotCanvasRef.axes.set_xlabel('Wavelength (μm)')
        self.plotCanvasRef.axes.set_ylabel('Lock-in Mag. (V)')
        self.plotCanvasRef.axes.set_title('Current Reference')
        self.tabSingleGrid.addWidget(self.plotCanvasRef, 0, 5, 1, 3)
        ### Plot: transmittance
        self.plotCanvasT = mplCanvas(width=4, height=3)
        self.plotCanvasT.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.plotCanvasT.axes.set_xlabel('Wavelength (μm)')
        self.plotCanvasT.axes.set_ylabel('Transmittance')
        self.plotCanvasT.axes.set_title('Transmittance (Latest/Reference)')
        self.tabSingleGrid.addWidget(self.plotCanvasT, 0, 8, 1, 3)
        ### Make dark mode for plots default
        self.plot_dark_mode()
        ### Buttons: select QCL, laser arm, tune, enable emission
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['QCL1'] = [QPushButton('QCL 1 Off'), 2, 0, 2, 1]
        self.btn['QCL1'][0].setToolTip('Select QCL module 1')
        self.btn['QCL2'] = [QPushButton('QCL 2 Off'), 4, 0, 2, 1]
        self.btn['QCL2'][0].setToolTip('Select QCL module 2')
        self.btn['QCL3'] = [QPushButton('QCL 3 Off'), 6, 0, 2, 1]
        self.btn['QCL3'][0].setToolTip('Select QCL module 3')
        self.btn['QCL4'] = [QPushButton('QCL 4 Off'), 8, 0, 2, 1]
        self.btn['QCL4'][0].setToolTip('Select QCL module 4')
        # self.btn['WlUnits'] = [QPushButton('Units: μm'), 10, 5, 2, 1]
        # self.btn['WlUnits'][0].setToolTip('Switch wavelength units')
        self.btn['Tune'] = [QPushButton('Tune'), 4, 7, 2, 1]
        self.btn['Tune'][0].setToolTip(
                          'Tune laser to displayed wavelength for selected QCL')
        self.btn['Arm'] = [QPushButton('Arm'), 2, 7, 2, 1]
        self.btn['Arm'][0].setToolTip('Arm/Disarm laser')
        self.btn['Emission'] = [QPushButton('Enable'), 6, 7, 2, 1]
        self.btn['Emission'][0].setToolTip('Enable/disable laser emission')
        ### Buttons: reference
        self.btn['RefEnable'] = [QPushButton('Reference'), 10, 7, 2, 1]
        self.btn['RefEnable'][0].setToolTip('Enable/disable use of reference')
        self.btn['RefSet'] = [QPushButton('Set Reference'), 11, 8, 1, 1]
        self.btn['RefSet'][0].setToolTip('Set latest spectrum as reference')
        self.btn['RefSave'] = [QPushButton('Save Reference'), 11, 9, 1, 1]
        self.btn['RefSave'][0].setToolTip('Save latest spectrum path for later')
        self.btn['RefRecall'] = [QPushButton('Recall Reference'), 11, 10, 1, 1]
        self.btn['RefRecall'][0].setToolTip(
                              'Recall saved spectrum path and set as reference')
        ### Buttons: start sweep, start scan, stop scan
        self.btn['Sweep'] = [QPushButton('Sweep'), 12, 8, 2, 1]
        self.btn['Sweep'][0].setToolTip('Start sweep')
        self.btn['Start'] = [QPushButton('Scan'), 12, 9, 2, 1]
        self.btn['Start'][0].setToolTip('Start step-and-measure scan')
        self.btn['Repeat'] = [QPushButton('Repeat'), 12, 10, 2, 1]
        self.btn['Repeat'][0].setToolTip('Repeat last scan or sweep')
        # self.btn['Stop'] = [QPushButton('Stop'), 12, 7, 2, 1]
        # self.btn['Stop'][0].setToolTip('Stop scan or sweep in progress')
        for x, k in self.btn.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            # k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            if x in ['QCL1', 'QCL2', 'QCL3', 'QCL4']:
                k[0].setStyleSheet(defaults.STYLE_BUTTON)
            elif x in ['WlUnits']:
                k[0].setStyleSheet(defaults.STYLE_BUTTON_UNIT)
            else:
                k[0].setStyleSheet(defaults.STYLE_ARMED)
            self.tabSingleGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Input fields: wavelength
        self.inputField = dict() # to collect all input fields
        startupText = [defaults.MIN_WL_QCL1_UM,
                       defaults.MIN_WL_QCL2_UM,
                       defaults.MIN_WL_QCL3_UM,
                       defaults.MIN_WL_QCL4_UM]
        for qcl in range(1, self.laser.numQCL + 1):
                row = qcl * 2 # odd rows starting at 2 (the third)
                fieldName = 'QCL{}SetWl'.format(qcl)
                fieldText = '{}'.format(startupText[qcl - 1])
                self.inputField[fieldName] = [QLineEdit(fieldText), row, 5, 1, 1]
        ### Input fields: experiment controls
        self.inputField['WlStart'] = [QLineEdit('{}'.format(
                                    defaults.DEF_WL_START_UM)), 3, 8, 1, 1]
        self.inputField['WlStart'][0].setToolTip('First scan wavelength')
        self.inputField['WlEnd'] = [QLineEdit('{}'.format(
                                    defaults.DEF_WL_END_UM)), 3, 9, 1, 1]
        self.inputField['WlEnd'][0].setToolTip('Last scan wavelength')
        self.inputField['WlStep'] = [QLineEdit('{}'.format(
                                    defaults.DEF_WL_STEP_UM)), 3, 10, 1, 1]
        self.inputField['WlStep'][0].setToolTip('Scan wavelength step')
        self.inputField['SamplingRate'] = [QLineEdit('{}'.format(
                                    defaults.DEF_SAMPLERATE)), 9, 8, 1, 1]
        self.inputField['SamplingRate'][0].setToolTip(
                                    'Acquisition card sampling rate')
        self.inputField['SamplesPerWl'] = [QLineEdit('{}'.format(
                                    defaults.DEF_SAMPLES)), 9, 9, 1, 1]
        self.inputField['SamplesPerWl'][0].setToolTip(
                                    'Voltage points per wavelength/number step')
        self.inputField['Speed'] = [QLineEdit('{}'.format(
                                    defaults.MAX_SWEEP_SPEED_UM)), 9, 10, 1, 1]
        self.inputField['Speed'][0].setToolTip('Sweep speed')
        ### Input fields: reference
        self.inputField['RefPath'] = [QLineEdit('C:\\Data\\_experiment_data'),
                                    10, 8, 1, 3]
        ### Create all input fields
        for _, k in self.inputField.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.tabSingleGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Labels: headers, in a dict for ease of positioning
        self.labelHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelHead['QCLMod'] = [QLabel('QCL Modules'), 1, 0, 1, 1]
        # self.labelHead['QCLCurr'] = [QLabel('QCL Currents'), 1, 1, 1, 4]
        self.labelHead['QCLWav'] = [QLabel('QCL Wavelengths'), 1, 5, 1, 2]
        self.labelHead['LasControls'] = [QLabel(
                          'Laser/Experiment Settings and Controls'), 1, 7, 1, 4]
        self.labelHead['Notes'] = [QLabel('Experiment Notes'), 11, 0, 1, 1]
        for _, k in self.labelHead.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.tabSingleGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: experiment controls sub-headers
        self.labelSubHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelSubHead['WlStart'] = [QLabel('Wl. Start (μm)'), 2, 8, 1, 1]
        self.labelSubHead['WlEnd'] = [QLabel('Wl. End (μm)'), 2, 9, 1, 1]
        self.labelSubHead['WlStep'] = [QLabel('Wl. Step (μm)'), 2, 10, 1, 1]
        # self.labelSubHead['XStart'] = [QLabel('Stg. X Start (μm)'), 4, 8, 1, 1]
        # self.labelSubHead['XEnd'] = [QLabel('Stg. X End (μm)'), 4, 9, 1, 1]
        # self.labelSubHead['XStep'] = [QLabel('Stg. X Step (μm)'), 4, 10, 1, 1]
        # self.labelSubHead['YStart'] = [QLabel('Stg. Y Start (μm)'), 6, 8, 1, 1]
        # self.labelSubHead['YEnd'] = [QLabel('Stg. Y End (μm)'), 6, 9, 1, 1]
        # self.labelSubHead['YStep'] = [QLabel('Stg. Y Step (μm)'), 6, 10, 1, 1]
        self.labelSubHead['SamplingRate'] = [QLabel('Sampl. Rate (Hz)'),
                                            8, 8, 1, 1]
        self.labelSubHead['SamplesPerWl'] = [QLabel('Sampl. per Wl.'),
                                            8, 9, 1, 1]
        self.labelSubHead['Speed'] = [QLabel('Speed (μm/s)'), 8, 10, 1, 1]
        for _, k in self.labelSubHead.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.tabSingleGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: instrument readings, in a dict for reference by other methods
        self.labelInstr = dict() # [label, row, col, rowSpan, colSpan]
        # Labels: read currents
        for qcl in range(1, self.laser.numQCL + 1):
            labelString = 'QCL{:d}Current'.format(qcl)
            self.labelInstr[labelString] = QLabel('n/a')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(defaults.STYLE_LABEL_READ_ALT)
            self.labelInstr[labelString].setToolTip('Reading from laser')
            self.tabSingleGrid.addWidget(self.labelInstr[labelString], 2*qcl, 1, 2, 4)
        # Labels: read wavelengths (blank at startup)
        for qcl in range(1, self.laser.numQCL + 1):
            labelString = 'QCL{:d}Wavelength'.format(qcl)
            self.labelInstr[labelString] = QLabel('n/a')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(defaults.STYLE_LABEL_READ_ALT)
            self.labelInstr[labelString].setToolTip('Reading from laser')
            self.tabSingleGrid.addWidget(self.labelInstr[labelString], 2*qcl+1, 5, 1, 2)
        # Labels: wavelength units
        for qcl in range(1, self.laser.numQCL + 1):
            labelString = 'QCL{:d}WlUnit'.format(qcl)
            self.labelInstr[labelString] = QLabel('μm    ')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(defaults.STYLE_LABEL_UNIT)
            self.tabSingleGrid.addWidget(self.labelInstr[labelString], 2*qcl, 6, 1, 1)
        # Compile relevant GUI elements to pass to other classes
        # GUIElem['expNo'] = outfld['ExpCur'][0]
        # GUIElem['expStepTot'] = outfld['ExpTotSteps'][0]
        # Text field for experiment notes
        self.notes = QTextEdit('')
        self.notes.setFont(font)
        self.notes.setStyleSheet(defaults.STYLE_TEXT)
        self.notes.setToolTip('Text written here will be saved to a "notes" file')
        self.tabSingleGrid.addWidget(self.notes, 12, 0, 2, 6)
        # Connect buttons to actions
        self.btn['QCL1'][0].clicked.connect(lambda: self.qcl(1))
        self.btn['QCL2'][0].clicked.connect(lambda: self.qcl(2))
        self.btn['QCL3'][0].clicked.connect(lambda: self.qcl(3))
        self.btn['QCL4'][0].clicked.connect(lambda: self.qcl(4))
        # self.btn['WlUnits'][0].clicked.connect(lambda: self.wl_units())
        self.btn['Arm'][0].clicked.connect(lambda: self.arm())
        self.btn['Emission'][0].clicked.connect(lambda: self.emission())
        self.btn['Tune'][0].clicked.connect(lambda: self.tune())
        self.btn['Start'][0].clicked.connect(lambda: self.run_experiment())
        self.btn['Sweep'][0].clicked.connect(lambda: self.run_experiment())
        self.btn['Repeat'][0].clicked.connect(lambda: self.repeat_experiment())
        self.btn['RefSet'][0].clicked.connect(lambda: self.reference_set(
                                                    self.parameters.latestDir))
        self.activeQcl = 0 # None selected on startup
        ### Multiple acquisition tab - Base layout
        # self.tabMultiple = QWidget()
        # self.tabMultiple.setStyleSheet(defaults.STYLE_CONTAINER)
        # self.tabs.addTab(self.tabMultiple, 'Multiple')
        ### Scanning imaging tab - Base layout
        self.tabImag = QWidget()
        self.tabImag.setStyleSheet(defaults.STYLE_CONTAINER)
        self.tabs.addTab(self.tabImag, 'Scanning imaging')
        ### Scanning imaging tab - Grid layout
        self.tabImagGrid = QGridLayout()
        self.tabImag.setLayout(self.tabImagGrid)
        self.tabImagGrid.setSpacing(10)
        ### Scanning imaging tab - Plot: stage position
        self.stagePlotCanvas = mplCanvas(width=5, height=4)
        self.stagePlotCanvas.patterns = [] # To store scanning patterns
        self.stagePlotCanvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.stagePlotCanvas.axes.set_aspect('equal')
        self.stagePlotCanvas.axes.set_xlabel('x (μm)')
        xTravel = defaults.STAGE_X_TRAVEL_UM
        xMax = 1.1 * xTravel / 2
        xMin = -1 * xMax
        self.stagePlotCanvas.axes.set_xlim(xMin, xMax)
        self.stagePlotCanvas.axes.set_ylabel('y (μm)')
        yTravel = defaults.STAGE_Y_TRAVEL_UM
        yMax = 1.1 * yTravel / 2
        yMin = -1 * yMax
        self.stagePlotCanvas.axes.set_ylim(yMin, yMax)
        self.stagePlotCanvas.axes.invert_yaxis() # Positive y is towards user
        self.stagePlotCanvas.axes.set_title('Stage Position')
        xMax = 1. * xTravel / 2
        xMin = -1 * xMax
        yMax = 1. * yTravel / 2
        yMin = -1 * yMax
        self.stagePlotCanvas.axes.set_axisbelow(True)
        self.stagePlotCanvas.axes.grid(color='gray', linestyle='dashed')
        patch = mpl.patches.Rectangle((xMin, yMin), xTravel, yTravel,
                                    alpha = 0.5,
                                    edgecolor = defaults.STG_COLORS['edge'],
                                    facecolor = defaults.STG_COLORS['fill'],
                                    fill = True,
                                    lw = 2,
                                    zorder = 1)
        self.stagePlotCanvas.axes.add_patch(patch)
        darkAxes = defaults.DARK_PLOT_AXES
        darkBackground = defaults.DARK_PLOT_BACKGROUND
        darkColor = defaults.PLOT_COLOR_DARK
        self.stagePlotCanvas.recolor(darkAxes, darkBackground, darkColor)
        self.tabImagGrid.addWidget(self.stagePlotCanvas, 0, 0, 4, 4)
        ### Scanning imaging tab - Plot: image
        self.imagePlotCanvas = mplCanvas(width=5, height=4)
        self.imagePlotCanvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.imagePlotCanvas.axes.set_aspect('equal')
        self.imagePlotCanvas.axes.set_xlabel('x (μm)')
        xTravel = defaults.STAGE_X_TRAVEL_UM
        xMax = 1.1 * xTravel / 2
        xMin = -1 * xMax
        self.imagePlotCanvas.axes.set_xlim(xMin, xMax)
        self.imagePlotCanvas.axes.set_ylabel('y (μm)')
        yTravel = defaults.STAGE_Y_TRAVEL_UM
        yMax = 1.1 * yTravel / 2
        yMin = -1 * yMax
        self.imagePlotCanvas.axes.set_ylim(yMin, yMax)
        self.imagePlotCanvas.axes.invert_yaxis() # Positive y is towards user
        self.imagePlotCanvas.axes.set_title('Image')
        xMax = 1. * xTravel / 2
        xMin = -1 * xMax
        yMax = 1. * yTravel / 2
        yMin = -1 * yMax
        self.imagePlotCanvas.axes.set_axisbelow(True)
        self.imagePlotCanvas.axes.grid(color='gray', linestyle='dashed')
        patch = mpl.patches.Rectangle((xMin, yMin), xTravel, yTravel,
                                    alpha = 0.5,
                                    edgecolor = defaults.STG_COLORS['edge'],
                                    facecolor = defaults.STG_COLORS['fill'],
                                    fill = True,
                                    lw = 2,
                                    zorder = 1)
        self.imagePlotCanvas.axes.add_patch(patch)
        darkAxes = defaults.DARK_PLOT_AXES
        darkBackground = defaults.DARK_PLOT_BACKGROUND
        darkColor = defaults.PLOT_COLOR_DARK
        self.imagePlotCanvas.recolor(darkAxes, darkBackground, darkColor)
        self.tabImagGrid.addWidget(self.imagePlotCanvas, 0, 6, 4, 4)
        ### Scanning imaging tab - Image wavelength/wavenumber selector
        self.imageWlSlider = QSlider(Qt.Orientation.Horizontal)
        self.tabImagGrid.addWidget(self.imageWlSlider, 4, 6, 1, 6)
        ### Scanning imaging tab - Scan browser
        self.scanBrowser = scanBrowser(self)
        self.tabImagGrid.addWidget(self.scanBrowser, 7, 0, 6, 6)
        ### Scanning imaging tab - Scan options
        scanFilePathLabel = QLabel('Scan configuration file path')
        scanFilePathLabel.setFont(font)
        scanFilePathLabel.setStyleSheet(defaults.STYLE_LABEL_EMPH)
        self.tabImagGrid.addWidget(scanFilePathLabel, 7, 6, 1, 6)
        self.scanFilePath = QLineEdit('C:\\')
        self.scanFilePath.setFont(font)
        self.scanFilePath.setStyleSheet(defaults.STYLE_INPUT)
        self.tabImagGrid.addWidget(self.scanFilePath, 8, 6, 1, 6)
        self.tabImagButtons = dict()
        self.tabImagButtons['Update'] = [QPushButton('Update'), 13, 0, 2, 3]
        self.tabImagButtons['Update'][0].setToolTip('Update scan in plot')
        self.tabImagButtons['Clear'] = [QPushButton('Clear'), 13, 3, 2, 3]
        self.tabImagButtons['Clear'][0].setToolTip('Clear scans')
        self.tabImagButtons['Save'] = [QPushButton('Save'), 9, 6, 1, 2]
        self.tabImagButtons['Save'][0].setToolTip('Save scan file')
        self.tabImagButtons['Load'] = [QPushButton('Load'), 9, 8, 1, 2]
        self.tabImagButtons['Load'][0].setToolTip('Load scan file')
        self.tabImagButtons['Start'] = [QPushButton('Start'), 12, 6, 2, 3]
        self.tabImagButtons['Start'][0].setToolTip('Start scan')
        self.tabImagButtons['Stop'] = [QPushButton('Stop'), 12, 9, 2, 3]
        self.tabImagButtons['Stop'][0].setToolTip('Stop scan')
        for x, k in self.tabImagButtons.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            # k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            if x in ['Start', 'Stop']:
                k[0].setStyleSheet(defaults.STYLE_ARMED)
            else:
                k[0].setStyleSheet(defaults.STYLE_BUTTON)
            self.tabImagGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Connect buttons to actions
        self.tabImagButtons['Start'][0].clicked.connect(lambda: self.run_scanning_imaging())
        ### Scanning imaging tab - Drop-down scan pattern menu
        self.tabImageDropdowns = dict()
        self.tabImageDropdowns['ScanPattern'] = [QComboBox(), 11, 6, 1, 3]
        self.tabImageDropdowns['ScanPattern'][0].addItem('Auto')
        self.tabImageDropdowns['ScanPattern'][0].addItem('Raster')
        self.tabImageDropdowns['ScanMode'] = [QComboBox(), 11, 9, 1, 3]
        self.tabImageDropdowns['ScanMode'][0].addItem('Step (one wavelength each position)')
        self.tabImageDropdowns['ScanMode'][0].addItem('Step (all wavelengths each position')
        self.tabImageDropdowns['ScanMode'][0].addItem('Sweep')
        self.tabImageDropdowns['ScanMode'][0].addItem('Continuous')
        for x, k in self.tabImageDropdowns.items(): # Arrange buttons in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_COMBOBOX)
            self.tabImagGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Show main application window
        self.show()

    def multiple(self):
        '''Multiple acquisitions'''
        self.parameters.timeInterval = 60 * float(
                            self.multiMenu.inputField['timeInterval'][0].text())
        print('Acquisitions every {:.0f} minutes.'.format(
                                             self.parameters.timeInterval / 60))
        self.multiMenu.labelHead['counter'][0].setText('Acquisitions: 0')
        ### Initial checks
        if not self.btn['Arm'][0].isChecked():
            print('Laser is not armed.')
            self.btn['Start'][0].setChecked(False)
            # GUIInstance.btn['Stop'][0].setChecked(False)
            self.btn['Sweep'][0].setChecked(False)
            return
        ### Read and compile experiment parameters
        self.parameters.laser = self.laser
        self.parameters.notes = self.notes.toPlainText()
        self.parameters.useRef = self.btn['RefEnable'][0].isChecked()
        self.parameters.sweeping = self.btn['Sweep'][0].isChecked()
        self.parameters.start = float(self.inputField['WlStart'][0].text())
        self.parameters.end = float(self.inputField['WlEnd'][0].text())
        self.parameters.step = float(self.inputField['WlStep'][0].text())
        self.parameters.sampleNumber = int(self.inputField['SamplesPerWl'][0].text())
        self.parameters.sampleRate = int(self.inputField['SamplingRate'][0].text())
        self.parameters.speed = float(self.inputField['Speed'][0].text())
        if self.wlUnits == 'invcm':
            self.parameters.units = 'invcm'
        else: # Default to micrometers
            self.parameters.units = 'um'
        ### Parameter checks
        if self.parameters.start == self.parameters.end: # Requested limits are equal
            print('Limits cannot be equal.')
            self.btn['Start'][0].setChecked(False)
            self.btn['Sweep'][0].setChecked(False)
            return
        ### Lock GUI controls
        self.lock_controls()
        self.statusbar.showMessage('Busy: multiple acquisitions')
        ### Change multiple menu UI styles
        self.multiMenu.labelHead['counter'][0].setStyleSheet(defaults.STYLE_LABEL_ALT)
        # self.multiMenu.labelHead['timer'][0].setStyleSheet(STYLE_LABEL_ALT)
        ### Run acquisitions until "Stop" is clicked
        self.threadMul = QThread()
        self.worker = experiment()
        self.multiMenu.btn['Stop'][0].clicked.connect(self.worker.stop)
        self.multiMenu.labelHead['counter'][0].setText('Running')
        self.worker.parameters = self.parameters
        self.worker.moveToThread(self.threadMul)
        self.threadMul.started.connect(self.worker.multiple)
        self.worker.finishedMulti.connect(self.threadMul.quit)
        self.worker.finishedMulti.connect(self.worker.deleteLater)
        self.threadMul.finished.connect(self.threadMul.deleteLater)
        self.threadMul.start()
        ### Acquisition timer
        self.worker.acquisitionTimer.connect(self.multiMenu.update_timer)
        self.worker.startedOne.connect(lambda: self.multiMenu.labelHead[
            'timer'][0].setStyleSheet(defaults.STYLE_LABEL_READ))
        self.worker.finishedOne.connect(lambda: self.multiMenu.labelHead[
            'timer'][0].setStyleSheet(defaults.STYLE_LABEL_ALT))
        self.worker.finishedMulti.connect(self.multiMenu.zero_timer)
        ### Increment counter/zero counter
        self.worker.startedOne.connect(self.multiMenu.update_counter_running)
        self.worker.startedOne.connect(lambda: self.multiMenu.labelHead[
            'counter'][0].setStyleSheet(defaults.STYLE_LABEL_ALT))
        self.worker.finishedOne.connect(self.multiMenu.update_counter_waiting)
        self.worker.finishedOne.connect(lambda: self.multiMenu.labelHead[
            'counter'][0].setStyleSheet(defaults.STYLE_LABEL_READ))
        self.worker.finishedMulti.connect(self.multiMenu.zero_counter)
        ### Plot data
        self.worker.outData.connect(self.plot)
        ### Save UI screenshot
        self.worker.finished.connect(lambda: self.grab().save(
                                                    'screenshot.png', 'png'))
        ### Save current QCLs, ranges and limits for use with "repeat" function
        self.worker.outParams.connect(self.update_parameters)
        ### Reset multiple menu UI styles
        self.worker.finishedMulti.connect(lambda: self.multiMenu.labelHead[
            'counter'][0].setStyleSheet(defaults.STYLE_LABEL_READ))
        self.worker.finishedMulti.connect(lambda: self.multiMenu.labelHead[
            'timer'][0].setStyleSheet(defaults.STYLE_LABEL_READ))
        ### Unlock GUI controls
        self.worker.finishedMulti.connect(lambda: self.lock_controls(lock=False))
        self.worker.finishedMulti.connect(lambda: self.statusbar.showMessage('Ready'))
        ### Uncheck UI buttons
        self.worker.finishedMulti.connect(lambda: self.multiMenu.btn[
            'Start'][0].setChecked(False))
        self.worker.finishedMulti.connect(lambda: self.multiMenu.btn[
            'Stop'][0].setChecked(False))

    def multiple_acq_menu(self):
        '''Multiple acquisitions menu'''
        self.multiMenu.show()

    def plot(self, data):
        ### Reverse data for plotting
        ### Deprecated, direction handling is now in routines
        if self.wlUnits == 'invcm':
            # plotData = np.flip(data, 0)
            plotData = data
        else:
            plotData = data
        ### Paint plots
        self.plotCanvas.clear_plots()
        self.plotCanvasT.clear_plots()
        # self.plotCanvas.flush_events()
        try:
            self.plotCanvas.axes.set_xlim(plotData[0, 0], plotData[-1, 0])
            # self.plotCanvas.axes.set_ylim(min(
            # plotData[:, 1]), max(plotData[-1, 0]))
            if self.darkMode.isChecked():
                colorPick = defaults.PLOT_COLOR_DARK
            else:
                colorPick = defaults.PLOT_COLOR
            self.plotCanvas.plot_line(plotData[:, 0], plotData[:, 3],
                                           color = colorPick)
            if self.btn['RefEnable'][0].isChecked():
                self.parameters.useRef = True
                if self.wlUnits == 'invcm':
                    # plotData = np.flip(data, 0)
                    # plotRef = np.flip(self.parameters.reference, 0)
                    plotData = data
                    plotRef = self.parameters.reference
                else:
                    plotData = data
                    plotRef = self.parameters.reference
                # self.plotCanvasT.flush_events()
                self.plotCanvasT.axes.set_xlim(plotData[0, 0], plotData[-1, 0])
                if self.darkMode.isChecked():
                    colorPick = defaults.PLOT_COLOR_T_DARK
                else:
                    colorPick = defaults.PLOT_COLOR_T
                self.plotCanvasT.plot_line(plotData[:, 0],
                                               plotData[:, 3]/plotRef[:, 3],
                                               color = colorPick)
            else:
                self.parameters.useRef = False
        except Exception as exc:
            print('Failed to plot data:\n{}'.format(exc))

    def plot_dark_mode(self):
        '''Use dark background in plots.'''
        if self.darkMode.isChecked():
            darkAxes = defaults.DARK_PLOT_AXES
            darkBackground = defaults.DARK_PLOT_BACKGROUND
            self.plotCanvas.recolor(darkAxes, darkBackground,
                                              defaults.PLOT_COLOR_DARK)
            self.plotCanvasRef.recolor(darkAxes, darkBackground,
                                             defaults.PLOT_COLOR_REF_DARK)
            self.plotCanvasT.recolor(darkAxes, darkBackground,
                                         defaults.PLOT_COLOR_T_DARK)
        else:

            self.plotCanvas.recolor(plotColor = defaults.PLOT_COLOR)
            self.plotCanvasRef.recolor(plotColor = defaults.PLOT_COLOR_REF)
            self.plotCanvasT.recolor(plotColor = defaults.PLOT_COLOR_T)

    def plot_scanning_imaging(self, data):
        '''Plot scanning imaging result'''
        self.imagePlotCanvas.clear_plots()
        wIndex = 0 # Wavelength/number index. Controlled by the scroll bar
        try:
            for iv, v in enumerate(data.V):
                xMin = np.min(data.X[iv])
                xMax = np.max(data.X[iv])
                yMin = np.min(data.Y[iv])
                yMax = np.max(data.Y[iv])
                self.imagePlotCanvas.axes.set_xlim(xMin, xMax)
                self.imagePlotCanvas.axes.set_ylim(yMin, yMax)
                # self.imagePlotCanvas.axes.invert_yaxis() # Positive y is towards user
                self.imagePlotCanvas.axes.invert_xaxis()
                # Z = np.transpose(v[wIndex])
                # Z = np.flip(np.transpose(v[wIndex]), axis = 1)
                Z = np.flip(np.transpose(v[wIndex]), axis = 0)
                img = self.imagePlotCanvas.axes.imshow(Z,
                    cmap=mpl.cm.inferno,
                    alpha=1.,
                    interpolation='none',
                    extent=(xMin, xMax, yMin, yMax),
                    zorder=80)
                self.imagePlotCanvas.plots.append(img)
                self.imagePlotCanvas.figure.canvas.draw()
        except Exception as exc:
            print('Failed to plot data:\n{}'.format(exc))

    def qcl(self, qclSelectNo):
        '''Handle button checked status and style sheet.'''
        self.lock_controls(lock=True)
        for qclNo in range(1, self.laser.numQCL + 1): # Set styles to highlight active QCL
            if qclNo == qclSelectNo:
                # Check button and highlight controls
                self.qcl_style(qclNo, True)
                self.activeQcl = qclNo
                self.update_qcl_reading(qclNo)
            else: # Uncheck buttons and remove highlights
                self.qcl_style(qclNo, False)
        self.lock_controls(lock=False)

    def qcl_fast(self, qclSelectNo):
        '''Version of "qcl" with less overhead. Use with caution.'''
        self.activeQcl = qclSelectNo

    def qcl_style(self, qclNo, selected):
        '''Apply style to QCL button and related controls.'''
        qclNoStr = 'QCL{:.0f}'.format(qclNo)
        qclNoStrCurr = 'QCL{:.0f}Current'.format(qclNo)
        qclNoStrSetWl = 'QCL{:.0f}SetWl'.format(qclNo)
        qclNoStrWl = 'QCL{:.0f}Wavelength'.format(qclNo)
        if selected:
            self.btn[qclNoStr][0].setChecked(True)
            self.btn[qclNoStr][0].setText('QCL {:.0f} ON'.format(qclNo))
            self.inputField[qclNoStrSetWl][0].setStyleSheet(
                defaults.STYLE_INPUT_ALT)
            self.labelInstr[qclNoStrCurr].setStyleSheet(
                defaults.STYLE_LABEL_READ_ALT)
            self.labelInstr[qclNoStrWl].setStyleSheet(defaults.STYLE_LABEL_READ_ALT)
        else:
            self.btn[qclNoStr][0].setChecked(False)
            self.btn[qclNoStr][0].setText('QCL {:.0f} Off'.format(qclNo))
            self.inputField[qclNoStrSetWl][0].setStyleSheet(
                defaults.STYLE_INPUT)
            self.labelInstr[qclNoStrCurr].setStyleSheet(
                defaults.STYLE_LABEL_READ_ALT)
            self.labelInstr[qclNoStrWl].setStyleSheet(defaults.STYLE_LABEL_READ_ALT)

    def reference_enable(self):
        '''Enable use of reference'''
        if self.btn['RefEnable'][0].isChecked:
            self.btn['RefEnable'][0].setText('Ref. ON')
        else:
            self.btn['RefEnable'][0].setText('Ref. Off')

    def reference_set(self, refDir):
        '''Set latest spectrum as reference.'''
        dataPath = refDir # Reference experiment directory
        self.inputField['RefPath'][0].setText('{}'.format(dataPath))
        self.plotCanvasRef.clear_plots()
        self.btn['RefSet'][0].setChecked(False)
        try: # Must follow conventions of experiment routine to find data
            dataPathParts = os.path.split(dataPath)
            fileName = '{}{}'.format(dataPathParts[-1], defaults.DEF_FILENAME)
            filePath = os.path.join(dataPath, fileName)
            data = np.loadtxt(filePath)
            self.plotCanvasRef.axes.set_xlim(data[0, 0], data[-1, 0])
            if self.darkMode.isChecked():
                colorPick = defaults.PLOT_COLOR_REF_DARK
            else:
                colorPick = defaults.PLOT_COLOR_REF
            self.plotCanvasRef.plot_line(data[:, 0], data[:, 3],
                                                              color = colorPick)
            self.parameters.reference = data
            self.parameters.refDir = refDir
        except Exception as exc:
            print('Could not read reference spectrum data:\n{}'.format(exc))

    def repeat_experiment(self):
        '''Run scan with previously used parameters.
           Only works if "run_experiment" is used first.'''
        ### Lock GUI controls
        self.lock_controls()
        self.statusbar.showMessage('Busy')
        ###
        try:
            self.threadRep = QThread()
            self.worker = experiment()
            ### Pass relevant parameters to worker instance
            self.worker.parameters = self.parameters
            self.worker.qcl = self.parameters.qcl
            self.worker.ranges = self.parameters.ranges
            self.worker.ranges = self.parameters.sweepLimits
            self.worker.moveToThread(self.threadRep)
            self.threadRep.started.connect(self.worker.repeat)
            self.worker.finished.connect(self.threadRep.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.threadRep.start()
        except Exception as exc:
            print('Could not repeat experiment:\n{}'.format(exc))
            return
        ### Plot data
        if self.repeatShow.isChecked():
            self.worker.outData.connect(self.plot)
        ### Save current QCLs, ranges and limits for use with "repeat" function
        self.worker.outParams.connect(self.update_parameters)
        ### Unlock GUI controls
        self.worker.finished.connect(lambda: self.lock_controls(lock=False))
        self.worker.finished.connect(lambda: self.statusbar.showMessage('Ready'))
        ### Uncheck UI buttons
        self.worker.finished.connect(lambda: self.btn['Repeat'][0].setChecked(False))

    def run_experiment(self):
        '''Run scan or sweep, according to which button was clicked.'''
        ### Initial checks
        if not self.btn['Arm'][0].isChecked():
            print('Laser is not armed.')
            self.btn['Start'][0].setChecked(False)
            # GUIInstance.btn['Stop'][0].setChecked(False)
            self.btn['Sweep'][0].setChecked(False)
            return
        ### Read and compile experiment parameters
        self.parameters.laser = self.laser
        self.parameters.notes = self.notes.toPlainText()
        self.parameters.useRef = self.btn['RefEnable'][0].isChecked()
        self.parameters.sweeping = self.btn['Sweep'][0].isChecked()
        self.parameters.start = float(self.inputField['WlStart'][0].text())
        self.parameters.end = float(self.inputField['WlEnd'][0].text())
        self.parameters.step = float(self.inputField['WlStep'][0].text())
        self.parameters.sampleNumber = int(self.inputField['SamplesPerWl'][0].text())
        self.parameters.sampleRate = int(self.inputField['SamplingRate'][0].text())
        self.parameters.speed = float(self.inputField['Speed'][0].text())
        if self.wlUnits == 'invcm':
            self.parameters.units = 'invcm'
        else: # Default to micrometers
            self.parameters.units = 'um'
        ### Parameter checks
        if self.parameters.start == self.parameters.end: # Requested limits are equal
            print('Limits cannot be equal.')
            self.btn['Start'][0].setChecked(False)
            # GUIInstance.btn['Stop'][0].setChecked(False)
            self.btn['Sweep'][0].setChecked(False)
            return
        ### Lock GUI controls
        self.lock_controls()
        self.statusbar.showMessage('Busy')
        ### Run acquisition in separate thread
        self.threadRun = QThread()
        self.worker = experiment()
        self.worker.parameters = self.parameters
        self.worker.moveToThread(self.threadRun)
        self.threadRun.started.connect(self.worker.run)
        self.worker.finished.connect(self.threadRun.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.threadRun.finished.connect(self.threadRun.deleteLater)
        self.threadRun.start()
        ### Plot data
        self.worker.outData.connect(self.plot)
        ### Save current QCLs, ranges and limits for use with "repeat" function
        self.worker.outParams.connect(self.update_parameters)
        ### Unlock GUI controls
        self.worker.finished.connect(lambda: self.lock_controls(lock=False))
        self.worker.finished.connect(lambda: self.statusbar.showMessage('Ready'))
        ### Uncheck UI buttons
        self.worker.finished.connect(lambda: self.btn['Start'][0].setChecked(False))
        self.worker.finished.connect(lambda: self.btn['Sweep'][0].setChecked(False))
        ### Save UI screenshot
        self.worker.finished.connect(lambda: self.grab().save('screenshot.png', 'png'))

    def run_scanning_imaging(self):
        '''Run scanning imaging experiment.'''
        ### Initial checks
        if not self.btn['Arm'][0].isChecked():
            print('Laser is not armed.')
            self.btn['Start'][0].setChecked(False)
            # GUIInstance.btn['Stop'][0].setChecked(False)
            self.btn['Sweep'][0].setChecked(False)
            return
        ### Show patterns on plot
        self.update_scanning_imaging_plot_patterns()
        self.scanImagParameters = scanningImagingParameters()
        ### Read and compile general experiment parameters
        self.scanImagParameters.laser = self.laser
        self.scanImagParameters.stage = self.stage
        # self.scanImagParameters.notes = self.notes.toPlainText()
        # self.scanImagParameters.useRef = self.btn['RefEnable'][0].isChecked()
        self.scanImagParameters.sweeping = self.btn['Sweep'][0].isChecked()
        ### Read and compile scanning patterns
        self.scanImagParameters.patterns = []
        for s in self.scanBrowser.scans:
            ### Get pattern parameters for this scan
            xOrig = int(s.inputFields['xOrig'][0].text())
            yOrig = int(s.inputFields['yOrig'][0].text())
            xStep = int(s.inputFields['xStep'][0].text())
            yStep = int(s.inputFields['yStep'][0].text())
            xSizeN = int(s.inputFields['xSizeN'][0].text())
            ySizeN = int(s.inputFields['ySizeN'][0].text())
            ### Construct pattern
            pattern, indices = self.construct_pattern(xOrig = xOrig,
                                             yOrig = yOrig,
                                             xSizeN = xSizeN,
                                             ySizeN = ySizeN,
                                             xStep = xStep,
                                             yStep = yStep)
            samplesPerWl = int(s.inputFields['samplesPerWl'][0].text())
            samplingRate = int(s.inputFields['samplingRate'][0].text())
            speed = float(s.inputFields['speed'][0].text())
            wlwnStr = s.wlwnList.toPlainText()
            wlwnListStr = re.split('[ ,;\n]+', wlwnStr)
            wlwnList = []
            for s in wlwnListStr:
                try:
                    n = float(s)
                    wlwnList.append(n)
                except Exception as exc:
                    print('String "{}" cannot be converted to wavelength/number.'.format(s))
            if not len(wlwnList) > 0:
                print('No wavelengths or wavenumbers in list.')
                self.tabImagButtons['Start'][0].setChecked(False)
                return
            wlwnList.sort()
            self.scanImagParameters.patterns.append(pattern)
            # self.scanImagParameters.patternSize.append(indices[:, 0].size)
            self.scanImagParameters.patternIndices.append(indices)
            self.scanImagParameters.sampleNumbers.append(samplesPerWl)
            self.scanImagParameters.sampleRates.append(samplingRate)
            self.scanImagParameters.speeds.append(speed)
            self.scanImagParameters.wlwnList.append(wlwnList)
            ### Prepare data variables.
            self.scanImagParameters.data.indices.append(indices)
            self.scanImagParameters.data.W.append(wlwnList)
            xVector = np.sort(np.unique(np.asarray(pattern[:, 0])))
            self.scanImagParameters.data.X.append(xVector)
            yVector = np.sort(np.unique(np.asarray(pattern[:, 1])))
            self.scanImagParameters.data.Y.append(yVector)
            self.scanImagParameters.data.add_V()
            self.scanImagParameters.data.add_Vtemp()
        if self.wlUnits == 'invcm':
            self.scanImagParameters.units = 'invcm'
        else: # Default to micrometers
            self.scanImagParameters.units = 'um'
        ### Lock GUI controls
        self.lock_controls()
        self.statusbar.showMessage('Busy')
        ### Run acquisition in separate thread
        self.threadRun = QThread()
        self.worker = imagingScan()
        self.worker.parameters = self.scanImagParameters
        self.worker.moveToThread(self.threadRun)
        self.threadRun.started.connect(self.worker.run)
        # self.worker.stageMoved.connect(self.update_scanning_imaging_plot_position)
        self.worker.finished.connect(self.threadRun.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.threadRun.finished.connect(self.threadRun.deleteLater)
        self.threadRun.start()
        ### Plot data
        self.worker.outData.connect(self.plot_scanning_imaging)
        ### Save current QCLs, ranges and limits for use with "repeat" function
        self.worker.outParams.connect(self.update_scanning_imaging_parameters)
        ### Unlock GUI controls
        self.worker.finished.connect(lambda: self.lock_controls(lock=False))
        self.worker.finished.connect(lambda: self.statusbar.showMessage('Ready'))
        ### Uncheck UI buttons
        self.worker.finished.connect(lambda: self.tabImagButtons['Start'][0].setChecked(False))
        # self.worker.finished.connect(lambda: self.btn['Sweep'][0].setChecked(False))
        ### Save UI screenshot
        self.worker.finished.connect(lambda: self.grab().save('screenshot.png', 'png'))

    def stage_motion_window(self):
        '''Multiple acquisitions menu'''
        self.stageMotionWindow.show()

    def stage_set(self, stageInstance):
        '''Set laser instance'''
        self.stage = stageInstance

    def tune(self):
        '''Tune laser to input wavelength of currently selected QCL.'''
        self.lock_controls(lock=True)
        self.statusbar.showMessage('Busy')
        self.repaint()
        if not self.btn['Arm'][0].isChecked():
            self.btn['Tune'][0].setChecked(False)
            self.statusbar.showMessage('Not armed', defaults.MSG_TIMEOUT)
        else:
            qclNoStrSetWl = 'QCL{:.0f}SetWl'.format(self.activeQcl)
            self.btn['Tune'][0].setText('Tuning ...')
            self.repaint()
            targetWl = float(self.inputField[qclNoStrSetWl][0].text())
            self.laser.tune(self.activeQcl, targetWl, self.wlUnits)
            self.update_qcl_reading(self.activeQcl)
            self.btn['Tune'][0].setText('Tune')
        self.btn['Tune'][0].setChecked(False)
        self.lock_controls(lock=False)
        self.statusbar.showMessage('Ready')

    def tune_fast(self, targetWl):
        '''Version of "tune" with less overhead. Use with caution.'''
        self.laser.tune(self.activeQcl, targetWl, self.wlUnits)

    def update_parameters(self, parameters):
        '''Update class instance experiment parameters with last used set, which
           may be re-used with "repeat".'''
        self.parameters = parameters

    def update_scanning_imaging_plot_patterns(self):
        '''Update patterns on imaging scanning stage position plot.'''
        for p in self.stagePlotCanvas.patterns:
            p.remove()
        self.stagePlotCanvas.patterns = [] # Re-initialize list
        for s in self.scanBrowser.scans:
            ### Get pattern parameters for this scan
            xOrig = int(s.inputFields['xOrig'][0].text())
            yOrig = int(s.inputFields['yOrig'][0].text())
            xStep = int(s.inputFields['xStep'][0].text())
            yStep = int(s.inputFields['yStep'][0].text())
            xSizeN = int(s.inputFields['xSizeN'][0].text())
            ySizeN = int(s.inputFields['ySizeN'][0].text())
            ### Construct pattern
            pattern, _ = self.construct_pattern(xOrig = xOrig,
                                             yOrig = yOrig,
                                             xSizeN = xSizeN,
                                             ySizeN = ySizeN,
                                             xStep = xStep,
                                             yStep = yStep)
            ### Display pattern on plot
            patternPlot = self.stagePlotCanvas.axes.scatter(pattern[:,0],
                                                      pattern[:,1],
                                            c = defaults.STG_COLORS['pattern'],
                                            marker = '.',
                                            zorder = 8)
            self.stagePlotCanvas.patterns.append(patternPlot)
            for p in range (0, pattern.shape[0] - 1):
                p1x = pattern[p, 0]
                p1y = pattern[p, 1]
                p1 = [p1x, p1y]
                p2x = pattern[p + 1, 0]
                p2y = pattern[p + 1, 1]
                p2 = [p2x, p2y]
                xLine = [p1[0], p2[0]]
                yLine = [p1[1], p2[1]]
                line = self.stagePlotCanvas.axes.plot(xLine, yLine, 'k', zorder = 6)
                self.stagePlotCanvas.patterns.append(line[0]) # Index to get actual object
                xArrow = (p1[0] + p2[0]) / 2
                yArrow = (p1[1] + p2[1]) / 2
                arrowLength = 1800 # um, choose value for plot clarity
                ### Angle between two positions, with inverted y axis
                dirAngle = np.arctan2(-1 * (p2[1] - p1[1]), p2[0] - p1[0])
                if p2[0] == p1[0]:
                    dxArrow = 0
                else:
                    dxDir = (p2[0] - p1[0]) / np.abs(p2[0] - p1[0])
                    dxArrow = arrowLength * np.abs(np.cos(dirAngle)) * dxDir
                if p2[1] == p1[1]:
                    dyArrow = 0
                else: ### Corrections required for inverted y axis
                    dyDir = (p2[1] - p1[1]) / np.abs(p2[1] - p1[1])
                    dyArrow = arrowLength * np.abs(np.sin(dirAngle)) * dyDir
                arrow = self.stagePlotCanvas.axes.arrow(xArrow, yArrow,
                                                   dxArrow, dyArrow,
                                                   lw = 1,
                                                   length_includes_head = True,
                                                   head_length = arrowLength,
                                                   head_width = arrowLength,
                                                   color = 'k',
                                                   zorder = 7)
                self.stagePlotCanvas.patterns.append(arrow)
        self.stagePlotCanvas.figure.canvas.draw()

    def update_scanning_imaging_plot_position(self, x = 0, y = 0):
        '''Update stage position on imaging scanning stage position plot.'''
        self.stagePlotCanvas.clear_plots()
        plot = self.stagePlotCanvas.axes.scatter(x, y,
            c = defaults.STG_COLORS['marker'],
            marker = '+',
            zorder = 10)
        self.stagePlotCanvas.plots.append(plot)
        if (np.abs(x) < 1000) or (np.abs(y) < 1000):
            textStr = '{:.0f}, {:.0f}'.format(x, y)
        else:
            textStr = '{:.0f},\n{:.0f}'.format(x, y)
        text = self.stagePlotCanvas.axes.text(x + 2000, y + 0, textStr,
                        color = defaults.STG_COLORS['text'],
                        fontsize = 10,
                        zorder = 11)
        self.stagePlotCanvas.plots.append(text)
        titleString = 'Stage Position: x {:.0f} μm, y  {:.0f} μm'.format(x, y)
        self.stagePlotCanvas.axes.set_title(titleString)
        self.stagePlotCanvas.figure.canvas.draw()

    def update_scanning_imaging_parameters(self, parameters):
        '''Update class instance experiment parameters with last used set, which
           may be re-used with "repeat".'''
        self.scanImagParameters = parameters

    def update_qcl_reading(self, qcl):
        '''Read and display QCL "qcl" temperature, current, and wavelength.'''
        if self.wlUnits=='um':
            unitString = 'μm'
        elif self.wlUnits=='invcm':
            unitString = 'cm⁻¹'
        else:
            unitString = '...'
        qclCurrent = self.laser.get_current(qcl)
        qclPulseRate = self.laser.get_pulse_rate(qcl)
        qclPulseWidth = self.laser.get_pulse_width(qcl)
        tecTemp = self.laser.get_temperature(qcl)
        labelString = 'QCL{:d}Current'.format(qcl)
        labelText = '{:.2f}°C, {:.0f} mA\n{:.0f} ns @ {:.0f} Hz'.format(
                               tecTemp, qclCurrent, qclPulseWidth, qclPulseRate)
        self.labelInstr[labelString].setText(labelText)
        qclWl = self.laser.get_wavelength()
        if self.wlUnits=='um':
            labelText = '{:.2f} {}'.format(qclWl, unitString)
        elif self.wlUnits=='invcm':
            if qclWl > 0:
                qclWl = self.wl_converter(qclWl, self.wlUnits, qcl)
            labelText = '{:.1f} {}'.format(qclWl, unitString)
        labelString = 'QCL{:d}Wavelength'.format(qcl)
        self.labelInstr[labelString].setText(labelText)

    def wl_converter(self, wavelength, unit, qcl=[]):
        '''Convert "wavelength" to "unit", check it is within "qcl" limits'''
        # Convert um to cm^-1
        if unit in ['invcm']:
            convertedWl_invcm = 1/(wavelength*1E-4)
            # Check that converted wavelength is within QCL bounds
            if not qcl:
                outWl = convertedWl_invcm
            else:
                if convertedWl_invcm > defaults.WN_MINIMUMS_INVCM[qcl-1]:
                    outWl = defaults.WN_MINIMUMS_INVCM[qcl-1]
                elif convertedWl_invcm < defaults.WN_MAXIMUMS_INVCM[qcl-1]:
                    outWl = defaults.WN_MAXIMUMS_INVCM[qcl-1]
                else:
                    outWl = convertedWl_invcm
        # Convert cm^-1 to um
        if unit in ['um']:
            convertedWl_um = 1E4/wavelength
            # Check that converted wavelength is within QCL bounds
            if not qcl:
                outWl = convertedWl_um
            else:
                if convertedWl_um < defaults.WL_MINIMUMS_UM[qcl-1]:
                    outWl = defaults.WL_MINIMUMS_UM[qcl-1]
                elif convertedWl_um > defaults.WL_MAXIMUMS_UM[qcl-1]:
                    outWl = defaults.WL_MAXIMUMS_UM[qcl-1]
                else:
                    outWl = convertedWl_um
        return outWl

    def wl_units(self):
        '''Change wavelength/wavenumber units.'''
        # Uncheck
        # if self.btn['WlUnits'][0].isChecked:
        #     self.btn['WlUnits'][0].setChecked(False)
        # Invert plot x axis
        # self.plotCanvas.axes.invert_xaxis()
        # Switch units from um to cm^-1
        if self.wlUnits == 'um':
            self.wlUnits = 'invcm'
            # self.btn['WlUnits'][0].setText('Units: cm⁻¹')
            # Relabel QCL fields
            for qcl in range(1, self.laser.numQCL + 1):
                labelString = 'QCL{:d}WlUnit'.format(qcl)
                self.labelInstr[labelString].setText('cm⁻¹  ')
                inputFieldString = 'QCL{}SetWl'.format(qcl)
                currentWl = float(self.inputField[inputFieldString][0].text())
                convertedWl = self.wl_converter(currentWl, 'invcm', qcl)
                wlString = '{:.1f}'.format(convertedWl)
                self.inputField[inputFieldString][0].setText(wlString)
            # Relabel scan settings
            self.labelSubHead['WlStart'][0].setText('Wl. Start (cm⁻¹)')
            self.labelSubHead['WlEnd'][0].setText('Wl. End (cm⁻¹)')
            self.labelSubHead['WlStep'][0].setText('Wl. Step (cm⁻¹)')
            self.labelSubHead['Speed'][0].setText('Speed (cm⁻¹/s)')
            for wlLabel in ['WlStart', 'WlEnd']:
                currentWl = float(self.inputField[wlLabel][0].text())
                convertedWl = self.wl_converter(currentWl, 'invcm', qcl=[])
                wlString = '{:.1f}'.format(convertedWl)
                self.inputField[wlLabel][0].setText(wlString)
            # Set maximum sweep speed
            self.inputField['Speed'][0].setText('{:.0f}'.format(
                defaults.MAX_SWEEP_SPEED_INVCM))
            # Can't unambiguously convert step
            self.inputField['WlStep'][0].setText('100')
            self.plotCanvas.axes.set_xlabel('Wavenumber (cm⁻¹)')
            self.plotCanvasRef.axes.set_xlabel('Wavenumber (cm⁻¹)')
            self.plotCanvasT.axes.set_xlabel('Wavenumber (cm⁻¹)')
        # Switch units from cm^-1 to um
        elif self.wlUnits == 'invcm':
            self.wlUnits = 'um'
            # self.btn['WlUnits'][0].setText('Units: μm  ')
            for qcl in range(1, self.laser.numQCL + 1):
                labelString = 'QCL{:d}WlUnit'.format(qcl)
                self.labelInstr[labelString].setText('μm    ')
                inputFieldString = 'QCL{}SetWl'.format(qcl)
                currentWl = float(self.inputField[inputFieldString][0].text())
                convertedWl = self.wl_converter(currentWl, 'um', qcl)
                wlString = '{:.2f}'.format(convertedWl)
                self.inputField[inputFieldString][0].setText(wlString)
            # Relabel scan settings
            self.labelSubHead['WlStart'][0].setText('Wl. Start (μm)  ')
            self.labelSubHead['WlEnd'][0].setText('Wl. End (μm)  ')
            self.labelSubHead['WlStep'][0].setText('Wl. Step (μm)  ')
            self.labelSubHead['Speed'][0].setText('Speed (μm/s)')
            for wlLabel in ['WlStart', 'WlEnd']:
                currentWl = float(self.inputField[wlLabel][0].text())
                convertedWl = self.wl_converter(currentWl, 'um', qcl=[])
                wlString = '{:.1f}'.format(convertedWl)
                self.inputField[wlLabel][0].setText(wlString)
            # Set maximum sweep speed
            self.inputField['Speed'][0].setText('{:.2f}'.format(
                defaults.MAX_SWEEP_SPEED_UM))
            # Can't unambiguously convert step
            self.inputField['WlStep'][0].setText('0.1')
            self.plotCanvas.axes.set_xlabel('Wavelength (μm)')
            self.plotCanvasRef.axes.set_xlabel('Wavelength (μm)')
            self.plotCanvasT.axes.set_xlabel('Wavelength (μm)')


class multipleAcquisitionsWindow(QMainWindow):
    '''GUI for multiple acquisitions'''

    def __init__(self, mainGUI):
        # super().__init__(None, Qt.WindowStaysOnTopHint)
        super().__init__()
        # self.latestExperiment = [] # Placeholder for latest experiment instance
        self.make_gui()
        self.acquisitions = 0 # Controls acuisition counter only

    def center_window(self):
        '''Center main application window on screen'''
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def closeEvent(self, event): # Redefined from parent QMainWindow
        '''Show warning dialog on close.'''
        event.accept()

    def make_gui(self):
        '''Draw controls'''
        self.setGeometry(0, 0, 250, 350)
        font = QFont()
        font.setFamily(defaults.FONT_FAMILY)
        font.setPointSize(defaults.FONT_SIZE_MEDIUM)
        ### Set title, icon and center window
        self.setWindowTitle('Multiple Acquisitions')
        self.setWindowIcon(QIcon('icons/mircat.ico'))
        self.center_window()
        ### Actions
        exitAction = QAction(QIcon(None), 'Close Window', self)
        exitAction.setShortcut('Ctrl+W')
        exitAction.setStatusTip('Close multiple acquisitions window')
        exitAction.triggered.connect(lambda: self.close())
        ### Menus
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(defaults.STYLE_MENUBAR)
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.setStyleSheet(defaults.STYLE_MENU)
        fileMenu.addAction(exitAction)
        ### Configure grid layout
        self.containerMultiple = QWidget()
        self.containerMultiple.setStyleSheet(defaults.STYLE_CONTAINER)
        self.setCentralWidget(self.containerMultiple)
        self.tabSingleGrid = QGridLayout()
        self.containerMultiple.setLayout(self.tabSingleGrid)
        self.tabSingleGrid.setSpacing(10)
        for row in range(0, 9): # Set row spacing
            self.tabSingleGrid.setRowStretch(row, 1)
        ### Buttons
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['Start'] = [QPushButton('Start'), 5, 0, 2, 1]
        self.btn['Start'][0].setToolTip('Start multiple acquisitions')
        self.btn['Stop'] = [QPushButton('Stop'), 7, 0, 2, 1]
        self.btn['Stop'][0].setToolTip('Stop multiple acquisitions')
        for x, k in self.btn.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            # k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            k[0].setStyleSheet(defaults.STYLE_ARMED)
            self.tabSingleGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Input fields
        self.inputField = dict() # to collect all input fields
        self.inputField['timeInterval'] = [QLineEdit('{}'.format(5)), 4, 0, 1, 1]
        self.inputField['timeInterval'][0].setToolTip(
            'Multiple acquisition time interval')
        for _, k in self.inputField.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.tabSingleGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Labels
        self.labelHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelHead['counter'] = [QLabel('Not running'), 0, 0, 1, 1]
        self.labelHead['timer'] = [QLabel('Elapsed: 00 : 00 : 00'), 1, 0, 1, 1]
        self.labelHead['timeInterval'] = [QLabel('Time Interval (min)'), 3, 0, 1, 1]
        for _, k in self.labelHead.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_READ)
            self.tabSingleGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        self.labelHead['timeInterval'][0].setStyleSheet(defaults.STYLE_LABEL_EMPH)

    def update_counter_running(self, acquisitions):
        '''Increment acquisitions counter by 1'''
        self.labelHead['counter'][0].setText('Running. Done: {:.0f}'.format(
            acquisitions))
        self.repaint()

    def update_counter_waiting(self, acquisitions):
        '''Increment acquisitions counter by 1'''
        self.labelHead['counter'][0].setText('Waiting. Done: {:.0f}'.format(
            acquisitions))
        self.repaint()

    def update_timer(self, elapsed_s):
        '''Update acquisition timer'''
        elapsed_m, elapsed_s = divmod(elapsed_s, 60)
        elapsed_h, elapsed_m = divmod(elapsed_m, 60)
        self.labelHead['timer'][0].setText(
            'Elapsed: {:02.0f} : {:02.0f} : {:02.0f}'.format(
                elapsed_h, elapsed_m, elapsed_s))

    def zero_counter(self):
        '''Zero acquisition counter'''
        self.acquisitions = 0
        self.labelHead['counter'][0].setText('Not running'.format(
            self.acquisitions))

    def zero_timer(self):
        '''Zero acquisition timer'''
        self.labelHead['counter'][0].setText('Not running'.format(
            self.acquisitions))
        self.labelHead['timer'][0].setText(
            'Elapsed: {:02.0f} : {:02.0f} : {:02.0f}'.format(0, 0, 0))


class scanningImagingData():
    '''Holds data from scanning imaging experiments.
       Organized by pattern, each pattern organized by wavelength/wavenumber.'''

    def __init__(self):
        '''Prepare variables to hold data.
           All these are lists of vectors, matrices or lists.
           Data structure:

           XY SCANNING PATTERN (one element of each of the list variables)
                + ------ indices               (list)
                + ------ V VOLTAGES            (list of matrices, one per wl/wn)
                + ------ V_temp VOLTAGES       (list of lists, one per wl/wn)
                + ------ W WAVELENGTHS/NUMBERS (list)
                + ------ X POSITIONS           (vector)
                + ------ Y POSITIONS           (vector)
        '''
        self.indices = [] # YX indices for temporary voltage list
        self.V = []       # Voltage averages matrix: X columns, Y rows
        self.Vtemp = []  # Voltage non-averaged list, used during acquisition
        self.W = []       # Wavelengths or wavenumbers
        self.X = []       # X positions vector
        self.Y = []       # Y positions vector

    def add_V(self, index = -1):
        '''Make zero matrices to hold voltages, one per wl/wn.
           X are columns, Y rows.
           Use immediately after "add_W", "add_X" and "add_Y" to match index.'''
        self.V.append([])
        for wi, _ in enumerate(self.W[index]):
            self.V[-1].append([])
            self.V[-1][wi] = np.zeros((self.X[index].size, self.Y[index].size))

    def add_Vtemp(self, index = -1):
        '''Make lists to hold voltages during acquisition, one per wl/wn.
           Use immediately after "add_W", "add_X" and "add_Y" to match index.'''
        self.Vtemp.append([])
        for wi, _ in enumerate(self.W[index]):
            self.Vtemp[-1].append([])
            # self.Vtemp[-1][wi].append([])


class scanningImagingParameters():
    '''Holds experiment parameters for scanning imaging.'''

    def __init__(self):
        # self.acquisitions = 0 # Number of acquisitions
        # self.acq_time_interval_s = 300 # Interval between acquisitions, s
        self.data = scanningImagingData() # Holds acquired data
        # self.end = 100 # Placeholder value, no unit
        self.laser = [] # Laser instance, laceholder value
        self.latestDir = 0 # Latest experiment directory, placeholder value
        # self.notes = [] # Placeholder value\
        self.qcl = [] # QCL modules to be used, placeholder value
        self.patterns = [] # Scanning imaging patters, placeholder value
        self.patternIndices = [] # Indices of pattern positions, placeholder value
        self.ranges = [] # Wavelength/wavenumber ranges, placeholder value
        self.refDir = '' # Reference experiment directory
        # self.reference = np.zeros((1, 2)) # Placeholder value
        self.sampleNumbers = [] # Sample numbers, placeholder value
        self.sampleRates = [] # Sample rates, placeholder value
        self.scanMode = 'step_one'
        self.speeds = [] # Sweeping speeds, placeholder value
        self.stage = [] # Stage instance, laceholder value
        # self.start = 0 # Placeholder value, no unit
        # self.step = 1 # Placeholder value, no unit
        # self.sweeping = True # By default, use the sweep routine
        # self.sweepLimits = [] # Placeholder value
        self.units = 'um' # By default, wavelengths in micrometers
        # self.useRef = False # By default, do not use reference
        self.wlwnList = [] # List of wavelengths (um) or wavenumbers (cm^-1)


if __name__ == '__main__':
    APP = QApplication(sys.argv)
    GUI1 = mainWindow()
    sys.exit(APP.exec())
