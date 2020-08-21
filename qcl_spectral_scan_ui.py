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
# from instruments.mircat import laser
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigCanvas
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (QAction,
                             QApplication,
                             QDesktopWidget,
                             QDialog,
                             QGridLayout,
                             QLabel,
                             QMainWindow,
                             QMessageBox,
                             QPushButton,
                             QWidget,
                             QSizePolicy,
                             QLineEdit)

# Color dictionaries
newTab10 = {'blue' : '#4e79a7', 'orange' : '#f28e2b', 'red' : '#e15759',
            'cyan' : '#76b7b2', 'green' : '#59a14e', 'yellow' : '#edc949',
            'violet' : '#b07aa2', 'pink' : '#ff9da7', 'brown' : '#9c755f',
            'gray' : '#bab0ac'} # New Tableau 10 palette
GS_COLORS = {'background': '#1f1f1f',
             'bg-alt': '#e6e6e6',
             'bg-warn': '#d75a3e',
             'border': '#404040',
             'border-alt': '#303030',
             'border-warn': '#d75a3e',
             'hover': '#353535',
             'hover-alt': '#d8d8d8',
             'hover-warn': '#b73e26',
             'menu': '#0c0c0d',
             'text': '#b9b9b9',
             'text-alt': '#141414',
             'text-lo': '#989898',
             'text-hi': '#cf8730',
             'warning': '#d75a3e'}
SOLARIZED = {'base03' : '#002b36',
             'base02': '#073642',
             'base01': '#586e75',
             'base00': '#657b83',
             'base0': '#839496',
             'base1': '#93a1a1',
             'base2': '#eee8d5',
             'base3': '#fdf6e3',
             'yellow': '#b58900',
             'orange': '#cb4b16',
             'red': '#dc322f',
             'magenta': '#d33682',
             'violet': '#6c71c4',
             'blue': '#268bd2',
             'cyan': '#2aa198',
             'green': '#859900'}
DEFAULT_COLORMAP = plt.cm.Spectral # Default colormap

# MIRcat default parameters
DEF_PULSERATE = 100 # kHz
DEF_PULSEWIDTH = 500 # ns
MIN_WL_QCL1 = 5.12 # um
MIN_WL_QCL2 = 5.85 # um
MIN_WL_QCL3 = 6.83 # um
MIN_WL_QCL4 = 8.20 # um
MAX_CURR_QCL1 = 450 # mA
MAX_CURR_QCL2 = 825 # mA
MAX_CURR_QCL3 = 575 # mA
MAX_CURR_QCL4 = 950 # mA
MAX_WL_QCL1 = 6.04 # um
MAX_WL_QCL2 = 7.16 # um
MAX_WL_QCL3 = 7.69 # um
MAX_WL_QCL4 = 9.70 # um
NUMBER_OF_QCLS = 4

# UI look and feel settings
COL_WIDTH = 100
FONT_FAMILY = 'Open Sans Semibold'
FONT_SIZE = 12
MSG_TIMEOUT = 1000 # ms
ROW_HEIGHT = 20
STYLE_ARMED = '''QPushButton {{
        background-color: {};
        border: 2px solid {};
        border-radius: 5px;
        color: {};
    }}
    QPushButton:checked {{
        background-color: {};
        border: 2px solid {};
        color: {};
    }}
    QPushButton:hover {{
        background-color: {};
    }}
    QPushButton:checked:hover {{
        background-color: {};
    }}'''.format(GS_COLORS['background'],
                 GS_COLORS['border'],
                 GS_COLORS['text'],
                 GS_COLORS['bg-warn'],
                 GS_COLORS['border-alt'],
                 GS_COLORS['text-alt'],
                 GS_COLORS['hover'],
                 GS_COLORS['hover-warn'])
STYLE_BAR = ''' QMenuBar {{
        background-color: {};
        color: {};
    }}'''.format(GS_COLORS['menu'],
                 GS_COLORS['text'])
STYLE_BUTTON = '''QPushButton {{
        background-color: {};
        border: 2px solid {};
        border-radius: 5px;
        color: {};
    }}
    QPushButton:checked {{
        background-color: {};
        border: 2px solid {};
        color: {};
    }}
    QPushButton:hover {{
        background-color: {};
    }}
    QPushButton:checked:hover {{
        background-color: {};
    }}'''.format(GS_COLORS['background'],
                 GS_COLORS['border'],
                 GS_COLORS['text'],
                 GS_COLORS['bg-alt'],
                 GS_COLORS['border-alt'],
                 GS_COLORS['text-alt'],
                 GS_COLORS['hover'],
                 GS_COLORS['hover-alt'])
