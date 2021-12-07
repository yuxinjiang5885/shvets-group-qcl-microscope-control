'''
stage_windows
Giovanni Sartorello (srtgnn@gmail.com)
UI elements for HLD117 stage
Python 3.9.6 on Windows 10
Created 2021-Dec-07
'''

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


class stageMotionWindow(QMainWindow):
    '''GUI for stage motion control'''

    def __init__(self, mainGUI):
            super().__init__(None, Qt.WindowStaysOnTopHint)
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
            '''Move to set x and y when Enter is pressed'''
            targetx = float(self.inputField['xSet'][0].text())
            targety = float(self.inputField['ySet'][0].text())

    def make_gui(self):
        '''Draw controls'''
        self.setGeometry(0, 0, 1200, 600)
        font = QFont()
        font.setFamily(defaults.FONT_FAMILY)
        font.setPointSize(defaults.FONT_SIZE)
        ### Set title, icon and center window
        self.setWindowTitle('Stage Motion')
        self.setWindowIcon(QIcon('icons/mircat_ui.ico'))
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
        self.grid.addWidget(self.plotCanvas, 0, 0, 5, 5)
        ### Labels: header
        self.labels = dict() # [label, row, col, rowSpan, colSpan]
        # self.labels['Stage'] = [QLabel('Stage'), 0, 1, 1, 5]
        self.labels['Read'] = [QLabel('Read'), 0, 6, 1, 1]
        self.labels['Set'] = [QLabel('Set'), 0, 7, 1, 1]
        self.labels['Start'] = [QLabel('Start'), 0, 8, 1, 1]
        self.labels['Stop'] = [QLabel('Stop'), 0, 9, 1, 1]
        self.labels['Step'] = [QLabel('Step'), 0, 10, 1, 1]
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
        self.paramLabels['x'] = [QLabel('x (μm)'), 1, 5, 1, 1]
        self.paramLabels['y'] = [QLabel('y (μm)'), 2, 5, 1, 1]
        self.paramLabels['v'] = [QLabel('v (μm/s)'), 3, 5, 1, 1]
        self.paramLabels['a'] = [QLabel('a (μm/s²)'), 4, 5, 1, 1]
        for _, k in self.paramLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Input fields: x/y set/start/stop/step and v/a
        self.inputField = dict() # to collect all input fields
        self.inputField['xSet'] = [QLineEdit(''), 1, 7, 1, 1]
        self.inputField['xStart'] = [QLineEdit(''), 1, 8, 1, 1]
        self.inputField['xStop'] = [QLineEdit(''), 1, 9, 1, 1]
        self.inputField['xStep'] = [QLineEdit(''), 1, 10, 1, 1]
        self.inputField['ySet'] = [QLineEdit(''), 2, 7, 1, 1]
        self.inputField['yStart'] = [QLineEdit(''), 2, 8, 1, 1]
        self.inputField['yStop'] = [QLineEdit(''), 2, 9, 1, 1]
        self.inputField['yStep'] = [QLineEdit(''), 2, 10, 1, 1]
        self.inputField['v'] = [QLineEdit(''), 3, 7, 1, 1]
        self.inputField['a'] = [QLineEdit(''), 4, 7, 1, 1]
        for _, k in self.inputField.items(): # Arrange in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Connecting one-by-one as workaround
        # self.inputField['xSet'][0].returnPressed.connect(lambda: self.goto())
        # self.inputField['ySet'][0].returnPressed.connect(lambda: self.goto())