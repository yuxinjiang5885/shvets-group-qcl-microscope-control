'''
qcl_spectral_scan_ui
Giovanni Sartorello (srtgnn@gmail.com)
UI for QCL scanning spectroscopy experiments
Version 1
Python 3.7 on Mac 10.15
Created 2020-Aug-17
'''

import os
import platform
import sys
import matplotlib as mpl
import numpy as np
import matplotlib.pyplot as plt
import time
from timeit import default_timer as timer
from experiment.defaults import *
from experiment.experiment import experiment
from ui.plot_widgets import mplCanvas
from instruments.mircat import laser
from instruments.ni_daq import MultiChannelAnalogInput as MultiAI

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (QAction,
                             QApplication,
                             QDesktopWidget,
                             QDialog,
                             QFileDialog,
                             QGridLayout,
                             QLabel,
                             QMainWindow,
                             QMessageBox,
                             QPushButton,
                             QWidget,
                             QSizePolicy,
                             QTextEdit,
                             QLineEdit)


class laserStartupDialog(QMessageBox):
    '''Show a dialog informing user laser is starting up.'''

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
        self.setWindowTitle('MIRcat Control Panel')
        self.setWindowIcon(QIcon('icons/mircat_ui.ico'))
        self.setText('Initializing MIRcat laser. Please wait.')
        # self.center_window()
        self.show()


