'''
laser_windows
Giovanni Sartorello (srtgnn@gmail.com)
UI elements for QCL laser
Python 3.9.6 on Windows 10
Created 2021-Dec-07
'''

import experiment.defaults as defaults
from instruments.mircat import laser
# from PyQt5.QtCore import Qt
# from PyQt5.QtCore import QObject, pyqtSignal
# from PyQt5.QtGui import QIntValidator, QIcon, QFont
# from PyQt5.QtWidgets import (QAction,
#                              QDesktopWidget,
#                              QDialog,
#                              QGridLayout,
#                              QLabel,
#                              QLineEdit,
#                              QMainWindow,
#                              QPushButton,
#                              QWidget,
#                              QSizePolicy,
#                              QVBoxLayout)
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIntValidator, QIcon, QFont, QScreen
from PyQt6.QtWidgets import (QDialog,
                             QGridLayout,
                             QLabel,
                             QLineEdit,
                             QMainWindow,
                             QPushButton,
                             QWidget,
                             QSizePolicy,
                             QVBoxLayout)


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


class laserSettingWindow(QMainWindow):
    '''GUI for laser settings'''

    def __init__(self, mainGUI):
        # super().__init__(None, Qt.WindowStaysOnTopHint)
        super().__init__()
        self.paramNames = ['PulseRate',
                           'PulseWidth',
                           'DutyCycle',
                           'Current',
                           'CurrentPercent']
        self.laser = mainGUI.laser
        self.make_gui()

    def center_window(self):
        '''Center main application window on screen'''
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def closeEvent(self, event): # Redefined from parent QMainWindow
        '''Show warning dialog on close.'''
        event.accept()

    def get_qcl_parameters(self, qcl):
        '''Read parameters of QCL module "qcl".'''
        parameters = dict()
        parameters['QCLCurrent'] = self.laser.get_current(qcl)
        parameters['QCLPulseRate'] = self.laser.get_pulse_rate(qcl)
        parameters['QCLPulseWidth'] = self.laser.get_pulse_width(qcl)
        parameters['TECTemperature'] = self.laser.get_temperature(qcl)
        # qclWavelength_um = self.laser.get_wavelength()
        # qclWavenumber_invcm = (1/qclWavelength_um)*1E4
        return parameters

    def make_gui(self):
        '''Draw controls'''
        self.setGeometry(0, 0, 1100, 400)
        font = QFont()
        font.setFamily(defaults.FONT_FAMILY)
        font.setPointSize(defaults.FONT_SIZE)
        ### Set title, icon and center window
        self.setWindowTitle('MIRcat Settings Panel')
        self.setWindowIcon(QIcon('icons/mircat.ico'))
        self.center_window()
        ### Actions
        updateAction = QAction(QIcon(None), 'Refresh Readings', self)
        updateAction.setShortcut('Ctrl+R')
        updateAction.setStatusTip('Refresh QCL parameter readings')
        updateAction.triggered.connect(lambda: self.update_readings())
        exitAction = QAction(QIcon(None), 'Close Window', self)
        exitAction.setShortcut('Ctrl+W')
        exitAction.setStatusTip('Close laser settings window')
        exitAction.triggered.connect(lambda: self.close())
        ### Menus
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(defaults.STYLE_MENUBAR)
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.setStyleSheet(defaults.STYLE_MENU)
        fileMenu.addAction(updateAction)
        fileMenu.addAction(exitAction)
        ### Configure grid layout
        self.container = QWidget()
        self.container.setStyleSheet(defaults.STYLE_CONTAINER)
        self.setCentralWidget(self.container)
        self.grid = QGridLayout()
        self.container.setLayout(self.grid)
        self.grid.setSpacing(10)
        ### Labels: QCL modules
        self.labels = dict() # [label, row, col, rowSpan, colSpan]
        for qcl in range(1, self.laser.numQCL + 1):
            labelName = 'QCL{:.0f}'.format(qcl)
            labelText = '{:.0f}'.format(qcl)
            row = 2 * qcl - 1 # Every other row, starting at 1
            self.labels[labelName] = [QLabel(labelText), row, 0, 2, 1]
        ### Labels: header
        self.labels['QCL'] = [QLabel('QCL    '), 0, 0, 1, 1]
        self.labels['PulseRate'] = [QLabel('Pulse Rate'), 0, 1, 1, 2]
        self.labels['PulseWidth'] = [QLabel('Pulse Width'), 0, 3, 1, 2]
        self.labels['DutyCycle'] = [QLabel('Duty Cycle'), 0, 5, 1, 2]
        self.labels['Current'] = [QLabel('Current'), 0, 7, 1, 4]
        for _, k in self.labels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: units
        unitLabelStrings = ['Hz    ', 'ns    ', '%    ', 'mA    ', '%    ']
        for x, labelText in enumerate(unitLabelStrings):
            col = x * 2 + 2 # Every other column, starting at 2
            for row in range(1, 8, 2): # Every other row
                labelObject = QLabel(labelText)
                labelObject.setFont(font)
                labelObject.setStyleSheet(defaults.STYLE_LABEL_UNIT)
                self.grid.addWidget(labelObject, row, col, 1, 1)
        ### Buttons
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        for qcl in range(1, self.laser.numQCL + 1):
            btnName = 'QCL{:.0f}SetParameters'.format(qcl)
            btnText = '  Set QCL {:.0f} Parameters  '.format(qcl)
            row = 2 * qcl - 1 # Every other row, starting at 1
            self.btn[btnName] = [QPushButton(btnText), row, 11, 2, 1]
        for x, (_, k) in enumerate(self.btn.items()): # Arrange buttons in grid
            k[0].setCheckable(True)
            # k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            # k[0].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            k[0].setStyleSheet(defaults.STYLE_ARMED)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
            ### Connecting here will connect all to the last QCL.
            # k[0].clicked.connect(lambda: self.set_qcl_parameters(x+1))
        ### Connect buttons.
        ### Connecting one-by-one as workaround
        self.btn['QCL1SetParameters'][0].clicked.connect(lambda: self.set_qcl_parameters(1))
        self.btn['QCL2SetParameters'][0].clicked.connect(lambda: self.set_qcl_parameters(2))
        self.btn['QCL3SetParameters'][0].clicked.connect(lambda: self.set_qcl_parameters(3))
        self.btn['QCL4SetParameters'][0].clicked.connect(lambda: self.set_qcl_parameters(4))
        ### Input fields: pulse rate and width, duty cycle, current (mA and %)
        self.inputField = dict() # to collect all input fields
        for x, param in enumerate(self.paramNames):
            col = x * 2 + 1 # every other column, starting at 1.
            for qcl in range(1, self.laser.numQCL + 1):
                row = 2 * qcl - 1 # every other row, starting at 1.
                fieldName = 'QCL{}Set{}'.format(qcl, param)
                self.inputField[fieldName] = [QLineEdit(''), row, col, 1, 1]
        for n, k in self.inputField.items(): # Arrange in grid
            k[0].setFont(font)
            if 'DutyCycle' in n: # It is a duty cycle control
                k[0].setStyleSheet(defaults.STYLE_INPUT_LOCKED)
                k[0].setReadOnly(True)
            else:
                k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Input fields: set validators
        for qcl in range(1, self.laser.numQCL + 1):
            currentMax_mA = self.laser.get_current_maximum_pulsed(qcl)
            [pulseRateMax_Hz, pulseWidthMax_ns, _] = self.laser.get_pulse_limits(qcl)
            ### Pulse rate validator
            fieldName = 'QCL{}SetPulseRate'.format(qcl, param)
            validator = QIntValidator(bottom=0, top=int(pulseRateMax_Hz))
            self.inputField[fieldName][0].setValidator(validator)
            ### Pulse width validator
            fieldName = 'QCL{}SetPulseWidth'.format(qcl, param)
            validator = QIntValidator(bottom=0, top=int(pulseWidthMax_ns))
            self.inputField[fieldName][0].setValidator(validator)
            ### Current validators
            fieldName = 'QCL{}SetCurrent'.format(qcl, param)
            validator = QIntValidator(bottom=0, top=int(currentMax_mA))
            self.inputField[fieldName][0].setValidator(validator)
            fieldName = 'QCL{}SetCurrentPercent'.format(qcl, param)
            validator = QIntValidator(bottom=0, top=100)
            self.inputField[fieldName][0].setValidator(validator)
        ### Labels for QCL parameter readings
        self.readingLabels = dict()
        for x, param in enumerate(self.paramNames):
            col = x * 2 + 1 # every other column, starting at 1.
            for qcl in range(1, self.laser.numQCL + 1):
                row = 2 * qcl # Every other row, starting at 2.
                labelName = 'QCL{}{}'.format(qcl, param)
                self.readingLabels[labelName] = [QLabel(''), row, col, 1, 2]
        for _, k in self.readingLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_READ_ALT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        for row in range(0, 9): # Set row spacing
            self.grid.setRowStretch(row, 1)
        ### Populate UI with updated readings
        self.update_readings()
        ### Connect pulse rate/width inputs
        ### Update duty cycle when pulse rate/width inputs are changed
        ### Connecting one-by-one as workaround
        ### This is placed last to avoid triggering it while readings are blank
        self.inputField['QCL1SetPulseRate'][0].textChanged.connect(lambda:self.update_duty_cycle(1))
        self.inputField['QCL2SetPulseRate'][0].textChanged.connect(lambda:self.update_duty_cycle(2))
        self.inputField['QCL3SetPulseRate'][0].textChanged.connect(lambda:self.update_duty_cycle(3))
        self.inputField['QCL4SetPulseRate'][0].textChanged.connect(lambda:self.update_duty_cycle(4))
        self.inputField['QCL1SetPulseWidth'][0].textChanged.connect(lambda:self.update_duty_cycle(1))
        self.inputField['QCL2SetPulseWidth'][0].textChanged.connect(lambda:self.update_duty_cycle(2))
        self.inputField['QCL3SetPulseWidth'][0].textChanged.connect(lambda:self.update_duty_cycle(3))
        self.inputField['QCL4SetPulseWidth'][0].textChanged.connect(lambda:self.update_duty_cycle(4))

    def set_qcl_parameters(self, qcl):
        '''Read parameters for qcl module "qcl" from UI and set.'''
        print('Updating parameters for QCL module {:.0f}.'.format(qcl))
        ### Set button text
        btnName = 'QCL{:.0f}SetParameters'.format(qcl)
        btnText = '  Setting ...  '.format(qcl)
        self.btn[btnName][0].setText(btnText)
        ### Read maximum current for selected QCL module
        currentMax_mA = self.laser.get_current_maximum_pulsed(qcl)
        [pulseRateMax_Hz, pulseWidthMax_ns, dutyCycleMax] = self.laser.get_pulse_limits(qcl)
        ### Read QCL module parameters, as currently set
        initialPulseRate_Hz = self.laser.get_pulse_rate(qcl) # Hz
        initialPulseWidth_ns = self.laser.get_pulse_width(qcl) # ns
        initialCurrent_mA = self.laser.get_current(qcl) # mA
        initialCurrent_pc = currentMax_mA / 100 * initialCurrent_mA
        ### Read desired inputs
        try:
            fieldName = 'QCL{}SetPulseRate'.format(qcl)
            pulseRate_Hz = float(self.inputField[fieldName][0].text())
            fieldName = 'QCL{}SetPulseWidth'.format(qcl)
            pulseWidth_ns = float(self.inputField[fieldName][0].text())
            fieldName = 'QCL{}SetCurrent'.format(qcl)
            current_mA = float(self.inputField[fieldName][0].text())
            fieldName = 'QCL{}SetCurrentPercent'.format(qcl)
            current_pc = float(self.inputField[fieldName][0].text())
        except Exception as exc:
            print('Could not read input parameters:\n{}'.format(exc))
            btnText = '  Set QCL {:.0f} Parameters  '.format(qcl)
            self.btn[btnName][0].setChecked(False)
            self.btn[btnName][0].setText(btnText)
            self.update_readings()
            return
        ### If percentage setting has been changed, use it to set current
        if current_mA == initialCurrent_mA and current_pc != initialCurrent_pc:
            current_mA = currentMax_mA / 100 * current_pc
        ### Sanitize inputs
        if pulseRate_Hz < defaults.MIN_PULSERATE_HZ:
            pulseRate_Hz = defaults.MIN_PULSERATE_HZ
        if pulseRate_Hz > pulseRateMax_Hz:
            pulseRate_Hz = pulseRateMax_Hz
        if pulseWidth_ns < defaults.MIN_PULSEWIDTH_NS:
            pulseWidth_ns = defaults.MIN_PULSEWIDTH_NS
        if pulseWidth_ns > pulseWidthMax_ns:
            pulseWidth_ns = pulseWidthMax_ns
        if current_mA < 0:
            current_mA = 0
        if current_mA > currentMax_mA:
            current_mA = currentMax_mA
        ### Reduce pulse rate if duty cycle is too high
        dutyCycle = pulseRate_Hz * pulseWidth_ns * 1e-9 * 100
        if dutyCycle > dutyCycleMax:
            pulseRate_Hz = dutyCycleMax / (pulseWidth_ns * 1e-9 * 100)
            print('Requested duty cycle is too high, pulse rate has been reduced.')
        ### Set parameters
        self.laser.set_qcl_parameters(qcl, pulseRate_Hz, pulseWidth_ns, current_mA)
        ### Reset button text and update readings
        btnText = '  Set QCL {:.0f} Parameters  '.format(qcl)
        self.btn[btnName][0].setChecked(False)
        self.btn[btnName][0].setText(btnText)
        self.update_readings()

    def update_duty_cycle(self, qcl):
        '''Update duty cycle when pulse rate/width are changed.'''
        try:
            fieldName = 'QCL{}SetPulseRate'.format(qcl)
            pulseRate_Hz = float(self.inputField[fieldName][0].text())
            fieldName = 'QCL{}SetPulseWidth'.format(qcl)
            pulseWidth_ns = float(self.inputField[fieldName][0].text())
            dutyCycle = pulseRate_Hz * pulseWidth_ns * 1e-9 * 100
            fieldName = 'QCL{}SetDutyCycle'.format(qcl)
            self.inputField[fieldName][0].setText('{:.0f}'.format(dutyCycle))
            if dutyCycle > 20:
                self.inputField[fieldName][0].setStyleSheet(defaults.STYLE_INPUT_LOCKED_WARN)
            else:
                self.inputField[fieldName][0].setStyleSheet(defaults.STYLE_INPUT_LOCKED)
        except Exception as exc:
            print('Could not calculate duty cycle:\n{}'.format(exc))
            return

    def update_readings(self):
        '''Update QCL modules parameter readings.'''
        paramText = ['Hz', 'ns', '%', 'mA', '%']
        for qcl in range(1, self.laser.numQCL + 1):
            pulseRate = self.laser.get_pulse_rate(qcl) # Hz
            pulseWidth = self.laser.get_pulse_width(qcl) # ns
            current = self.laser.get_current(qcl) # mA
            currentMax_mA = self.laser.get_current_maximum_pulsed(qcl)
            currentPercent = current / currentMax_mA * 100
            dutyCycle = pulseRate * pulseWidth * 1E-9 * 100
            paramReadings = [pulseRate, pulseWidth, dutyCycle, current, currentPercent]
            for x, param in enumerate(self.paramNames):
                ### Update reading labels
                labelName = 'QCL{}{}'.format(qcl, param)
                labelText = '{:.0f} {}'.format(paramReadings[x], paramText[x])
                self.readingLabels[labelName][0].setText(labelText)
                ### Update input fields
                fieldName = 'QCL{}Set{}'.format(qcl, self.paramNames[x])
                self.inputField[fieldName][0].setText('{:.0f}'.format(paramReadings[x]))


class laserStartupDialog(QDialog):
    '''Show a dialog when laser is starting up.'''

    def __init__(self):
        super().__init__()
        self.make_dialog()

    def center_window(self):
        '''Center main application window on screen'''
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def make_dialog(self):
        '''Setup dialog window.
           Main UI window is disabled until laser is initialized.'''
        ### Window parameters
        self.setWindowTitle('Laser Initialization')
        self.setWindowIcon(QIcon('icons/mircat.ico'))
        self.setGeometry(0, 0, 200, 50)
        self.font = QFont()
        self.font.setFamily(defaults.FONT_FAMILY)
        self.font.setPointSize(defaults.FONT_SIZE)
        self.setStyleSheet(defaults.STYLE_CONTAINER)
        # self.setWindowModality(Qt.ApplicationModal) # Disable rest of UI
        ### Dialog text
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.textBox = QLabel('Initializing MIRcat laser. Please wait.')
        self.textBox.setFont(self.font)
        self.textBox.setStyleSheet(defaults.STYLE_LABEL_ALT)
        self.layout.addWidget(self.textBox)
        self.center_window()