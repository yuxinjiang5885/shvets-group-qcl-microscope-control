'''
qcl_spectral_scan_ui_multithread
Giovanni Sartorello (srtgnn@gmail.com)
UI for QCL scanning spectroscopy experiments
Multi-threaded version of "qcl_spectral_scan_ui"
Python 3.8.3 on Windows 10
Created 2021-Mar-03
'''

import os
import platform
import sys
import matplotlib as mpl
import numpy as np
import matplotlib.pyplot as plt
import time
from timeit import default_timer as timer, timeit
from experiment.defaults import *
from experiment.routines_multithread import experiment
from ui.plot_widgets import mplCanvas
from instruments.mircat import laser
from instruments.ni_daq import MultiChannelAnalogInput as MultiAI
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import experiment.defaults as defaults
from PyQt5.QtGui import QIcon, QFont, QWindow
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


class laserInitializer(QObject):
    '''Initialize laser'''
    laserInitialized = pyqtSignal() # Emitted when laser is initialized
    laserInstance = pyqtSignal(object) # Returns laser instance

    def __init__(self):
        super().__init__()

    def laser_initialize(self):
        laser0 = laser() # Initialize laser
        self.laserInstance.emit(laser0)
        self.laserInitialized.emit()


class laserStartupDialog(QDialog):
    '''Show a dialog when laser is starting up.'''

    def __init__(self):
        super().__init__()
        self.make_dialog()

    def center_window(self):
        '''Center window on screen.'''
        qtRectangle = self.frameGeometry()
        centerPoint = QDesktopWidget().availableGeometry().center()
        qtRectangle.moveCenter(centerPoint)
        self.move(qtRectangle.topLeft())

    def make_dialog(self):
        '''Setup dialog window.
           Main UI window is disabled until laser is initialized.'''
        ### Window parameters
        self.setWindowTitle('MIRcat Control Panel (Multi-thread)')
        self.setWindowIcon(QIcon('icons/mircat_ui.ico'))
        self.setGeometry(0, 0, 200, 50)
        self.setStyleSheet(STYLE_CONTAINER)
        self.setWindowModality(Qt.ApplicationModal) # Disable rest of UI
        ### Dialog text
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.textBox = QLabel('Initializing MIRcat laser. Please wait.')
        self.textBox.setStyleSheet(STYLE_LABEL_ALT)
        self.layout.addWidget(self.textBox)
        self.center_window()


