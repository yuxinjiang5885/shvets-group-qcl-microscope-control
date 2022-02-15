'''
stage_windows
Giovanni Sartorello (srtgnn@gmail.com)
UI elements for HLD117 stage
Python 3.9.6 on Windows 10
Created 2021-Dec-07
'''

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import experiment.defaults as defaults
from instruments.hld117 import stage
import time
from ui.plot_widgets import mplCanvas
from PyQt5.QtCore import Qt, QThread
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
                             QTabWidget,
                             QSizePolicy,
                             QVBoxLayout,
                             QWidget)


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

class stageMotion(QObject):
    '''Complex stage motion and scan patterns. Run in a separate thread.'''
    finished = pyqtSignal()
    currentPosition = pyqtSignal(int, int, list)
    stopped = False

    def __init__(self):
        '''Parameters must be set by caller for any method to work.'''
        super().__init__()
        self.parameters = [] # Parameters from caller, placeholder value

    def goto_and_wait(self, targetx, targety):
        '''Move to set x and y. Wait for stage to finish moving.'''
        try:
            self.parameters.stage.goto(targetx, targety)
            while int(self.parameters.stage.busy()) > 0:
                time.sleep(0.1)
        except Exception as exc:
            print('Could not move stage:\n{}'.format(exc))
            return

    def multiwell(self):
        '''Multiwell scan: move to a number of positions in a sequence, stop and
           dwell at each'''
        ### Read parameters
        xWells = self.parameters.xWells
        yWells = self.parameters.yWells
        xWellSep = self.parameters.xWellSep
        yWellSep = self.parameters.yWellSep
        angle = self.parameters.angle
        x1 = self.parameters.x1
        y1 = self.parameters.y1
        dwellTime = self.parameters.dwellTime
        ### Calculate positions vector
        positions = []
        for x in range(0, xWells):
            for y in range(0, yWells):
                xPos = x1 + x*xWellSep*np.cos(angle) - y*yWellSep*np.sin(angle)
                yPos = y1 + x*xWellSep*np.sin(angle) + y*yWellSep*np.cos(angle)
                positions.append([xPos, yPos])
        ### Scan positions
        for p in positions:
            if self.stopped:
                print('Stage scan interrupted by user')
                break
            self.goto_and_wait(p[0], p[1])
            self.currentPosition.emit(p[0], p[1], positions) # Send to plot
            time.sleep(dwellTime)
        self.stopped = False
        self.finished.emit()

    def stop(self):
        '''Set stop flag. Connect to UI stop button.'''
        self.stopped = True


class stageMotionParameters():
    '''Holds stage motion parameters, used by threaded run processes'''

    def __init__(self):
        self.stage = [] # Stage instance
        self.xWells = defaults.DEF_WELLS_X # Wells along x
        self.yWells = defaults.DEF_WELLS_Y # Wells along y
        self.xWellSep = defaults.DEF_WELL_SEP_X_UM # Well separation x, um
        self.yWellSep = defaults.DEF_WELL_SEP_Y_UM # Well separation y, um
        self.x1 = defaults.DEF_WELL_ORIGIN_X_UM # Origin/start well x, um
        self.y1 = defaults.DEF_WELL_ORIGIN_Y_UM # Origin/start well y, um
        self.x2 = defaults.DEF_WELL_CORNER_X_UM # Corner/end well x, um
        self.y2 = defaults.DEF_WELL_CORNER_Y_UM # Corner/end well y, um
        self.dwellTime = defaults.DEF_DWELL_TIME_S # Dwell time, s
        self.xCornerRel = self.x2 - self.x1 # Corner/end well relative x, um
        self.yCornerRel = self.y2 - self.y1 # Corner/end well relative y, um
        ### Inside size of well plate, as defined by scan path
        self.xLength = (defaults.DEF_WELLS_X - 1) * defaults.DEF_WELL_SEP_X_UM
        self.yLength = (defaults.DEF_WELLS_Y - 1) * defaults.DEF_WELL_SEP_Y_UM
        self.angle = 0 # Well plate angle

