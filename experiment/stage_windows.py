'''
stage_windows
Giovanni Sartorello (srtgnn@gmail.com)
UI elements for HLD117 stage
Python 3.9.6 on Windows 10
Created 2021-Dec-07
'''

import time
import experiment.defaults as defaults
from instruments.hld117 import stage
from ui.plot_widgets import mplCanvas
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QIntValidator, QIcon, QFont
from PyQt5.QtWidgets import (QAction,
                             QDesktopWidget,
                             QDialog,
                             QGridLayout,
                             QLabel,
                             QLineEdit,
                             QMainWindow,
                             QPushButton,
                             QWidget,
                             QSizePolicy,
                             QVBoxLayout)


class stageInitializer(QObject):
    '''Initialize stage'''
    stageInitialized = pyqtSignal() # Emitted when stage is initialized
    stageInstance = pyqtSignal(object) # Returns stage instance

    def __init__(self):
        super().__init__()

    def stage_initialize(self):
        stage0 = stage() # Initialize stage
        stage0.connect()
        stage0.identify()
        self.stageInstance.emit(stage0)
        self.stageInitialized.emit()


class stageMotionWindow(QMainWindow):
    '''GUI for stage motion control'''

    def __init__(self, mainGUI):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.paramNames = ['x_um', 'y_um', 'v_um_per_s', 'a_um_per_s2']
        self.stage = mainGUI.stage
        self.stage.set_acc() # Return acceleration to default
        self.stage.set_speed() # Return speed to default
        self.make_gui()

    def center_window(self):
        '''Center main application window on screen'''
        qtRectangle = self.frameGeometry()
        centerPoint = QDesktopWidget().availableGeometry().center()
        qtRectangle.moveCenter(centerPoint)
        self.move(qtRectangle.topLeft())

    def closeEvent(self, event): # Redefined from parent QMainWindow
        '''Show warning dialog on close.'''
        event.accept()

    def goto(self):
        '''Move to set x and y'''
        targetx = float(self.inputField['xSet'][0].text())
        targety = float(self.inputField['ySet'][0].text())
        print('Moving stage to ({:.0f} μm, {:.0f} μm)'.format(targetx, targety))
        try:
            self.stage.goto(targetx, targety)
            self.update_readings()
        except Exception as exc:
            print('Could not move stage:\n{}'.format(exc))
            return

    def make_gui(self):
        '''Draw controls'''
        self.setGeometry(0, 0, 600, 600)
        font = QFont()
        font.setFamily(defaults.FONT_FAMILY)
        font.setPointSize(defaults.FONT_SIZE)
        ### Set title, icon and center window
        self.setWindowTitle('Stage Motion')
        self.setWindowIcon(QIcon('icons/stage.ico'))
        self.center_window()
        ### Actions
        exitAction = QAction(QIcon(None), 'Close Window', self)
        exitAction.setShortcut('Ctrl+W')
        exitAction.setStatusTip('Close stage motion window')
        exitAction.triggered.connect(lambda: self.close())
        ### Menus
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(defaults.STYLE_MENUBAR)
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.setStyleSheet(defaults.STYLE_MENU)
        fileMenu.addAction(exitAction)
        ### Configure grid layout
        self.container = QWidget()
        self.container.setStyleSheet(defaults.STYLE_CONTAINER)
        self.setCentralWidget(self.container)
        self.grid = QGridLayout()
        self.container.setLayout(self.grid)
        self.grid.setSpacing(10)
        ### Plot: stage position
        self.plotCanvas = mplCanvas(width=5, height=4)
        self.plotCanvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.plotCanvas.axes.set_xlabel('x (μm)')
        self.plotCanvas.axes.set_ylabel('y (μm)')
        self.plotCanvas.axes.set_title('Stage Position')
        darkAxes = defaults.DARK_PLOT_AXES
        darkBackground = defaults.DARK_PLOT_BACKGROUND
        darkColor = defaults.PLOT_COLOR_DARK
        self.plotCanvas.recolor(darkAxes, darkBackground, darkColor)
        self.grid.addWidget(self.plotCanvas, 0, 0, 5, 6)
        ### Labels: header
        self.labels = dict() # [label, row, col, rowSpan, colSpan]
        # self.labels['Stage'] = [QLabel('Stage'), 0, 1, 1, 5]
        self.labels['Read'] = [QLabel('Read'), 5, 1, 1, 1]
        self.labels['Set'] = [QLabel('Set'), 5, 2, 1, 1]
        self.labels['Start'] = [QLabel('Start'), 5, 3, 1, 1]
        self.labels['Stop'] = [QLabel('Stop'), 5, 4, 1, 1]
        self.labels['Step'] = [QLabel('Step'), 5, 5, 1, 1]
        for _, k in self.labels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # Labels: units
        # unitLabelStrings = ['μm', 'μm', 'μm/s', 'μm/s²']
        # for x, labelText in enumerate(unitLabelStrings):
        #     row = x + 1 # Every row starting from 1
        #     labelObject = QLabel(labelText)
        #     labelObject.setFont(font)
        #     labelObject.setStyleSheet(defaults.STYLE_LABEL_UNIT)
        #     self.grid.addWidget(labelObject, row, 12, 1, 1)
        # Labels: axes
        # xLabel = QLabel('x')
        # xLabel.setFont(font)
        # xLabel.setStyleSheet(defaults.STYLE_LABEL_UNIT)
        # self.grid.addWidget(xLabel, 6, 3, 1, 1)
        # yLabel = QLabel('y')
        # yLabel.setFont(font)
        # yLabel.setStyleSheet(defaults.STYLE_LABEL_UNIT)
        # self.grid.addWidget(yLabel, 3, 0, 1, 1)
        # Labels: parameters
        self.paramLabels = dict() # [label, row, col, rowSpan, colSpan]
        self.paramLabels['x'] = [QLabel('x (μm)'), 6, 0, 1, 1]
        self.paramLabels['y'] = [QLabel('y (μm)'), 7, 0, 1, 1]
        self.paramLabels['v'] = [QLabel('v (μm/s)'), 8, 0, 1, 1]
        self.paramLabels['a'] = [QLabel('a (μm/s²)'), 9, 0, 1, 1]
        for _, k in self.paramLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Labels for QCL parameter readings
        blankLine = ''
        self.readingLabels = dict()
        for x, param in enumerate(self.paramNames):
            row = x + 6 # Start from row 6
            labelName = '{}'.format(param)
            self.readingLabels[labelName] = [QLabel(blankLine), row, 1, 1, 1]
        for _, k in self.readingLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_READ_ALT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Input fields: x/y set/start/stop/step and v/a
        blankLine = ''
        self.inputField = dict() # to collect all input fields
        self.inputField['xSet'] = [QLineEdit(blankLine), 6, 2, 1, 1]
        self.inputField['xStart'] = [QLineEdit(blankLine), 6, 3, 1, 1]
        self.inputField['xStop'] = [QLineEdit(blankLine), 6, 4, 1, 1]
        self.inputField['xStep'] = [QLineEdit(blankLine), 6, 5, 1, 1]
        self.inputField['ySet'] = [QLineEdit(blankLine), 7, 2, 1, 1]
        self.inputField['yStart'] = [QLineEdit(blankLine), 7, 3, 1, 1]
        self.inputField['yStop'] = [QLineEdit(blankLine), 7, 4, 1, 1]
        self.inputField['yStep'] = [QLineEdit(blankLine), 7, 5, 1, 1]
        self.inputField['vSet'] = [QLineEdit(blankLine), 8, 2, 1, 1]
        self.inputField['aSet'] = [QLineEdit(blankLine), 9, 2, 1, 1]
        for _, k in self.inputField.items(): # Arrange in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        # buttons
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['Start'] = [QPushButton('Start'), 10, 0, 2, 2]
        self.btn['Start'][0].setToolTip('Start raster scan')
        self.btn['Stop'] = [QPushButton('Stop'), 12, 0, 2, 2]
        self.btn['Stop'][0].setToolTip('Stop raster scan')
        for x, k in self.btn.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            k[0].setStyleSheet(defaults.STYLE_ARMED)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Set row stretch
        for row in range(0, 14): # Set row spacing
            self.grid.setRowStretch(row, 1)
        ### Fill in readings, and use as start values for inputs
        self.update_readings()
        ### Connecting one-by-one as workaround
        self.inputField['xSet'][0].returnPressed.connect(lambda: self.goto())
        self.inputField['ySet'][0].returnPressed.connect(lambda: self.goto())
        self.inputField['vSet'][0].returnPressed.connect(lambda: self.set_v())
        self.inputField['aSet'][0].returnPressed.connect(lambda: self.set_a())

    def set_a(self):
        '''Set acceleration'''
        targeta = float(self.inputField['aSet'][0].text())
        try:
            self.stage.set_acc(targeta)
            self.update_readings()
        except Exception as exc:
            print('Could not set acceleration:\n{}'.format(exc))
            return

    def set_v(self):
        '''Set speed'''
        targetv = float(self.inputField['vSet'][0].text())
        try:
            self.stage.set_speed(targetv)
            self.update_readings()
        except Exception as exc:
            print('Could not set speed:\n{}'.format(exc))
            return

    def update_readings(self):
        '''Update stage parameter readings.'''
        (x_um, y_um) = self.stage.get_position()
        # print('Stage position: {:.0f} μm, {:.0f} μm'.format(x_um, y_um))
        v_um_s = self.stage.get_speed()
        a_um_s2 = self.stage.get_acc()
        paramReadings = [x_um, y_um, v_um_s, a_um_s2]
        inputNames = ['x', 'y', 'v', 'a']
        for x, param in enumerate(self.paramNames):
            ### Update reading labels
            labelName = '{}'.format(param)
            labelText = '{:.0f}'.format(paramReadings[x])
            self.readingLabels[labelName][0].setText(labelText)
            ### Update input fields
            fieldName = '{}Set'.format(inputNames[x])
            self.inputField[fieldName][0].setText('{:.0f}'.format(paramReadings[x]))


class stageStartupDialog(QDialog):
    '''Show a dialog when stage is starting up.'''

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
           Main UI window is disabled until stage is initialized.'''
        ### Window parameters
        self.setWindowTitle('Stage Initialization')
        self.setWindowIcon(QIcon('icons/stage.ico'))
        self.setGeometry(0, 0, 200, 50)
        self.font = QFont()
        self.font.setFamily(defaults.FONT_FAMILY)
        self.font.setPointSize(defaults.FONT_SIZE)
        self.setStyleSheet(defaults.STYLE_CONTAINER)
        self.setWindowModality(Qt.ApplicationModal) # Disable rest of UI
        ### Dialog text
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.textBox = QLabel('Initializing HLD117 stage. Please wait.')
        self.textBox.setFont(self.font)
        self.textBox.setStyleSheet(defaults.STYLE_LABEL_ALT)
        self.layout.addWidget(self.textBox)
        self.center_window()