class mainWindow(QMainWindow):
    '''Main application window and instrument controls.'''

    def __init__(self):
        super().__init__()
        ### Initialize laser
        self.laser = []
        self.thread = QThread()
        self.laserWorker = laserInitializer()
        self.laserWorker.moveToThread(self.thread)
        self.thread.started.connect(self.laserWorker.laser_initialize)
        self.laserWorker.laserInitialized.connect(self.thread.quit)
        self.laserWorker.laserInitialized.connect(self.laserWorker.deleteLater)
        self.laserWorker.laserInstance.connect(self.laser_set)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        ### Show startup dialog
        startupDialog = laserStartupDialog() # Closes when startup finishes
        self.laserWorker.laserInitialized.connect(lambda: startupDialog.done(0))
        # startupDialog.show()
        startupDialog.exec()
        ### Prepare text for "about" dialog
        try:
            self.aboutText = ''
            aboutFile = 'docs/mircat_ui_multithread_about.html'
            with open(aboutFile) as f:
                self.aboutText = f.read()
        except Exception as exc:
            print('Falied to load "about" text:\n{}'.format(exc))
        ### Set class parameters
        self.parameters = experimentParameters() # For passing to "run" and "repeat"
        # self.useRef = False # By default, do not use reference
        self.wlUnits = 'um' # Wavelength/number units
        ### Thread and worker placeholders
        # self.thread = [] # Placeholder for last-used thread
        # self.worker = [] # Placeholder for last-used worker
        ### Create GUI
        self.make_gui()
        self.multiMenu = multipleAcquisitionsWindow(self)
        self.multiMenu.btn['Start'][0].clicked.connect(lambda: self.multiple())
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
                    self.statusbar.showMessage('No QCL selected', MSG_TIMEOUT)
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
        '''Center main application window on screen.'''
        qtRectangle = self.frameGeometry()
        centerPoint = QDesktopWidget().availableGeometry().center()
        qtRectangle.moveCenter(centerPoint)
        self.move(qtRectangle.topLeft())

    def closeEvent(self, event): # Redefined from parent QMainWindow
        '''Show warning dialog on close.'''
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

    def emission(self):
        '''Enable or disable laser emission.'''
        self.lock_controls(lock=True)
        if self.btn['Emission'][0].isChecked():
            if not self.btn['Arm'][0].isChecked():
                self.btn['Emission'][0].setChecked(False)
                self.statusbar.showMessage('Not armed', MSG_TIMEOUT)
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

    def lock_controls(self, lock=True):
        '''Disable all buttons while operations are performed.'''
        enabled = not lock # For the sake of clarity
        for _, k in self.btn.items():
            k[0].setEnabled(enabled)

    def make_gui(self):
        '''Create main GUI window.'''
        self.setGeometry(0, 0, 1400, 960)
        font = QFont()
        font.setFamily(FONT_FAMILY)
        font.setPointSize(FONT_SIZE)
        # self.setWindowModality(Qt.ApplicationModal)
        ### Create bars
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(STYLE_BAR)
        self.statusbar = self.statusBar()
        self.statusbar.setStyleSheet(STYLE_BAR)
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
        laserOff = QAction(QIcon(None), 'Laser off', self)
        laserOff.setShortcut('Ctrl+Alt+L')
        laserOff.setStatusTip('Power down laser (Not Implemented)')
        laserOff.triggered.connect(lambda: print('Action not implemented'))
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.addAction(laserOff)
        fileMenu.addAction(exitAction)
        fileMenu.addAction(changeUnits)
        ### "Multiple" menu
        multipleMenu = self.menubar.addMenu('Multiple')
        multipleAcqMenu = QAction(QIcon(None), 'Timed multiple acquisitions', self)
        multipleAcqMenu.setShortcut('Ctrl+M')
        multipleAcqMenu.setStatusTip('Open timed multiple acquisitions menu')
        multipleMenu.addAction(multipleAcqMenu)
        multipleAcqMenu.triggered.connect(lambda: self.multiple_acq_menu())
        ### "Options" menu
        optionsMenu = self.menubar.addMenu('Options')
        self.repeatShowAction = QAction(QIcon(None), 'Plot data when using "Repeat"', self, checkable=True)
        self.repeatShowAction.setStatusTip('Plot data when using the repeat function')
        optionsMenu.addAction(self.repeatShowAction)
        ### "About" menu
        aboutAction = QAction(QIcon(None), 'About', self)
        aboutAction.setStatusTip('About')
        aboutAction.triggered.connect(self.about)
        helpMenu = self.menubar.addMenu('Help')
        helpMenu.addAction(aboutAction)
        ### Set title, icon and center window
        self.setWindowTitle('MIRcat Control Panel (Multi-thread)')
        self.setWindowIcon(QIcon('icons/mircat_ui.ico'))
        self.center_window()
        # Configure grid layout
        self.container = QWidget()
        self.container.setStyleSheet(STYLE_CONTAINER)
        self.setCentralWidget(self.container)
        self.grid = QGridLayout()
        self.container.setLayout(self.grid)
        self.grid.setSpacing(10)
        for row in range(0, NUMBER_OF_ROWS): # Set row spacing
            # self.grid.setRowMinimumHeight(row, ROW_HEIGHT)
            if row in [0]:
                self.grid.setRowStretch(row, 8)
            else:
                self.grid.setRowStretch(row, 1)
        for col in range(0, NUMBER_OF_COLS): # Set column spacing
            if col in [1, 3, 5]: # QCL settings
                self.grid.setColumnStretch(col, 2)
            if col in [2, 4, 6]: # Scl setting labels
                self.grid.setColumnStretch(col, 1)
            # elif col in [3]:
            #     self.grid.setColumnStretch(col, 4)
            else:
                self.grid.setColumnStretch(col, 20)
        ### Plot: latest spectrum
        self.spectrumCanvas = mplCanvas(width=5, height=4)
        self.spectrumCanvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.spectrumCanvas.axes.set_xlabel('Wavelength (μm)')
        self.spectrumCanvas.axes.set_ylabel('Lock-in Mag. (V)')
        self.spectrumCanvas.axes.set_title('Latest Spectrum')
        self.grid.addWidget(self.spectrumCanvas, 0, 0, 1, 5)
        ### Plot: current reference
        self.spectrumCanvasRef = mplCanvas(width=5, height=4)
        self.spectrumCanvasRef.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.spectrumCanvasRef.axes.set_xlabel('Wavelength (μm)')
        self.spectrumCanvasRef.axes.set_ylabel('Lock-in Mag. (V)')
        self.spectrumCanvasRef.axes.set_title('Current Reference')
        self.grid.addWidget(self.spectrumCanvasRef, 0, 5, 1, 3)
        ### Plot: transmittance
        self.spectrumCanvasT = mplCanvas(width=5, height=4)
        self.spectrumCanvasT.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.spectrumCanvasT.axes.set_xlabel('Wavelength (μm)')
        self.spectrumCanvasT.axes.set_ylabel('Transmittance')
        self.spectrumCanvasT.axes.set_title('Transmittance (Latest/Reference)')
        self.grid.addWidget(self.spectrumCanvasT, 0, 8, 1, 3)
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
        self.btn['Tune'][0].setToolTip('Tune laser to displayed wavelength for selected QCL')
        self.btn['Arm'] = [QPushButton('Arm'), 2, 7, 2, 1]
        self.btn['Arm'][0].setToolTip('Arm/Disarm laser')
        self.btn['Emission'] = [QPushButton('Enable'), 6, 7, 2, 1]
        self.btn['Emission'][0].setToolTip('Enable/disable laser emission')
        # self.btn['ScanAutoEnable'] = [QPushButton('Laser\nAuto-Enable'), 8, 7, 2, 1]
        # self.btn['ScanAutoEnable'][0].setToolTip('Automatically enable laser during scan (slow)')
        # self.btn['Triggering'] = [QPushButton('Triggering'), 12, 7, 2, 1]
        # self.btn['Triggering'][0].setToolTip('Enable/disable triggering')
        # Buttons: reference
        self.btn['RefEnable'] = [QPushButton('Reference'), 10, 7, 2, 1]
        self.btn['RefEnable'][0].setToolTip('Enable/disable use of reference')
        self.btn['RefSet'] = [QPushButton('Set Reference'), 11, 8, 1, 1]
        self.btn['RefSet'][0].setToolTip('Set latest spectrum as reference')
        self.btn['RefSave'] = [QPushButton('Save Reference'), 11, 9, 1, 1]
        self.btn['RefSave'][0].setToolTip('Save latest spectrum path for later')
        self.btn['RefRecall'] = [QPushButton('Recall Reference'), 11, 10, 1, 1]
        self.btn['RefRecall'][0].setToolTip('Recall saved spectrum path and set as reference')
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
            k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            if x in ['QCL1', 'QCL2', 'QCL3', 'QCL4']:
                k[0].setStyleSheet(STYLE_BUTTON)
            elif x in ['WlUnits']:
                k[0].setStyleSheet(STYLE_UNITBUTTON)
            else:
                k[0].setStyleSheet(STYLE_ARMED)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Input fields: current, current percentage, wavelength
        paramStrings = ['SetCurrent', 'SetCurrPc', 'SetWl']
        self.inputField = dict() # to collect all input fields
        startupText = [MAX_CURR_QCL1_MILLIAMP, MAX_CURR_QCL2_MILLIAMP, MAX_CURR_QCL3_MILLIAMP,
                       MAX_CURR_QCL4_MILLIAMP, 100, 100, 100, 100, MIN_WL_QCL1_UM,
                       MIN_WL_QCL2_UM, MIN_WL_QCL3_UM, MIN_WL_QCL4_UM]
        startupFormat = ['{:.0f}', '{:.0f}', '{:.2f}'] # Current, %, wavelength
        for param in range(0, len(paramStrings)):
            for qcl in range(1, NUMBER_OF_QCLS + 1):
                col = param * 2 + 1 # even columns starting at 1 (the second)
                row = qcl * 2 # odd rows starting at 2 (the third)
                fieldString = 'QCL{}{}'.format(qcl, paramStrings[param])
                itemNo = param * NUMBER_OF_QCLS + qcl - 1
                startupString = '{}'.format(startupFormat[param]).format(
                                                            startupText[itemNo])
                self.inputField[fieldString] = [QLineEdit(startupString), row, col, 1, 1]
                self.inputField[fieldString][0].setToolTip('DO NOT USE: set in MIRcatControl')
        ### Input fields: experiment controls
        self.inputField['WlStart'] = [QLineEdit('{}'.format(DEF_WL_START_UM)), 3, 8, 1, 1]
        self.inputField['WlStart'][0].setToolTip('First scan wavelength')
        self.inputField['WlEnd'] = [QLineEdit('{}'.format(DEF_WL_END_UM)), 3, 9, 1, 1]
        self.inputField['WlEnd'][0].setToolTip('Last scan wavelength')
        self.inputField['WlStep'] = [QLineEdit('{}'.format(DEF_WL_STEP_UM)), 3, 10, 1, 1]
        self.inputField['WlStep'][0].setToolTip('Scan wavelength step')
        self.inputField['SamplingRate'] = [QLineEdit('{}'.format(DEF_SAMPLERATE)), 9, 8, 1, 1]
        self.inputField['SamplingRate'][0].setToolTip('Acquisition card sampling rate')
        self.inputField['SamplesPerWl'] = [QLineEdit('{}'.format(DEF_SAMPLES)), 9, 9, 1, 1]
        self.inputField['SamplesPerWl'][0].setToolTip('Samples read by acquisition card at every step')
        self.inputField['Speed'] = [QLineEdit('{}'.format(MAX_SWEEP_SPEED_UM)), 9, 10, 1, 1]
        self.inputField['Speed'][0].setToolTip('Sweep speed')
        ### Input fields: reference
        self.inputField['RefPath'] = [QLineEdit('C:\\Data\\_experiment_data'), 10, 8, 1, 3]
        ### Create all input fields
        for _, k in self.inputField.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Labels: headers, in a dict for ease of positioning
        self.labelHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelHead['QCLMod'] = [QLabel('QCL Modules'), 1, 0, 1, 1]
        self.labelHead['QCLCurr'] = [QLabel('QCL Currents'), 1, 1, 1, 4]
        self.labelHead['QCLWav'] = [QLabel('QCL Wavelengths'), 1, 5, 1, 2]
        self.labelHead['LasControls'] = [QLabel('Laser/Experiment Settings and Controls'), 1, 7, 1, 4]
        # self.labelHead['ExpControls'] = [QLabel('Scan/Reference Settings'), 1, 8, 1, 3]
        self.labelHead['Notes'] = [QLabel('Experiment Notes'), 11, 0, 1, 1]
        for _, k in self.labelHead.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: experiment controls sub-headers
        self.labelSubHead = dict() # [label, row, col, rowSpan, colSpan]
        # self.labelSubHead['RefPath'] = [QLabel('Reference Path'), 10, 7, 1, 1]
        self.labelSubHead['WlStart'] = [QLabel('Wl. Start (μm)'), 2, 8, 1, 1]
        self.labelSubHead['WlEnd'] = [QLabel('Wl. End (μm)'), 2, 9, 1, 1]
        self.labelSubHead['WlStep'] = [QLabel('Wl. Step (μm)'), 2, 10, 1, 1]
        self.labelSubHead['XStart'] = [QLabel('Stg. X Start (μm)'), 4, 8, 1, 1]
        self.labelSubHead['XEnd'] = [QLabel('Stg. X End (μm)'), 4, 9, 1, 1]
        self.labelSubHead['XStep'] = [QLabel('Stg. X Step (μm)'), 4, 10, 1, 1]
        self.labelSubHead['YStart'] = [QLabel('Stg. Y Start (μm)'), 6, 8, 1, 1]
        self.labelSubHead['YEnd'] = [QLabel('Stg. Y End (μm)'), 6, 9, 1, 1]
        self.labelSubHead['YStep'] = [QLabel('Stg. Y Step (μm)'), 6, 10, 1, 1]
        self.labelSubHead['SamplingRate'] = [QLabel('Sampl. Rate (Hz)'), 8, 8, 1, 1]
        self.labelSubHead['SamplesPerWl'] = [QLabel('Sampl. per Wl.'), 8, 9, 1, 1]
        self.labelSubHead['Speed'] = [QLabel('Speed (μm/s)'), 8, 10, 1, 1]
        for _, k in self.labelSubHead.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: instrument readings, in a dict for reference by other methods
        self.labelInstr = dict() # [label, row, col, rowSpan, colSpan]
        # Labels: read currents
        for qcl in range(1, NUMBER_OF_QCLS + 1):
            labelString = 'QCL{:d}Current'.format(qcl)
            self.labelInstr[labelString] = QLabel('n/a')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(STYLE_LABEL_READ)
            self.labelInstr[labelString].setToolTip('Reading from laser')
            self.grid.addWidget(self.labelInstr[labelString], 2*qcl+1, 1, 1, 4)
        # Labels: read wavelengths (blank at startup)
        for qcl in range(1, NUMBER_OF_QCLS + 1):
            labelString = 'QCL{:d}Wavelength'.format(qcl)
            self.labelInstr[labelString] = QLabel('n/a')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(STYLE_LABEL_READ)
            self.labelInstr[labelString].setToolTip('Reading from laser')
            self.grid.addWidget(self.labelInstr[labelString], 2*qcl+1, 5, 1, 2)
        # Labels: current controls
        unitLabelStrings = ['mA    ', '%     ']
        for label in range(0, len(unitLabelStrings)):
            col = label * 2 + 2 # odd columns starting at 2 (the third)
            for row in range(2, 9, 2): # every other row
                labelObject = QLabel(unitLabelStrings[label])
                labelObject.setFont(font)
                labelObject.setStyleSheet(STYLE_LABEL_UNIT)
                self.grid.addWidget(labelObject, row, col, 1, 1)
        # Labels: wavelength units
        for qcl in range(1, NUMBER_OF_QCLS + 1):
            labelString = 'QCL{:d}WlUnit'.format(qcl)
            self.labelInstr[labelString] = QLabel('μm    ')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(STYLE_LABEL_UNIT)
            self.grid.addWidget(self.labelInstr[labelString], 2*qcl, 6, 1, 1)
        # Compile relevant GUI elements to pass to other classes
        # GUIElem['expNo'] = outfld['ExpCur'][0]
        # GUIElem['expStepTot'] = outfld['ExpTotSteps'][0]
        # Text field for experiment notes
        self.notes = QTextEdit('')
        self.notes.setFont(font)
        self.notes.setStyleSheet(STYLE_TEXT)
        self.notes.setToolTip('Text written here will be saved to a separate file')
        self.grid.addWidget(self.notes, 12, 0, 2, 6)
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
        self.btn['RefSet'][0].clicked.connect(lambda: self.reference_set(self.parameters.latestDir))
        self.activeQcl = 0 # None selected on startup
        self.show()

    def multiple(self):
        '''Multiple acquisitions'''
        self.parameters.timeInterval = 60 * float(self.multiMenu.inputField['timeInterval'][0].text())
        print('Acquisitions every {:.0f} minutes.'.format(self.parameters.timeInterval / 60))
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
        self.multiMenu.labelHead['counter'][0].setStyleSheet(STYLE_LABEL_ALT)
        # self.multiMenu.labelHead['timer'][0].setStyleSheet(STYLE_LABEL_ALT)
        ### Run acquisitions until "Stop" is clicked
        self.thread = QThread()
        self.worker = experiment()
        self.multiMenu.btn['Stop'][0].clicked.connect(self.worker.stop)
        self.multiMenu.labelHead['counter'][0].setText('Running')
        self.worker.parameters = self.parameters
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.multiple)
        self.worker.finishedMulti.connect(self.thread.quit)
        self.worker.finishedMulti.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        ### Acquisition timer
        self.worker.acquisitionTimer.connect(self.multiMenu.update_timer)
        self.worker.startedOne.connect(lambda: self.multiMenu.labelHead['timer'][0].setStyleSheet(STYLE_LABEL_READ))
        self.worker.finishedOne.connect(lambda: self.multiMenu.labelHead['timer'][0].setStyleSheet(STYLE_LABEL_ALT))
        self.worker.finishedMulti.connect(self.multiMenu.zero_timer)
        ### Increment counter/zero counter
        self.worker.startedOne.connect(self.multiMenu.update_counter_running)
        self.worker.startedOne.connect(lambda: self.multiMenu.labelHead['counter'][0].setStyleSheet(STYLE_LABEL_ALT))
        self.worker.finishedOne.connect(self.multiMenu.update_counter_waiting)
        self.worker.finishedOne.connect(lambda: self.multiMenu.labelHead['counter'][0].setStyleSheet(STYLE_LABEL_READ))
        self.worker.finishedMulti.connect(self.multiMenu.zero_counter)
        ### Plot data
        self.worker.outData.connect(self.plot)
        ### Save UI screenshot
        self.worker.finished.connect(lambda: self.grab().save('screenshot.png', 'png'))
        ### Save current QCLs, ranges and limits for use with "repeat" function
        self.worker.outParams.connect(self.update_parameters)
        ### Reset multiple menu UI styles
        self.worker.finishedMulti.connect(lambda: self.multiMenu.labelHead['counter'][0].setStyleSheet(STYLE_LABEL_READ))
        self.worker.finishedMulti.connect(lambda: self.multiMenu.labelHead['timer'][0].setStyleSheet(STYLE_LABEL_READ))
        ### Unlock GUI controls
        self.worker.finishedMulti.connect(lambda: self.lock_controls(lock=False))
        self.worker.finishedMulti.connect(lambda: self.statusbar.showMessage('Ready'))
        ### Uncheck UI buttons
        self.worker.finishedMulti.connect(lambda: self.multiMenu.btn['Start'][0].setChecked(False))
        self.worker.finishedMulti.connect(lambda: self.multiMenu.btn['Stop'][0].setChecked(False))

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
        self.spectrumCanvas.clear_plots()
        self.spectrumCanvasT.clear_plots()
        # self.spectrumCanvas.flush_events()
        try:
            self.spectrumCanvas.axes.set_xlim(plotData[0, 0], plotData[-1, 0])
            # self.spectrumCanvas.axes.set_ylim(min(plotData[:, 1]), max(plotData[-1, 0]))
            self.spectrumCanvas.plot_line(plotData[:, 0], plotData[:, 3])
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
                # self.spectrumCanvasT.flush_events()
                self.spectrumCanvasT.axes.set_xlim(plotData[0, 0], plotData[-1, 0])
                self.spectrumCanvasT.plot_line(plotData[:, 0],
                                                      plotData[:, 3]/plotRef[:, 3])
            else:
                self.parameters.useRef = False
        except Exception as exc:
            print('Failed to plot data:\n{}'.format(exc))

    def qcl(self, qclSelectNo):
        '''Handle button checked status and style sheet.'''
        self.lock_controls(lock=True)
        for qclNo in range(1, 5): # Set styles to highlight active QCL
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
        qclNoStrSetCurr = 'QCL{:.0f}SetCurrent'.format(qclNo)
        qclNoStrSetCurrPc = 'QCL{:.0f}SetCurrPc'.format(qclNo)
        qclNoStrSetWl = 'QCL{:.0f}SetWl'.format(qclNo)
        qclNoStrWl = 'QCL{:.0f}Wavelength'.format(qclNo)
        if selected:
            self.btn[qclNoStr][0].setChecked(True)
            self.btn[qclNoStr][0].setText('QCL {:.0f} ON'.format(qclNo))
            self.inputField[qclNoStrSetCurr][0].setStyleSheet(STYLE_INPUT_ALT)
            self.inputField[qclNoStrSetCurrPc][0].setStyleSheet(STYLE_INPUT_ALT)
            self.inputField[qclNoStrSetWl][0].setStyleSheet(STYLE_INPUT_ALT)
            self.labelInstr[qclNoStrCurr].setStyleSheet(STYLE_LABEL_ALT)
            self.labelInstr[qclNoStrWl].setStyleSheet(STYLE_LABEL_ALT)
        else:
            self.btn[qclNoStr][0].setChecked(False)
            self.btn[qclNoStr][0].setText('QCL {:.0f} Off'.format(qclNo))
            self.inputField[qclNoStrSetCurr][0].setStyleSheet(STYLE_INPUT)
            self.inputField[qclNoStrSetCurrPc][0].setStyleSheet(STYLE_INPUT)
            self.inputField[qclNoStrSetWl][0].setStyleSheet(STYLE_INPUT)
            self.labelInstr[qclNoStrCurr].setStyleSheet(STYLE_LABEL_READ)
            self.labelInstr[qclNoStrWl].setStyleSheet(STYLE_LABEL_READ)

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
        self.spectrumCanvasRef.clear_plots()
        self.btn['RefSet'][0].setChecked(False)
        try: # Must follow conventions of experiment routine to find data
            dataPathParts = os.path.split(dataPath)
            fileName = '{}{}'.format(dataPathParts[-1], DEF_FILENAME)
            filePath = os.path.join(dataPath, fileName)
            data = np.loadtxt(filePath)
            self.spectrumCanvasRef.axes.set_xlim(data[0, 0], data[-1, 0])
            self.spectrumCanvasRef.plot_line(data[:, 0], data[:, 3])
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
            self.thread = QThread()
            self.worker = experiment()
            ### Pass relevant parameters to worker instance
            self.worker.parameters = self.parameters
            self.worker.qcl = self.parameters.qcl
            self.worker.ranges = self.parameters.ranges
            self.worker.ranges = self.parameters.sweepLimits
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.repeat)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.start()
        except Exception as exc:
            print('Could not repeat experiment:\n{}'.format(exc))
            return
        ### Plot data
        if self.repeatShowAction.isChecked():
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
        self.thread = QThread()
        self.worker = experiment()
        self.worker.parameters = self.parameters
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
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

    def tune(self):
        '''Tune laser to input wavelength of currently selected QCL.'''
        self.lock_controls(lock=True)
        if not self.btn['Arm'][0].isChecked():
            self.btn['Tune'][0].setChecked(False)
            self.statusbar.showMessage('Not armed', MSG_TIMEOUT)
        else:
            qclNoStrSetWl = 'QCL{:.0f}SetWl'.format(self.activeQcl)
            self.btn['Tune'][0].setText('Tuning ...')
            targetWl = float(self.inputField[qclNoStrSetWl][0].text())
            self.laser.tune(self.activeQcl, targetWl, self.wlUnits)
            self.update_qcl_reading(self.activeQcl)
            self.btn['Tune'][0].setText('Tune')
            self.statusbar.showMessage('Ready')
        self.btn['Tune'][0].setChecked(False)
        self.lock_controls(lock=False)

    def tune_fast(self, targetWl):
        '''Version of "tune" with less overhead. Use with caution.'''
        self.laser.tune(self.activeQcl, targetWl, self.wlUnits)

    def update_parameters(self, parameters):
        '''Update class instance experiment parameters with last used set, which
           may be re-used with "repeat".'''
        self.parameters = parameters

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
        labelText = '{:.2f}°C | {:d} mA | {:.0f} ns @ {:.0f} Hz'.format(tecTemp,
                                        qclCurrent, qclPulseWidth, qclPulseRate)
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
                if convertedWl_invcm > WL_MINIMUMS_INVCM[qcl-1]:
                    outWl = WL_MINIMUMS_INVCM[qcl-1]
                elif convertedWl_invcm < WL_MAXIMUMS_INVCM[qcl-1]:
                    outWl = WL_MAXIMUMS_INVCM[qcl-1]
                else:
                    outWl = convertedWl_invcm
        # Convert cm^-1 to um
        if unit in ['um']:
            convertedWl_um = 1E4/wavelength
            # Check that converted wavelength is within QCL bounds
            if not qcl:
                outWl = convertedWl_um
            else:
                if convertedWl_um < WL_MINIMUMS_UM[qcl-1]:
                    outWl = WL_MINIMUMS_UM[qcl-1]
                elif convertedWl_um > WL_MAXIMUMS_UM[qcl-1]:
                    outWl = WL_MAXIMUMS_UM[qcl-1]
                else:
                    outWl = convertedWl_um
        return outWl

    def wl_units(self):
        '''Change wavelength/wavenumber units.'''
        # Uncheck
        # if self.btn['WlUnits'][0].isChecked:
        #     self.btn['WlUnits'][0].setChecked(False)
        # Invert plot x axis
        # self.spectrumCanvas.axes.invert_xaxis()
        # Switch units from um to cm^-1
        if self.wlUnits == 'um':
            self.wlUnits = 'invcm'
            # self.btn['WlUnits'][0].setText('Units: cm⁻¹')
            # Relabel QCL fields
            for qcl in range(1, NUMBER_OF_QCLS + 1):
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
            self.inputField['Speed'][0].setText('{:.0f}'.format(MAX_SWEEP_SPEED_INVCM))
            # Can't unambiguously convert step
            self.inputField['WlStep'][0].setText('100')
            self.spectrumCanvas.axes.set_xlabel('Wavenumber (cm⁻¹)')
        # Switch units from cm^-1 to um
        elif self.wlUnits == 'invcm':
            self.wlUnits = 'um'
            # self.btn['WlUnits'][0].setText('Units: μm  ')
            for qcl in range(1, NUMBER_OF_QCLS + 1):
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
            self.inputField['Speed'][0].setText('{:.2f}'.format(MAX_SWEEP_SPEED_UM))
            # Can't unambiguously convert step
            self.inputField['WlStep'][0].setText('0.1')
            self.spectrumCanvas.axes.set_xlabel('Wavelength (μm)')