class stageMotionWindow(QMainWindow):
    '''GUI for stage motion control'''

    def __init__(self, mainGUI):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.paramNames = ['x_um', 'y_um', 'v_um_per_s', 'a_um_per_s2']
        self.stage = mainGUI.stage
        self.stage.set_acc() # Return acceleration to default
        self.stage.set_speed() # Return speed to default
        self.parameters = stageMotionParameters() # Passed to "run"
        self.threadMW = [] # Multiwell thread
        self.workerMW = [] # Multiwell worker
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

    def goto(self, targetx=-1, targety=-1):
        '''Move to set x and y.
           Note: there is no wait at the end for the stage to finish moving.'''
        if targetx == -1:
            targetx = float(self.inputField['xSet'][0].text())
        if targety == -1:
            targety = float(self.inputField['ySet'][0].text())
        print('Moving stage to ({:.0f} μm, {:.0f} μm)'.format(targetx, targety))
        try:
            self.stage.goto(targetx, targety)
            self.update_readings()
        except Exception as exc:
            print('Could not move stage:\n{}'.format(exc))
            return

    def lock_controls(self, lock=True):
        '''Disable all buttons while operations are performed.'''
        enabled = not lock # For the sake of clarity
        lockableControls = [self.btn['Start'],
                            self.inputField['xSet'],
                            self.inputField['ySet'],
                            self.inputField['vSet'],
                            self.inputField['aSet']]
        for k in lockableControls:
            k[0].setEnabled(enabled)

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
        updateAction = QAction(QIcon(None), 'Update readings', self)
        updateAction.setShortcut('Ctrl+U')
        updateAction.setStatusTip('Update x/y stage position readings')
        updateAction.triggered.connect(lambda: self.update_readings())
        ### Menus
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(defaults.STYLE_MENUBAR)
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.setStyleSheet(defaults.STYLE_MENU)
        fileMenu.addAction(exitAction)
        fileMenu.addAction(updateAction)
        ### Configure main grid layout
        self.container = QWidget()
        self.container.setStyleSheet(defaults.STYLE_CONTAINER)
        self.setCentralWidget(self.container)
        self.grid = QGridLayout()
        self.container.setLayout(self.grid)
        self.grid.setSpacing(10)
        ### Plot: stage position
        self.plotCanvas = mplCanvas(width=5, height=4)
        self.plotCanvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.plotCanvas.axes.set_aspect('equal')
        self.plotCanvas.axes.set_xlabel('x (μm)')
        xTravel = defaults.STAGE_X_TRAVEL_UM
        xMax = 1.1 * xTravel / 2
        xMin = -1 * xMax
        self.plotCanvas.axes.set_xlim(xMin, xMax)
        self.plotCanvas.axes.set_ylabel('y (μm)')
        yTravel = defaults.STAGE_Y_TRAVEL_UM
        yMax = 1.1 * yTravel / 2
        yMin = -1 * yMax
        self.plotCanvas.axes.set_ylim(yMin, yMax)
        self.plotCanvas.axes.invert_yaxis() # Positive y is towards user
        self.plotCanvas.axes.set_title('Stage Position')
        xMax = 1. * xTravel / 2
        xMin = -1 * xMax
        yMax = 1. * yTravel / 2
        yMin = -1 * yMax
        self.plotCanvas.axes.set_axisbelow(True)
        self.plotCanvas.axes.grid(color='gray', linestyle='dashed')
        patch = mpl.patches.Rectangle((xMin, yMin), xTravel, yTravel,
                                    alpha = 0.5,
                                    edgecolor = defaults.STG_COLORS['edge'],
                                    facecolor = defaults.STG_COLORS['fill'],
                                    fill = True,
                                    lw = 2,
                                    zorder = 1)
        self.plotCanvas.axes.add_patch(patch)
        darkAxes = defaults.DARK_PLOT_AXES
        darkBackground = defaults.DARK_PLOT_BACKGROUND
        darkColor = defaults.PLOT_COLOR_DARK
        self.plotCanvas.recolor(darkAxes, darkBackground, darkColor)
        self.grid.addWidget(self.plotCanvas, 0, 1, 4, 4)
        ### Tabs widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(defaults.STYLE_TABS)
        self.tabs.setFont(font)
        self.grid.addWidget(self.tabs, 5, 0, 5, 6)
        ### Raster tab - Base layout
        self.tabRaster = QWidget()
        self.tabRaster.setStyleSheet(defaults.STYLE_CONTAINER)
        self.tabs.addTab(self.tabRaster, 'Position/Raster')
        ### Raster tab - Grid layout
        self.tabRasterGrid = QGridLayout()
        self.tabRaster.setLayout(self.tabRasterGrid)
        self.tabRasterGrid.setSpacing(10)
        ### Raster tab - Labels: header
        self.labels = dict() # [label, row, col, rowSpan, colSpan]
        self.labels['Read'] = [QLabel('Read'), 5, 1, 1, 1]
        self.labels['Set'] = [QLabel('Set'), 5, 2, 1, 1]
        self.labels['Start'] = [QLabel('Start'), 5, 3, 1, 1]
        self.labels['Stop'] = [QLabel('Stop'), 5, 4, 1, 1]
        self.labels['Step'] = [QLabel('Step'), 5, 5, 1, 1]
        for _, k in self.labels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.tabRasterGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Raster tab - Labels: parameters
        self.paramLabels = dict() # [label, row, col, rowSpan, colSpan]
        self.paramLabels['x'] = [QLabel('x (μm)'), 6, 0, 1, 1]
        self.paramLabels['y'] = [QLabel('y (μm)'), 7, 0, 1, 1]
        self.paramLabels['v'] = [QLabel('v (μm/s)'), 8, 0, 1, 1]
        self.paramLabels['a'] = [QLabel('a (μm/s²)'), 9, 0, 1, 1]
        for _, k in self.paramLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.tabRasterGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Raster tab - Labels: readings
        blankLine = ''
        self.readingLabels = dict()
        for x, param in enumerate(self.paramNames):
            row = x + 6 # Start from row 6
            labelName = '{}'.format(param)
            self.readingLabels[labelName] = [QLabel(blankLine), row, 1, 1, 1]
        for _, k in self.readingLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_READ_ALT)
            self.tabRasterGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Raster tab - Input fields: x/y set/start/stop/step and v/a
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
            self.tabRasterGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Multiwell tab - Base layout
        self.tabMultiwell = QWidget()
        self.tabMultiwell.setStyleSheet(defaults.STYLE_CONTAINER)
        self.tabs.addTab(self.tabMultiwell, 'Multiwell')
        ### Multiwell tab - Grid layout
        self.tabMultiwellGrid = QGridLayout()
        self.tabMultiwell.setLayout(self.tabMultiwellGrid)
        self.tabMultiwellGrid.setSpacing(10)
        ### Multiwell tab - Labels: headers and parameters
        self.multiwellLabels = dict() # [label, row, col, rowSpan, colSpan]
        self.multiwellLabels['x'] = [QLabel('x'), 1, 0, 1, 1]
        self.multiwellLabels['y'] = [QLabel('y'), 2, 0, 1, 1]
        self.multiwellLabels['wells'] = [QLabel('Wells'), 0, 1, 1, 1]
        self.multiwellLabels['wellSeparation'] = [QLabel('Well Sep. (μm)'),
                                                                     0, 2, 1, 1]
        self.multiwellLabels['firstWell'] = [QLabel('First Well Pos. (μm)'),
                                                                     0, 3, 1, 1]
        self.multiwellLabels['lastWell'] = [QLabel('Last Well Pos. (μm)'),
                                                                     0, 4, 1, 1]
        self.multiwellLabels['dwell'] = [QLabel('Dwell time (s)'), 4, 0, 1, 2]
        for _, k in self.multiwellLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.tabMultiwellGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Multiwell tab - Input fields
        mwDef = ['{:.0f}'.format(defaults.DEF_WELLS_X),
                 '{:.0f}'.format(defaults.DEF_WELLS_Y),
                 '{:.0f}'.format(defaults.DEF_WELL_SEP_X_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_SEP_Y_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_ORIGIN_X_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_ORIGIN_Y_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_CORNER_X_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_CORNER_Y_UM),
                 '{:.3f}'.format(defaults.DEF_DWELL_TIME_S)]
        self.mwInputField = dict() # to collect all input fields
        self.mwInputField['xWells'] = [QLineEdit(mwDef[0]), 1, 1, 1, 1]
        self.mwInputField['yWells'] = [QLineEdit(mwDef[1]), 2, 1, 1, 1]
        self.mwInputField['xWellSep'] = [QLineEdit(mwDef[2]), 1, 2, 1, 1]
        self.mwInputField['yWellSep'] = [QLineEdit(mwDef[3]), 2, 2, 1, 1]
        self.mwInputField['wellx1'] = [QLineEdit(mwDef[4]), 1, 3, 1, 1]
        self.mwInputField['welly1'] = [QLineEdit(mwDef[5]), 2, 3, 1, 1]
        self.mwInputField['wellx2'] = [QLineEdit(mwDef[6]), 1, 4, 1, 1]
        self.mwInputField['welly2'] = [QLineEdit(mwDef[7]), 2, 4, 1, 1]
        self.mwInputField['dwell'] = [QLineEdit(mwDef[8]), 4, 3, 1, 1]
        for _, k in self.mwInputField.items(): # Arrange in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.tabMultiwellGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Buttons
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['Start'] = [QPushButton('Start'), 10, 0, 2, 3]
        self.btn['Start'][0].setToolTip('Start stage scan')
        self.btn['Stop'] = [QPushButton('Stop'), 10, 3, 2, 3]
        self.btn['Stop'][0].setToolTip('Stop stage scan')
        for x, k in self.btn.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            k[0].setStyleSheet(defaults.STYLE_ARMED)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Set stretch
        for row in range(0, 12):
            self.grid.setRowStretch(row, 1)
        for col in range(0, 6):
            self.grid.setColumnStretch(col, 1)
        ### Fill in readings, and use as start values for inputs
        self.update_readings()
        ### Connecting inputs one-by-one as workaround
        self.inputField['xSet'][0].returnPressed.connect(lambda: self.goto())
        self.inputField['ySet'][0].returnPressed.connect(lambda: self.goto())
        self.inputField['vSet'][0].returnPressed.connect(lambda: self.set_v())
        self.inputField['aSet'][0].returnPressed.connect(lambda: self.set_a())
        ### Connecting buttons
        self.btn['Start'][0].clicked.connect(lambda: self.run())

    def run(self):
        '''Run stage scan'''
        if self.tabs.currentIndex() not in [1]:
            print('Not implemented.')
        elif self.tabs.currentIndex() == 1:
            print('Running multiwell scan.')
            self.run_multiwell()

    def run_multiwell(self):
        '''Run multiwell holder scan'''
        ### Lock GUI controls
        self.lock_controls()
        # self.statusbar.showMessage('Busy')
        ### Read, calculate and compile experiment parameters
        self.parameters.stage = self.stage
        self.parameters.xWells = int(self.mwInputField['xWells'][0].text())
        self.parameters.yWells = int(self.mwInputField['yWells'][0].text())
        self.parameters.xWellSep = int(self.mwInputField['xWellSep'][0].text())
        self.parameters.yWellSep = int(self.mwInputField['yWellSep'][0].text())
        self.parameters.x1 = int(self.mwInputField['wellx1'][0].text())
        self.parameters.x2 = int(self.mwInputField['wellx2'][0].text())
        self.parameters.y1 = int(self.mwInputField['welly1'][0].text())
        self.parameters.y2 = int(self.mwInputField['welly2'][0].text())
        self.parameters.dwellTime = float(self.mwInputField['dwell'][0].text())
        x0 = self.parameters.x2 - self.parameters.x1
        y0 = self.parameters.y2 - self.parameters.y1
        xMW = (self.parameters.xWells - 1) * self.parameters.xWellSep
        yMW = (self.parameters.yWells - 1) * self.parameters.yWellSep
        sine = (y0 - (yMW/xMW)*x0) / (xMW + yMW**2/xMW)
        self.parameters.xCornerRel = x0
        self.parameters.yCornerRel = y0
        self.parameters.xLength = xMW
        self.parameters.yLength = yMW
        self.parameters.angle = np.arcsin(sine)
        positions = []
        ### Parameter checks
        # if self.parameters.start == self.parameters.end: # Requested limits are equal
        #     print('Limits cannot be equal.')
        #     self.btn['Start'][0].setChecked(False)
        #     # GUIInstance.btn['Stop'][0].setChecked(False)
        #     self.btn['Sweep'][0].setChecked(False)
        #     return
        ### Run stage scan in separate thread
        self.threadMW = QThread()
        self.workerMW = stageMotion()
        self.btn['Stop'][0].clicked.connect(self.workerMW.stop)
        self.workerMW.parameters = self.parameters
        self.workerMW.moveToThread(self.threadMW)
        self.threadMW.started.connect(self.workerMW.multiwell)
        self.workerMW.finished.connect(self.threadMW.quit)
        self.workerMW.finished.connect(self.workerMW.deleteLater)
        self.threadMW.finished.connect(self.threadMW.deleteLater)
        self.threadMW.start()
        ### Plot current position and pattern
        self.workerMW.currentPosition.connect(self.update_plot)
        ### Unlock GUI controls
        self.workerMW.finished.connect(lambda: self.lock_controls(lock=False))
        # self.workerMW.finished.connect(lambda: self.statusbar.showMessage('Ready'))
        ### Uncheck UI buttons
        self.workerMW.finished.connect(lambda: self.btn['Start'][0].setChecked(False))
        self.workerMW.finished.connect(lambda: self.btn['Stop'][0].setChecked(False))

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

    def update_plot(self, x=0, y=0, pattern=[]):
        '''Update stage position plot'''
        self.plotCanvas.clear_plots()
        if not pattern == []:
            for p in range (0, len(pattern) - 1):
                p1 = pattern[p]
                p2 = pattern[p + 1]
                xLine = [p1[0], p2[0]]
                yLine = [p1[1], p2[1]]
                line = self.plotCanvas.axes.plot(xLine, yLine, 'k')
                self.plotCanvas.plots.append(line[0])
                # self.plotCanvas.axes.arrow(0, 0, 0.01, np.sin(0.01), shape='full', lw=10,
                #         length_includes_head=True, head_width=.05, color='r')
        plot = self.plotCanvas.axes.scatter(x, y,
                                            c = defaults.STG_COLORS['marker'],
                                            marker = '+',
                                            zorder = 10)
        self.plotCanvas.plots.append(plot)
        if (np.abs(x) < 1000) or (np.abs(y) < 1000):
            textStr = '{:.0f}, {:.0f}'.format(x, y)
        else:
            textStr = '{:.0f},\n{:.0f}'.format(x, y)
        text = plt.text(x + 2000, y + 0, textStr,
                        color = defaults.STG_COLORS['text'],
                        fontsize = 10)
        self.plotCanvas.plots.append(text)
        titleString = 'Stage Position: x {:.0f} μm, y  {:.0f} μm'.format(x, y)
        self.plotCanvas.axes.set_title(titleString)
        self.plotCanvas.figure.canvas.draw()

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
        ### Update position plot
        self.update_plot(x_um, y_um)


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