STYLE_CONTAINER = '''QWidget {{
        background-color: {};
    }}'''.format(GS_COLORS['background'])
STYLE_LABEL_EMPH = '''QLabel {{
        color:{};
        qproperty-alignment: AlignLeft;
    }}'''.format(GS_COLORS['text'])
STYLE_INPUT = '''QLineEdit {{
        color: {};
        border: 2px solid {};
        border-radius: 5px;
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-lo'],
                 GS_COLORS['border'])
STYLE_INPUT_ALT = '''QLineEdit {{
        background-color: {};
        color: {};
        border: 2px solid {};
        border-radius: 5px;
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['bg-alt'],
                 GS_COLORS['text-alt'],
                 GS_COLORS['border-alt'])
STYLE_LABEL_ALT = '''QLabel {{
        color:{};
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-hi'])
STYLE_LABEL_READ = '''QLabel {{
        color:{};
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-lo'])
STYLE_LABEL_UNIT = '''QLabel {{
        color:{};
        qproperty-alignment: AlignLeft;
        qproperty-alignment: AlignMiddle;
    }}'''.format(GS_COLORS['text-lo'])


class experiment(): # Scan and aux routines
    
    def __init__(self): # Prepare NI-DAQ task
        self.multipleAI = MChAI([ch_sx, ch_rx, ch_sy, ch_ry])

    def collect(self, sampleNumber, sampleRate): # Get samples fromDAQ device
        self.multipleAI.configure(sampleNumber, sampleRate)
        voltages = self.multipleAI.readAllChannels(sampleNumber)
        self.multipleAI.clearTask()
        return  voltages
    
    def get_voltages(self, sampleNumber, sampleRate): # Collect and average
        daqVoltages = self.collect(sampleNumber, sampleRate)
        SX = np.sum(daqVoltages[0])/sampleNumber
        RX = np.sum(daqVoltages[1])/sampleNumber
        SY = np.sum(daqVoltages[2])/sampleNumber
        RY = np.sum(daqVoltages[3])/sampleNumber
        return [SX, RX, SY, RY]
        
    def scan(self, GUIElements):
        stageStart_um = float(GUIElements['stgStart'].text())
        stageEnd_um = float(GUIElements['stgEnd'].text())
        stageStep_um = float(GUIElements['stgStep'].text())
        piezoStart_um = float(GUIElements['pzoStart'].text())
        piezoEnd_um = float(GUIElements['pzoEnd'].text())
        piezoStep_um = float(GUIElements['pzoStep'].text())
        sampleNumber = int(GUIElements['samples'].text())
        sampleRate = int(GUIElements['sampleRate'].text())
        currentDir = os.getcwd()
        if platform.system() == 'Windows':
            currentDirSplit = currentDir.split('\\')
        else:
            currentDirSplit = currentDir.split('/')
        currentFolder = currentDirSplit[-1]
        original = sys.stdout
        logFile = open('%s.log' % (currentFolder), 'w')
        sys.stdout = logFile
        print('Connecting Reference Lock-in ...')
        lockinRef = lockin(lockinGPIBPortReference)
        print('Connecting Signal Lock-in ...')
        lockinSig = lockin(lockinGPIBPortSignal)
        print('Connecting Stage ...')
        stage1 = stage(stageCOMPort)
        print('Connecting Piezo ...')
        piezo1 = piezo(piezoCOMPort)
        if GUIElements['stgOn'].isChecked():
            stagePositions_um = np.arange(stageStart_um,
                                          stageEnd_um + stageStep_um,
                                          stageStep_um)
            stageStepNumber = len(stagePositions_um)
            GUIElements['stgStepTot'].setText('0 / %.0f' % stageStepNumber)
        else:
            stageStepNumber = 1
            GUIElements['stgStepTot'].setText('n/a')
        if GUIElements['pzoOn'].isChecked():
            piezoPositions_um = np.arange(piezoStart_um,
                                          piezoEnd_um + piezoStep_um,
                                          piezoStep_um)
            piezoStepNumber = len(piezoPositions_um)
            GUIElements['pzoStepTot'].setText('0 / %.0f' % piezoStepNumber)
        else:
            piezoStepNumber = 1
            GUIElements['pzoStepTot'].setText('n/a')
        stepNumber = stageStepNumber * piezoStepNumber
        GUIElements['expStepTot'].setText('0 / %.0f' % stepNumber)
        data = np.zeros((stepNumber, 6)) # stage, Piezo, SX, RX, SY, RY
        position = np.zeros((stepNumber, 1))
        signal = np.zeros((stepNumber, 1))
        reference = np.zeros((stepNumber, 1))
        trace = np.zeros((stepNumber, 1))
        print('Scan started ...')
        GUIElements['main'].repaint()
        start = timer()
        step = 0
        scanInterrupted = False
        lockinRefStatus = lockinRef.get_status() # clear errors, if any
        lockinSigStatus = lockinSig.get_status() # clear errors, if any
        print('One voltage point per step, avg. of %.0f samples at %.0f Hz'
              % (sampleNumber, sampleRate))
        for x in range(0, stageStepNumber): # First step at initial pos
            if GUIElements['stop'].isChecked(): # Stop if button pressed
                scanInterrupted = True
            if scanInterrupted:
                break
            for y in range(0, piezoStepNumber): # First step at initial pos
                GUIElements['main'].setUpdatesEnabled(False)
                if GUIElements['stop'].isChecked(): # Stop if button pressed
                    scanInterrupted = True
                if scanInterrupted:
                    break
                if GUIElements['stgOn'].isChecked():
                    GUIElements['stgStepTot'].setText('%.0f / %.0f' %
                               ((x + 1), stageStepNumber))
                    if x == 0 and y == 0: # Starting scan position
                        stagePos_um = stage1.set_position(stageStart_um) # abs
                    elif x > 0 and y == 0: # Any starting piezo position
                        stagePos_um = stage1.move(stageStep_um) # rel
                    else:
                        stagePos_um = stage1.get_position() # Other stage pos
                else: # Stage unused
                    stagePos_um = stage1.get_position()
                if GUIElements['pzoOn'].isChecked():
                    GUIElements['pzoStepTot'].setText('%.0f / %.0f' %
                               ((y + 1), piezoStepNumber))
                    if y == 0: # Any starting piezo position
                        piezoPos_um = piezo1.set_position(piezoStart_um) # abs
                    else: # Non-start piezo pos
                        piezoPos_um = piezo1.move(piezoStep_um) # rel
                else: # Piezo unused
                    piezoPos_um = piezo1.get_position()
                GUIElements['expStepTot'].setText('%.0f / %.0f' %
                           ((step + 1), stepNumber))
                GUIElements['stgPos'].setText('%.3f' % stagePos_um)
                GUIElements['pzoPos'].setText('%.3f' % piezoPos_um)
                lockinRefStatus = lockinRef.get_status()
                lockinSigStatus = lockinSig.get_status()
                if any(lockinRefStatus):
                    print('Reference Lock-in Overload')
                    scanInterrupted = True
                    break
                if any(lockinSigStatus):
                    print('Signal Lock-in Overload')
                    scanInterrupted = True
                    break
                start2 = timer()
                voltages = self.get_voltages(sampleNumber, sampleRate)
                end2 = timer()
                data[step,0] = stagePos_um
                data[step,1] = piezoPos_um
                for z in range (0, 4):
                    data[step,z+2] = voltages[z]
                position[step, 0] = data[step, 0] + data[step, 1]
                signal[step, 0] = (np.sqrt(np.power(data[step, 2], 2) +
                      np.power(data[step, 4], 2)))
                reference[step, 0] = (np.sqrt(np.power(data[step, 3], 2) +
                         np.power(data[step, 5], 2)))
                trace[step, 0] = signal[step, 0]/reference[step, 0]
                GUIElements['plotS'].update_figure([position[:step+1, 0],
                                                   signal[:step+1, 0]])
                GUIElements['plotR'].update_figure([position[:step+1, 0],
                                                   reference[:step+1, 0]])
                GUIElements['plotSR'].update_figure([position[:step+1, 0],
                                                    trace[:step+1, 0]])
                step += 1
                print('Done step %.0f: stage %.1f um, piezo %.1f um (%.3f s)'
                      % (step,stagePos_um, piezoPos_um, (end2-start2)))
                GUIElements['main'].setUpdatesEnabled(True)
                GUIElements['main'].repaint()
        end = timer()
        if scanInterrupted:
            print('Scan interrupted after %.3f s' % (end-start))
            data = data[0:step]
        else:
            print('Scan complete, took %.3f s' % (end-start))
        logFile.close()
        sys.stdout = original
        np.savetxt('%s_pos1-um_pos2-um_sx-v_rx-v_sy-v_ry-v.dat'
                   % (currentFolder), data)
        piezo1.close()
        stage1.set_position(stageStart_um)
        stage1.close()
        lockinSig.close()
        lockinRef.close()
        GUIElements['main'].setUpdatesEnabled(True)
        GUIElements['main'].repaint()
        GUIElements['main'].grab().save('screenshot.png', 'png')
        return data
    
    
class experimentRun(): # Directory management and multiple acquisitions
    
    def __init__(self):
        pass
        
    def start(self, GUIElements):
        workDir = defaultWorkDir
        if int(GUIElements['setAcqNo'].text()) < 0: # Like I would let you
            GUIElements['setAcqNo'].setText('%.0f' % 1)
        '''Can't have a scan with no active devices'''
        if not (GUIElements['pzoOn'].isChecked() or
                GUIElements['stgOn'].isChecked()):
            GUIElements['pzoOn'].setChecked(True) # Could be Stage too
        acquisitions = int(GUIElements['setAcqNo'].text())
        for x in range(0, acquisitions):
            if GUIElements['stop'].isChecked():
                break
            GUIElements['acqCounter'].setText('%.0f / %.0f' % (
                    (x + 1), acquisitions))
            GUIElements['acqCounter'].repaint()
            '''Create individual experiment folder'''
            os.chdir(workDir)
            newExpNo = 1;
            expNoStr = '%03.0f' % (newExpNo)
            dateStr = time.strftime('%Y-%m-%d')
            expDir = ''.join((workDir, dateStr, '_', expNoStr))
            while os.path.exists(expDir):
                newExpNo += 1;
                expNoStr = '%03.0f' % (newExpNo)
                expDir = ''.join((workDir, dateStr, '_', expNoStr))
            os.mkdir(expDir)
            os.chdir(expDir)
            GUIElements['expNo'].setText('%.0f' % newExpNo)
            experiment1 = experiment()
            data = experiment1.scan(GUIElements)
        GUIElements['stop'].setChecked(False)
        return data


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
        # self.laser = laser()
        self.laser = []
        super().__init__()
        self.make_gui()
        self.statusBar().showMessage('Ready')

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
                    self.statusBar().showMessage('No QCL selected', MSG_TIMEOUT)
                    self.btn['Arm'][0].setChecked(False)
                    self.lock_controls(lock=False)
                    return
                else:
                    self.btn['Arm'][0].setText('Arming ...')
                    self.statusBar().showMessage('Arming ...')
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
        self.statusBar().showMessage('Ready')

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
                self.statusBar().showMessage('Not armed', MSG_TIMEOUT)
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
        self.setGeometry(0, 0, 1200, 800)
        font = QFont()
        font.setFamily(FONT_FAMILY)
        font.setPointSize(FONT_SIZE)
        # self.setWindowModality(Qt.ApplicationModal)
        # Create menus
        self.menubar = self.menuBar()
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
        for row in range(0, 12): # Set row spacing
            # self.grid.setRowMinimumHeight(row, ROW_HEIGHT)
            if row in [0]:
                self.grid.setRowStretch(row, 8)
            else:
                self.grid.setRowStretch(row, 1)
        for col in range(0, 12): # Set column spacing
            if col in [2, 4, 6]:
                self.grid.setColumnStretch(col, 1)
            # elif col in [3]:
            #     self.grid.setColumnStretch(col, 4)
            else:
                self.grid.setColumnStretch(col, 10)
        # Make plot window
        self.spectrumCanvas = mplCanvas(width=12, height=4)
        self.spectrumCanvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.grid.addWidget(self.spectrumCanvas, 0, 0, 1, 11)
        # Buttons: select QCL, laser arm, tune, enable emission
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['QCL1'] = [QPushButton('QCL 1 Off'), 2, 0, 2, 1]
        self.btn['QCL2'] = [QPushButton('QCL 2 Off'), 4, 0, 2, 1]
        self.btn['QCL3'] = [QPushButton('QCL 3 Off'), 6, 0, 2, 1]
        self.btn['QCL4'] = [QPushButton('QCL 4 Off'), 8, 0, 2, 1]
        self.btn['Tune'] = [QPushButton('Tune'), 4, 7, 2, 1]
        self.btn['Arm'] = [QPushButton('Arm'), 2, 7, 2, 1]
        self.btn['Emission'] = [QPushButton('Enable'), 6, 7, 2, 1]
        # Buttons: start scan, stop scan
        self.btn['Start'] = [QPushButton('Start'), 10, 8, 2, 1]
        self.btn['Stop'] = [QPushButton('Stop'), 10, 9, 2, 1]
        for x, k in self.btn.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            if x in ['QCL1', 'QCL2', 'QCL3', 'QCL4']:
                k[0].setStyleSheet(STYLE_BUTTON)
            else:
                k[0].setStyleSheet(STYLE_ARMED)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Input fields: current, current percentage, wavelength
        paramStrings = ['SetCurrent', 'SetCurrPc', 'SetWl']
        self.inputField = dict() # to collect all input fields
        startupText = [MAX_CURR_QCL1, MAX_CURR_QCL2, MAX_CURR_QCL3,
                       MAX_CURR_QCL4, 100, 100, 100, 100, MIN_WL_QCL1,
                       MIN_WL_QCL2, MIN_WL_QCL3, MIN_WL_QCL4]
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
        # Input fields: experiment controls
        self.inputField['WlStart'] = [QLineEdit(''), 3, 8, 1, 1]
        self.inputField['WlEnd'] = [QLineEdit(''), 3, 9, 1, 1]
        self.inputField['WlStep'] = [QLineEdit(''), 3, 10, 1, 1]
        self.inputField['SampleRate'] = [QLineEdit(''), 9, 8, 1, 1]
        self.inputField['SamplesPerWl'] = [QLineEdit(''), 9, 9, 1, 1]
        # Create all input fields
        for _, k in self.inputField.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: headers, in a dict just for ease of positioning
        self.labelHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelHead['QCLMod'] = [QLabel('QCL Modules'), 1, 0, 1, 1]
        self.labelHead['QCLCurr'] = [QLabel('QCL Currents'), 1, 1, 1, 4]
        self.labelHead['QCLWav'] = [QLabel('QCL Wavelengths'), 1, 5, 1, 2]
        self.labelHead['LasControls'] = [QLabel('Laser Controls'), 1, 7, 1, 1]
        self.labelHead['ExpControls'] = [QLabel('Experiment Controls'), 1, 8, 1, 1]
        for _, k in self.labelHead.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: experiment controls sub-headers
        self.labelSubHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelSubHead['WlStart'] = [QLabel('Wl. Start (μm)'), 2, 8, 1, 1]
        self.labelSubHead['WlEnd'] = [QLabel('Wl. End (μm)'), 2, 9, 1, 1]
        self.labelSubHead['WlStep'] = [QLabel('Wl. Step (μm)'), 2, 10, 1, 1]
        self.labelSubHead['XStart'] = [QLabel('Stage X Start (μm)'), 4, 8, 1, 1]
        self.labelSubHead['XEnd'] = [QLabel('Stage X End (μm)'), 4, 9, 1, 1]
        self.labelSubHead['XStep'] = [QLabel('Stage X Step (μm)'), 4, 10, 1, 1]
        self.labelSubHead['YStart'] = [QLabel('Stage Y Start (μm)'), 6, 8, 1, 1]
        self.labelSubHead['YEnd'] = [QLabel('Stage Y End (μm)'), 6, 9, 1, 1]
        self.labelSubHead['YStep'] = [QLabel('Stage Y Step (μm)'), 6, 10, 1, 1]
        self.labelSubHead['SampleRate'] = [QLabel('Sample Rate (Hz)'), 8, 8, 1, 1]
        self.labelSubHead['SamplesPerWl'] = [QLabel('Samples per Wl.'), 8, 9, 1, 1]
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
            self.grid.addWidget(self.labelInstr[labelString], 2*qcl+1, 1, 1, 4)
        # Labels: read wavelengths (blank at startup)
        for qcl in range(1, NUMBER_OF_QCLS + 1):
            labelString = 'QCL{:d}Wavelength'.format(qcl)
            self.labelInstr[labelString] = QLabel('n/a')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(STYLE_LABEL_READ)
            self.grid.addWidget(self.labelInstr[labelString], 2*qcl+1, 5, 1, 2)
        # Labels: units
        unitLabelStrings = ['mA    ', '%     ', 'μm    ']
        for label in range(0, len(unitLabelStrings)):
            col = label * 2 + 2 # odd columns starting at 2 (the third)
            for row in range(2, 9, 2): # every other row
                labelObject = QLabel(unitLabelStrings[label])
                labelObject.setFont(font)
                labelObject.setStyleSheet(STYLE_LABEL_UNIT)
                self.grid.addWidget(labelObject, row, col, 1, 1)
        # Compile relevant GUI elements to pass to other classes
        # GUIElem = dict() # feed this to experiment()
        # GUIElem['main'] = self
        # GUIElem['stop'] = btn['Stop'][0]
        # GUIElem['pzoOn'] = btn['PzOn'][0]
        # GUIElem['stgOn'] = btn['StOn'][0]
        # GUIElem['acq01'] = btn['Acq01'][0]
        # GUIElem['acq05'] = btn['Acq05'][0]
        # GUIElem['acq10'] = btn['Acq10'][0]
        # GUIElem['plotS'] = plotS
        # GUIElem['plotR'] = plotR
        # GUIElem['plotSR'] = plotSR
        # GUIElem['pzoSetPos'] = infld['pzoSetPos'][0]
        # GUIElem['pzoStart'] = infld['PzFrom'][0]
        # GUIElem['pzoEnd'] = infld['PzTo'][0]
        # GUIElem['pzoStep'] = infld['PzStep'][0]
        # GUIElem['stgSetPos'] = infld['stgSetPos'][0]
        # GUIElem['stgStart'] = infld['StFrom'][0]
        # GUIElem['stgEnd'] = infld['StTo'][0]
        # GUIElem['stgStep'] = infld['StStep'][0]
        # GUIElem['samples'] = infld['Samples'][0]
        # GUIElem['sampleRate'] = infld['SampleRate'][0]
        # GUIElem['setAcqNo'] = infld['setAcqs'][0]
        # GUIElem['pzoPos'] = outfld['pzoPos'][0]
        # GUIElem['pzoStepTot'] = outfld['PzTotSteps'][0]
        # GUIElem['stgPos'] = outfld['stgPos'][0]
        # GUIElem['stgStepTot'] = outfld['StTotSteps'][0]
        # GUIElem['acqCounter'] = outfld['AcqCounter'][0]
        # GUIElem['expNo'] = outfld['ExpCur'][0]
        # GUIElem['expStepTot'] = outfld['ExpTotSteps'][0]
        # Connect buttons to actions
        self.btn['QCL1'][0].clicked.connect(lambda: self.qcl(1))
        self.btn['QCL2'][0].clicked.connect(lambda: self.qcl(2))
        self.btn['QCL3'][0].clicked.connect(lambda: self.qcl(3))
        self.btn['QCL4'][0].clicked.connect(lambda: self.qcl(4))
        self.btn['Arm'][0].clicked.connect(lambda: self.arm())
        self.btn['Emission'][0].clicked.connect(lambda: self.emission())
        self.btn['Tune'][0].clicked.connect(lambda: self.tune())
        self.btn['Start'][0].clicked.connect(lambda: self.startExperiment(GUIElem))
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
            self.inputField[qclNoStrSetCurr].setStyleSheet(STYLE_INPUT_ALT)
            self.inputField[qclNoStrSetCurrPc].setStyleSheet(STYLE_INPUT_ALT)
            self.inputField[qclNoStrSetWl].setStyleSheet(STYLE_INPUT_ALT)
            self.labelInstr[qclNoStrCurr].setStyleSheet(STYLE_LABEL_ALT)
            self.labelInstr[qclNoStrWl].setStyleSheet(STYLE_LABEL_ALT)
        else:
            self.btn[qclNoStr][0].setChecked(False)
            self.btn[qclNoStr][0].setText('QCL {:.0f} Off'.format(qclNo))
            self.inputField[qclNoStrSetCurr].setStyleSheet(STYLE_INPUT)
            self.inputField[qclNoStrSetCurrPc].setStyleSheet(STYLE_INPUT)
            self.inputField[qclNoStrSetWl].setStyleSheet(STYLE_INPUT)
            self.labelInstr[qclNoStrCurr].setStyleSheet(STYLE_LABEL_READ)
            self.labelInstr[qclNoStrWl].setStyleSheet(STYLE_LABEL_READ)

    def tune(self):
        '''Tune laser to input wavelength of currently selected QCL.'''
        self.lock_controls(lock=True)
        if not self.btn['Arm'][0].isChecked():
            self.btn['Tune'][0].setChecked(False)
            self.statusBar().showMessage('Not armed', MSG_TIMEOUT)
        else:
            qclNoStrSetWl = 'QCL{:.0f}SetWl'.format(self.activeQcl)
            self.btn['Tune'][0].setText('Tuning ...')
            targetWl = float(self.inputField[qclNoStrSetWl].text())
            self.laser.tune(self.activeQcl, targetWl)
            self.update_qcl_reading(self.activeQcl)
            self.btn['Tune'][0].setText('Tune')
            self.statusBar().showMessage('Ready')
        self.btn['Tune'][0].setChecked(False)
        self.lock_controls(lock=False)

    def update_qcl_reading(self, qcl):
        '''Reads and displays QCL "qcl" temperature, current, and wavelength.'''
        qclCurrent = self.laser.get_current(qcl)
        tecTemp = self.laser.get_temperature(qcl)
        labelString = 'QCL{:d}Current'.format(qcl)
        labelText = '{:.2f}°C, {:d} mA.'.format(tecTemp, qclCurrent)
        self.labelInstr[labelString].setText(labelText)
        qclWl = self.laser.get_wavelength()
        labelText = '{:.2f} um'.format(qclWl)
        labelString = 'QCL{:d}Wavelength'.format(qcl)
        self.labelInstr[labelString].setText(labelText)


class mplCanvas(FigCanvas):
    '''Matplotlib canvas embeddable in QT5.'''

    def __init__(self, parent=None, width=4, height=4):
        self.figure = plt.figure(figsize=(width, height))
        super().__init__(self.figure)
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.images = [] # Stores images plotted with "imshow"
        self.plots = [] # Stores lines plotted with "plot"

    def plot_image(self, Z, colormap=DEFAULT_COLORMAP, zLim=[0, 1]):
        '''Call imshow to plot data'''
        image = self.axes.imshow(Z, cmap=colormap, vmin=zLim[0], vmax=zLim[1], picker=True)
        self.images.append(image)
        self.figure.canvas.draw()

    def plot_line(self, X, Y, color=[0, 0, 0]):
        '''Call plot_surface to plot data'''
        plot = self.axes.plot(X, Y, color=color)
        self.plots.append(plot[0])
        self.figure.canvas.draw()


class plotCanvas(FigCanvas): # Widget for holding plots

    def __init__(self, parent=None, width=8, height=4, dpi=96):
        fig = Figure(figsize=(width, height), dpi=dpi)
        #plt.gcf().subplots_adjust(bottom = 0.5)
        self.axes = fig.add_subplot(111)
        self.make_figure()
        FigCanvas.__init__(self, fig)
        self.setParent(parent)
        FigCanvas.setSizePolicy(self, QSizePolicy.Expanding,
                                QSizePolicy.Expanding)
        FigCanvas.updateGeometry(self)
        
    def make_figure(self):
        pass


class plotWindow(plotCanvas): # Plot and related routines
    
    def make_figure(self):
        self.content, = self.axes.plot([], [], 'o--')
        self.axes.grid(True)
        
    def set_color(self, color):
        self.content.set_color(color)
        
    def set_labels(self, ylabelStr):
        self.xlabel = self.axes.set_xlabel('Position (um)')
        self.ylabel = self.axes.set_ylabel(ylabelStr)
        FigCanvas.updateGeometry(self)
        self.axes.relim() # Need both of these in order to rescale
        self.axes.autoscale_view()
        self.draw() # Redraw
        self.flush_events()
        
    def update_figure(self, data):
        self.content.set_data(data)
        self.axes.relim() # Need both of these in order to rescale
        self.axes.autoscale_view()
        self.draw() # Redraw
        self.flush_events()
    
if __name__ == '__main__':
    APP = QApplication([])
    GUI1 = mainWindow()
    sys.exit(APP.exec_())