class mainWindow(QMainWindow):
    '''Main application window and instrument controls.'''

    def __init__(self):
        startupDialog = laserStartupDialog() # Closes when startup finishes
        self.laser = laser()
        self.wlUnits = 'um' # Wavelength units
        # self.laser = [] # Debugging, UI will load immediately, laser won't work.
        self.latestDir = '' # Latest experiment directory
        self.refDir = '' # Reference experiment directory
        super().__init__()
        self.make_gui()
        self.statusbar.showMessage('Ready')


    def about(self):
        '''Show dialog when "about" is clicked.'''
        aboutFile = 'docs/mircat_ui_about.html'
        with open(aboutFile) as f:
            content = f.read()
        QMessageBox.about(self, 'About', content)

    def arm(self):
        '''Arm or disarm laser laser'''
        self.lock_controls(lock=True)
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
        # Create menus
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(STYLE_BAR)
        self.statusbar = self.statusBar()
        self.statusbar.setStyleSheet(STYLE_BAR)
        self.statusbar.showMessage('Initializing ...')
        exitAction = QAction(QIcon(None), 'Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(lambda: self.close())
        laserOff = QAction(QIcon(None), 'Laser off', self)
        laserOff.setShortcut('Ctrl+Alt+L')
        laserOff.setStatusTip('Power down laser')
        laserOff.triggered.connect(lambda: self.close())
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.addAction(laserOff)
        fileMenu.addAction(exitAction)
        aboutAction = QAction(QIcon(None), 'About', self)
        aboutAction.setStatusTip('About')
        aboutAction.triggered.connect(self.about)
        helpMenu = self.menubar.addMenu('Help')
        helpMenu.addAction(aboutAction)
        self.setWindowTitle('MIRcat Control Panel')
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
        # Plot: latest spectrum
        self.spectrumCanvas = mplCanvas(width=5, height=4)
        self.spectrumCanvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.spectrumCanvas.axes.set_xlabel('Wavelength (μm)')
        self.spectrumCanvas.axes.set_ylabel('Lock-in Mag. (V)')
        self.spectrumCanvas.axes.set_title('Latest Spectrum')
        self.grid.addWidget(self.spectrumCanvas, 0, 0, 1, 5)
        # Plot: current reference
        self.spectrumCanvasRef = mplCanvas(width=5, height=4)
        self.spectrumCanvasRef.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.spectrumCanvasRef.axes.set_xlabel('Wavelength (μm)')
        self.spectrumCanvasRef.axes.set_ylabel('Lock-in Mag. (V)')
        self.spectrumCanvasRef.axes.set_title('Current Reference')
        self.grid.addWidget(self.spectrumCanvasRef, 0, 5, 1, 3)
        # Plot: transmittance
        self.spectrumCanvasT = mplCanvas(width=5, height=4)
        self.spectrumCanvasT.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.spectrumCanvasT.axes.set_xlabel('Wavelength (μm)')
        self.spectrumCanvasT.axes.set_ylabel('Transmittance')
        self.spectrumCanvasT.axes.set_title('Transmittance (Latest/Reference)')
        self.grid.addWidget(self.spectrumCanvasT, 0, 8, 1, 3)
        # Buttons: select QCL, laser arm, tune, enable emission
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['QCL1'] = [QPushButton('QCL 1 Off'), 2, 0, 2, 1]
        self.btn['QCL1'][0].setToolTip('Select QCL module 1')
        self.btn['QCL2'] = [QPushButton('QCL 2 Off'), 4, 0, 2, 1]
        self.btn['QCL2'][0].setToolTip('Select QCL module 2')
        self.btn['QCL3'] = [QPushButton('QCL 3 Off'), 6, 0, 2, 1]
        self.btn['QCL3'][0].setToolTip('Select QCL module 3')
        self.btn['QCL4'] = [QPushButton('QCL 4 Off'), 8, 0, 2, 1]
        self.btn['QCL4'][0].setToolTip('Select QCL module 4')
        self.btn['WlUnits'] = [QPushButton('Units: μm'), 10, 5, 2, 1]
        self.btn['WlUnits'][0].setToolTip('Switch wavelength units')
        self.btn['Tune'] = [QPushButton('Tune'), 4, 7, 2, 1]
        self.btn['Tune'][0].setToolTip('Tune laser to displayed wavelength for selected QCL')
        self.btn['Arm'] = [QPushButton('Arm'), 2, 7, 2, 1]
        self.btn['Arm'][0].setToolTip('Arm/Disarm laser')
        self.btn['Emission'] = [QPushButton('Enable'), 6, 7, 2, 1]
        self.btn['Emission'][0].setToolTip('Enable/disable laser emission')
        self.btn['ScanAutoEnable'] = [QPushButton('Laser\nAuto-Enable'), 8, 7, 2, 1]
        self.btn['ScanAutoEnable'][0].setToolTip('Automatically enable laser during scan (slow)')
        self.btn['Triggering'] = [QPushButton('Triggering'), 12, 7, 2, 1]
        self.btn['Triggering'][0].setToolTip('Enable/disable triggering')
        # Buttons: reference
        self.btn['RefEnable'] = [QPushButton('Reference'), 10, 7, 2, 1]
        self.btn['RefEnable'][0].setToolTip('Enable/disable use of reference')
        self.btn['RefSet'] = [QPushButton('Set Reference'), 11, 8, 1, 1]
        self.btn['RefSet'][0].setToolTip('Set latest spectrum as reference')
        self.btn['RefSave'] = [QPushButton('Save Reference'), 11, 9, 1, 1]
        self.btn['RefSave'][0].setToolTip('Save latest spectrum path for later')
        self.btn['RefRecall'] = [QPushButton('Recall Reference'), 11, 10, 1, 1]
        self.btn['RefRecall'][0].setToolTip('Recall saved spectrum path and set as reference')
        # Buttons: start sweep, start scan, stop scan
        self.btn['Sweep'] = [QPushButton('Sweep'), 12, 8, 2, 1]
        self.btn['Sweep'][0].setToolTip('Start sweep')
        self.btn['Start'] = [QPushButton('Scan'), 12, 9, 2, 1]
        self.btn['Start'][0].setToolTip('Start step-and-measure scan')
        self.btn['Stop'] = [QPushButton('Stop'), 12, 10, 2, 1]
        self.btn['Stop'][0].setToolTip('Stop scan')
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
        # Input fields: current, current percentage, wavelength
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
        # Input fields: experiment controls
        self.inputField['WlStart'] = [QLineEdit('5.4'), 3, 8, 1, 1]
        self.inputField['WlStart'][0].setToolTip('First scan wavelength')
        self.inputField['WlEnd'] = [QLineEdit('5.8'), 3, 9, 1, 1]
        self.inputField['WlEnd'][0].setToolTip('Last scan wavelength')
        self.inputField['WlStep'] = [QLineEdit('0.1'), 3, 10, 1, 1]
        self.inputField['WlStep'][0].setToolTip('Scan wavelength step')
        self.inputField['SamplingRate'] = [QLineEdit('{}'.format(DEF_SAMPLERATE)), 9, 8, 1, 1]
        self.inputField['SamplingRate'][0].setToolTip('Acquisition card sampling rate')
        self.inputField['SamplesPerWl'] = [QLineEdit('{}'.format(DEF_SAMPLES)), 9, 9, 1, 1]
        self.inputField['SamplesPerWl'][0].setToolTip('Samples read by acquisition card at every step')
        # Input fields: reference
        self.inputField['RefPath'] = [QLineEdit('C:\\Data\\_experiment_data'), 10, 8, 1, 3]
        # Create all input fields
        for _, k in self.inputField.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: headers, in a dict for ease of positioning
        self.labelHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelHead['QCLMod'] = [QLabel('QCL Modules'), 1, 0, 1, 1]
        self.labelHead['QCLCurr'] = [QLabel('QCL Currents'), 1, 1, 1, 4]
        self.labelHead['QCLWav'] = [QLabel('QCL Wavelengths'), 1, 5, 1, 2]
        self.labelHead['LasControls'] = [QLabel('Laser/Experiment Settings and Controls'), 1, 7, 1, 4]
        # self.labelHead['ExpControls'] = [QLabel('Scan/Reference Settings'), 1, 8, 1, 3]
        self.labelHead['Notes'] = [QLabel('Experiment Notes'), 12, 0, 1, 1]
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
        self.notes.setStyleSheet(STYLE_INPUT)
        self.grid.addWidget(self.notes, 12, 1, 2, 4)
        # Connect buttons to actions
        self.btn['QCL1'][0].clicked.connect(lambda: self.qcl(1))
        self.btn['QCL2'][0].clicked.connect(lambda: self.qcl(2))
        self.btn['QCL3'][0].clicked.connect(lambda: self.qcl(3))
        self.btn['QCL4'][0].clicked.connect(lambda: self.qcl(4))
        self.btn['WlUnits'][0].clicked.connect(lambda: self.wl_units())
        self.btn['Arm'][0].clicked.connect(lambda: self.arm())
        self.btn['Emission'][0].clicked.connect(lambda: self.emission())
        self.btn['Tune'][0].clicked.connect(lambda: self.tune())
        self.btn['Start'][0].clicked.connect(lambda: self.run_experiment(self))
        # self.btn['RefEnable'][0].clicked.connect(lambda: self.reference_enable())
        self.btn['RefSet'][0].clicked.connect(lambda: self.reference_set(self.latestDir))
        self.activeQcl = 0 # None selected on startup
        self.show()

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
            self.refDir = refDir
        except Exception as exc:
            print('Could not read reference spectrum data:\n{}'.format(exc))

    def run_experiment(self, GUIElements):
        '''Run scan, return data'''
        self.statusbar.showMessage('Busy')
        experiment0 = experiment()
        data = experiment0.start(GUIElements)
        self.statusbar.showMessage('Ready')
        return data

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

    def update_qcl_reading(self, qcl):
        '''Read and display QCL "qcl" temperature, current, and wavelength.'''
        if self.wlUnits=='um':
            unitString = 'μm'
        elif self.wlUnits=='invcm':
            unitString = 'cm⁻¹'
        else:
            unitString = '...'
        qclCurrent = self.laser.get_current(qcl)
        tecTemp = self.laser.get_temperature(qcl)
        labelString = 'QCL{:d}Current'.format(qcl)
        labelText = '{:.2f}°C, {:d} mA'.format(tecTemp, qclCurrent)
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
        '''Change wavelength units.'''
        # Uncheck
        if self.btn['WlUnits'][0].isChecked:
            self.btn['WlUnits'][0].setChecked(False)
        # Invert plot x axis
        # self.spectrumCanvas.axes.invert_xaxis()
        # Switch units from um to cm^-1
        if self.wlUnits == 'um':
            self.wlUnits = 'invcm'
            self.btn['WlUnits'][0].setText('Units: cm⁻¹')
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
            for wlLabel in ['WlStart', 'WlEnd']:
                currentWl = float(self.inputField[wlLabel][0].text())
                convertedWl = self.wl_converter(currentWl, 'invcm', qcl=[])
                wlString = '{:.1f}'.format(convertedWl)
                self.inputField[wlLabel][0].setText(wlString)
            # Can't unambiguously convert step
            self.inputField['WlStep'][0].setText('10')
            self.spectrumCanvas.axes.set_xlabel('Wavelength (cm⁻¹)')
        # Switch units from cm^-1 to um
        elif self.wlUnits == 'invcm':
            self.wlUnits = 'um'
            self.btn['WlUnits'][0].setText('Units: μm  ')
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
            for wlLabel in ['WlStart', 'WlEnd']:
                currentWl = float(self.inputField[wlLabel][0].text())
                convertedWl = self.wl_converter(currentWl, 'um', qcl=[])
                wlString = '{:.1f}'.format(convertedWl)
                self.inputField[wlLabel][0].setText(wlString)
            # Can't unambiguously convert step
            self.inputField['WlStep'][0].setText('0.1')
            self.spectrumCanvas.axes.set_xlabel('Wavelength (μm)')

if __name__ == '__main__':
    APP = QApplication([])
    GUI1 = mainWindow()
    sys.exit(APP.exec_())