class multipleAcquisitionsWindow(QMainWindow):
    '''GUI for multiple acquisitions'''

    def __init__(self, mainGUI):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        # self.latestExperiment = [] # Placeholder for latest experiment instance
        self.make_gui()
        self.acquisitions = 0 # Controls acuisition counter only

    def center_window(self):
        '''Center main application window on screen'''
        qtRectangle = self.frameGeometry()
        centerPoint = QDesktopWidget().availableGeometry().center()
        qtRectangle.moveCenter(centerPoint)
        self.move(qtRectangle.topLeft())

    def closeEvent(self, event): # Redefined from parent QMainWindow
        '''Show warning dialog on close.'''
        event.accept()

    def make_gui(self):
        '''Draw controls'''
        self.setGeometry(0, 0, 250, 350)
        font = QFont()
        font.setFamily(FONT_FAMILY)
        font.setPointSize(FONT_SIZE)
        ### Set title, icon and center window
        self.setWindowTitle('Multiple Acquisitions')
        self.setWindowIcon(QIcon('icons/mircat_ui.ico'))
        self.center_window()
        ### Actions
        exitAction = QAction(QIcon(None), 'Quit', self)
        exitAction.setShortcut('Ctrl+Q')
        # exitAction.setStatusTip('Quit application')
        exitAction.triggered.connect(lambda: self.close())
        ### Menus
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(STYLE_BAR)
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.addAction(exitAction)
        ### Configure grid layout
        self.container = QWidget()
        self.container.setStyleSheet(STYLE_CONTAINER)
        self.setCentralWidget(self.container)
        self.grid = QGridLayout()
        self.container.setLayout(self.grid)
        self.grid.setSpacing(10)
        for row in range(0, 9): # Set row spacing
            self.grid.setRowStretch(row, 1)
        ### Buttons
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['Start'] = [QPushButton('Start'), 5, 0, 2, 1]
        self.btn['Start'][0].setToolTip('Start multiple acquisitions')
        self.btn['Stop'] = [QPushButton('Stop'), 7, 0, 2, 1]
        self.btn['Stop'][0].setToolTip('Stop multiple acquisitions')
        for x, k in self.btn.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            k[0].setStyleSheet(STYLE_ARMED)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Input fields
        self.inputField = dict() # to collect all input fields
        self.inputField['timeInterval'] = [QLineEdit('{}'.format(5)), 4, 0, 1, 1]
        self.inputField['timeInterval'][0].setToolTip('Multiple acquisition time interval')
        for _, k in self.inputField.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Labels
        self.labelHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelHead['counter'] = [QLabel('Not running'), 0, 0, 1, 1]
        self.labelHead['timer'] = [QLabel('Elapsed: 00 : 00 : 00'), 1, 0, 1, 1]
        self.labelHead['timeInterval'] = [QLabel('Time Interval (min)'), 3, 0, 1, 1]
        for _, k in self.labelHead.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_LABEL_READ)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        self.labelHead['timeInterval'][0].setStyleSheet(STYLE_LABEL_EMPH)

    def update_counter_running(self, acquisitions):
        '''Increment acquisitions counter by 1'''
        self.labelHead['counter'][0].setText('Running. Done: {:.0f}'.format(acquisitions))
        self.repaint()

    def update_counter_waiting(self, acquisitions):
        '''Increment acquisitions counter by 1'''
        self.labelHead['counter'][0].setText('Waiting. Done: {:.0f}'.format(acquisitions))
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


if __name__ == '__main__':
    APP = QApplication(sys.argv)
    GUI1 = mainWindow()
    sys.exit(APP.exec_())
