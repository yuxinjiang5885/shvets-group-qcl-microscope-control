#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
mircat_ui
Giovanni Sartorello (srtgnn@gmail.com)
Simple UI for MIRcat in QT5
Created 2019-Mar-14 for Python 3.7.2
'''

import sys
from instruments.mircat import laser
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

# Instrument default parameters
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

class LaserControlWindow(QMainWindow):
    '''Create the main application window and connect to laser.'''

    def __init__(self):
        startupDialog = LaserStartupDialog() # Closes when startup finishes
        self.laser = laser()
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
        reply = QMessageBox.question(self, 'Quit confirmation',
                                     "Are you sure you want to quit?",
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
            self.laser.disable()
            self.laser.disarm()
            self.laser.disconnect()
        else:
            event.ignore()

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
        font = QFont()
        font.setFamily(FONT_FAMILY)
        font.setPointSize(FONT_SIZE)
        self.setWindowModality(Qt.ApplicationModal)
        # Create menus
        self.menuBar()
        # self.menuBar().setStyleSheet(STYLE_BAR)
        # self.statusBar()
        # self.statusBar().showMessage('Initializing ...')
        # self.statusBar().setStyleSheet(STYLE_BAR)
        exitAction = QAction(QIcon(None), 'Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(lambda: self.close())
        laserOff = QAction(QIcon(None), 'Laser off', self)
        laserOff.setShortcut('Ctrl+Alt+L')
        laserOff.setStatusTip('Power down laser')
        laserOff.triggered.connect(lambda: self.close())
        fileMenu = self.menuBar().addMenu('Actions')
        fileMenu.addAction(laserOff)
        fileMenu.addAction(exitAction)
        aboutAction = QAction(QIcon(None), 'About', self)
        aboutAction.setStatusTip('About')
        aboutAction.triggered.connect(self.about)
        helpMenu = self.menuBar().addMenu('Help')
        helpMenu.addAction(aboutAction)
        self.setGeometry(0, 0, 800, ROW_HEIGHT*9)
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
        for row in range(0, 9): # Set row spacing
            self.grid.setRowMinimumHeight(row, ROW_HEIGHT)
            self.grid.setRowStretch(row, 1)
        for col in range(0, 8): # Set column spacing
            if col in [2, 4, 6]:
                self.grid.setColumnStretch(col, 1)
            elif col in [3]:
                self.grid.setColumnStretch(col, 4)
            else:
                self.grid.setColumnStretch(col, 10)
        # Buttons (select QCL, laser arming and emission)
        # In a dict for reference by other methods
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['QCL1'] = [QPushButton('QCL 1 Off'), 1, 0, 2, 1]
        self.btn['QCL2'] = [QPushButton('QCL 2 Off'), 3, 0, 2, 1]
        self.btn['QCL3'] = [QPushButton('QCL 3 Off'), 5, 0, 2, 1]
        self.btn['QCL4'] = [QPushButton('QCL 4 Off'), 7, 0, 2, 1]
        self.btn['Tune'] = [QPushButton('Tune'), 5, 7, 2, 1]
        self.btn['Arm'] = [QPushButton('Arm'), 3, 7, 2, 1]
        self.btn['Emission'] = [QPushButton('Enable'), 7, 7, 2, 1]
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
        # Input fields (current, current percentage, wavelength)
        # In a dict for reference by other methods
        paramStrings = ['SetCurrent', 'SetCurrPc', 'SetWl']
        self.inputField = dict() # to collect all input fields
        startupText = [MAX_CURR_QCL1, MAX_CURR_QCL2, MAX_CURR_QCL3,
                       MAX_CURR_QCL4, 100, 100, 100, 100, MIN_WL_QCL1,
                       MIN_WL_QCL2, MIN_WL_QCL3, MIN_WL_QCL4]
        startupFormat = ['{:.0f}', '{:.0f}', '{:.2f}'] # Current, %, wavelength
        for param in range(0, len(paramStrings)):
            for qcl in range(1, NUMBER_OF_QCLS + 1):
                col = param * 2 + 1 # odd columns starting at 1
                row = qcl * 2 - 1 # odd rows starting at 1
                fieldString = 'QCL{}{}'.format(qcl, paramStrings[param])
                itemNo = param * NUMBER_OF_QCLS + qcl - 1
                startupString = '{}'.format(startupFormat[param]).format(
                                                            startupText[itemNo])
                self.inputField[fieldString] = QLineEdit(startupString)
                self.inputField[fieldString].setFont(font)
                self.inputField[fieldString].setStyleSheet(STYLE_INPUT)
                self.grid.addWidget(self.inputField[fieldString], row, col)
        # Labels: headers. In a dict just for ease of positioning
        self.labelHead = dict() # [label, row, col, rowSpan, colSpan]
        self.labelHead['QCLMod'] = [QLabel('QCL Modules'), 0, 0, 1, 1]
        self.labelHead['QCLCurr'] = [QLabel('QCL Currents'), 0, 1, 1, 4]
        self.labelHead['QCLWav'] = [QLabel('QCL Wavelengths'), 0, 5, 1, 2]
        for _, k in self.labelHead.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: instrument readings
        # In a dict for reference by other methods
        self.labelInstr = dict() # [label, row, col, rowSpan, colSpan]
        # Labels: read currents
        for qcl in range(1, NUMBER_OF_QCLS + 1):
            labelString = 'QCL{:d}Current'.format(qcl)
            self.labelInstr[labelString] = QLabel('')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(STYLE_LABEL_READ)
            self.grid.addWidget(self.labelInstr[labelString], 2*qcl, 1, 1, 4)
        # Labels: read wavelengths (blank at startup)
        for qcl in range(1, NUMBER_OF_QCLS + 1):
            labelString = 'QCL{:d}Wavelength'.format(qcl)
            self.labelInstr[labelString] = QLabel('')
            self.labelInstr[labelString].setFont(font)
            self.labelInstr[labelString].setStyleSheet(STYLE_LABEL_READ)
            self.grid.addWidget(self.labelInstr[labelString], 2*qcl, 5, 1, 2)
        # Labels: units
        unitLabelStrings = ['mA    ', '%     ', 'μm    ']
        for label in range(0, len(unitLabelStrings)):
            col = label * 2 + 2 # even columns starting at 2
            for row in range(1, 8, 2): # every other row
                labelObject = QLabel(unitLabelStrings[label])
                labelObject.setFont(font)
                labelObject.setStyleSheet(STYLE_LABEL_UNIT)
                self.grid.addWidget(labelObject, row, col, 1, 1)
        # Set actions
        self.btn['QCL1'][0].clicked.connect(lambda: self.qcl(1))
        self.btn['QCL2'][0].clicked.connect(lambda: self.qcl(2))
        self.btn['QCL3'][0].clicked.connect(lambda: self.qcl(3))
        self.btn['QCL4'][0].clicked.connect(lambda: self.qcl(4))
        self.btn['Arm'][0].clicked.connect(lambda: self.arm())
        self.btn['Emission'][0].clicked.connect(lambda: self.emission())
        self.btn['Tune'][0].clicked.connect(lambda: self.tune())
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


class LaserStartupDialog(QMessageBox):
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


if __name__ == '__main__':
    APP = QApplication([])
    GUI1 = LaserControlWindow()
    sys.exit(APP.exec_())
