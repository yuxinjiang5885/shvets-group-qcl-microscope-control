# Modification: Keep gamepad UI updates on the GUI thread and coordinate shutdown.
# Author: Yuxin Jiang
# Email: yj546@cornell.edu

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
# from .software_joystick import Joystick
from .xbox_controller import xboxController
import time
from threading import Event, Lock
from time import perf_counter as timer, sleep
from ui.plot_widgets import mplCanvas
from PyQt6.QtCore import QThread
from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QFont
from PyQt6.QtWidgets import (QDialog,
                             QGridLayout,
                             QLabel,
                             QLineEdit,
                             QMainWindow,
                             QPushButton,
                             QTabWidget,
                             QSizePolicy,
                             QVBoxLayout,
                             QWidget)

class gamepad(QObject):
    '''Handle stage movement with gamepad'''
    stopped = pyqtSignal()

    readingsReady = pyqtSignal(float, float, float, float)
    failed = pyqtSignal(str)

    def __init__(self, stage_instance, step_text):
        super().__init__()
        self.updateInterval = defaults.GAMEPAD_UPDATE_INTERVAL_S
        self.stage = stage_instance
        self.gamepad = None
        self.stop_requested = Event()
        self.settings_lock = Lock()
        self.step_text = step_text

    def set_step_text(self, text):
        # Called by the GUI thread; the read loop does not process queued slots.
        with self.settings_lock:
            self.step_text = text

    def request_stop(self):
        self.stop_requested.set()

    def read(self):
        try:
            self.gamepad = xboxController()
            self.read_loop()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            try:
                self.stage.stop_smoothly()
            except Exception as exc:
                self.failed.emit(str(exc))
            finally:
                if self.gamepad is not None:
                    self.gamepad.stop()
                print('Gamepad stopped')
                self.stopped.emit()

    def find_index_of_nearest(self, array, value):
        '''https://stackoverflow.com/a/2566508'''
        array = np.asarray(array)
        i = (np.abs(array - value)).argmin()
        return i

    def read_loop(self):
        ### Initialize parameters
        deadzone = defaults.JOY_DEADZONE
        self.stage_speed = self.stage.get_speed() # um/s
        ### Initialize triggering flags for buttons
        ### A button should give a single input until released
        hatTriggered = False
        leftBumperTriggered = False
        rightBumperTriggered = False
        ### Start read loop
        while not self.stop_requested.is_set():
            start = timer()
            ### Read gamepad inputs
            gamepadInput = self.gamepad.read()
            # print(gamepadInput)
            xJoyL = gamepadInput[0]
            yJoyL = gamepadInput[1]
            pushJoyL = gamepadInput[2]
            xJoyR = gamepadInput[3]
            yJoyR = gamepadInput[4]
            pushJoyR = gamepadInput[5]
            hatX = gamepadInput[6]
            hatY = gamepadInput[7]
            btnA = gamepadInput[8]
            btnB = gamepadInput[9]
            btnX = gamepadInput[10]
            btnY = gamepadInput[11]
            leftBumper = gamepadInput[12]
            rightBumper = gamepadInput[13]
            leftTrigger = gamepadInput[14]
            rightTriger = gamepadInput[15]
            startBtn = gamepadInput[16]
            selectBtn = gamepadInput[17]
            ### Send commands: buttons pressed
            if selectBtn == 1:
                ### Menu button: stop loop
                self.request_stop()
                break
            elif (hatX != 0) or (hatY != 0):
                ### Hat: move by step at maximum speed
                if not hatTriggered:
                    with self.settings_lock:
                        self.step = float(self.step_text)
                    xRel = hatX * self.step
                    yRel = hatY * self.step
                    current_speed = self.stage.get_speed()
                    self.stage.set_speed(self.stage.speeds[-1])
                    self.stage.move_rel(xRel, yRel)
                    self.stage.set_speed(current_speed)
                hatTriggered = True
            elif pushJoyL == 1:
                ### Left thumbstick pushed: return to origin
                self.stage.goto(0, 0)
            elif (np.abs(xJoyL) > deadzone) or (np.abs(yJoyL) > deadzone):
                vx = xJoyL * self.stage_speed
                vy = -1 * yJoyL * self.stage_speed
                self.stage.move_at_velocity(vx, vy)
            elif btnB == 1:
                self.stage.stop_smoothly()
            elif leftBumper == 1:
                if not leftBumperTriggered:
                    i = self.find_index_of_nearest(self.stage.speeds, self.stage_speed)
                    if i > 0:
                        self.stage.set_speed(self.stage.speeds[i-1])
                        self.stage_speed = self.stage.get_speed()
                leftBumperTriggered = True
            elif rightBumper == 1:
                if not rightBumperTriggered:
                    i = self.find_index_of_nearest(self.stage.speeds, self.stage_speed)
                    if i < (len(self.stage.speeds) - 1):
                        self.stage.set_speed(self.stage.speeds[i+1])
                        self.stage_speed = self.stage.get_speed()
                rightBumperTriggered = True
            ### Send commands: buttons not pressed
            if (hatX == 0) and (hatY == 0):
                hatTriggered = False
            if leftBumper == 0:
                leftBumperTriggered = False
            if rightBumper == 0:
                rightBumperTriggered = False
            if (np.abs(xJoyL) <= deadzone) and (np.abs(yJoyL) <= deadzone):
                ### Left thumbstick centered: stop moving stage
                self.stage.move_at_velocity(0, 0)
            ### No inputs and stage not busy: update position reading
            if self.stage.busy() in ['0']:
                x, y = self.stage.get_position()
                self.readingsReady.emit(x, y, self.stage.get_speed(), self.stage.get_acc())
            ### Wait out update interval, waking promptly on a stop request.
            self.stop_requested.wait(max(0, self.updateInterval - (timer() - start)))


class gamepadBindingsWindow(QMainWindow):
    '''Shows gamepad bindings'''

    def __init__(self):
        super().__init__()
        self.make_gui()

    def center_window(self):
        '''Center window on screen'''
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def make_gui(self):
        '''Create UI with grid layout'''
        ### Set size
        self.setGeometry(0, 0, 675, 380)
        ### Add central widget
        # self.container = QWidget()
        # self.setCentralWidget(self.container)
        ### Center on screen
        self.center_window()
        ### Set fonts
        fontSmall = QFont()
        fontSmall.setFamily(defaults.FONT_FAMILY)
        fontSmall.setPointSize(defaults.FONT_SIZE_TINY)
        ### Set title and icon
        self.setWindowTitle('Gamepad Bindings')
        self.setWindowIcon(QIcon('icons/xbox.png'))
        ### Actions
        exitAction = QAction(QIcon(None), 'Close Window', self)
        exitAction.setShortcut('Ctrl+W')
        exitAction.setToolTip('Close stage motion window')
        exitAction.triggered.connect(lambda: self.close())
        ### Bars
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(defaults.STYLE_MENUBAR)
        ### Menus
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.setStyleSheet(defaults.STYLE_MENU)
        fileMenu.addAction(exitAction)
        ### Set controller picture as background
        self.setStyleSheet(defaults.STYLE_GAMEPAD_BINDINGS_WINDOW)
        ### Set text
        self.labels = dict() # [label, pixels x, pixels y]
        noteText = 'CONNECT GAMEPAD TO PC BEFORE LAUNCHING UI'
        self.labels['Note'] = [QLabel(noteText, self), 5, 25]
        self.labels['ConnectToPC'] = [QLabel('Connect to PC', self), 170, 70]
        self.labels['StopGamepad'] = [QLabel('Stop\ngamepad', self), 170, 100]
        self.labels['Move'] = [QLabel('Move stage\nPress: return to zero', self), 20, 120]
        self.labels['MoveByStep'] = [QLabel('Move by step', self), 150, 225]
        self.labels['StopStage'] = [QLabel('Stop stage', self), 325, 130]
        self.labels['IncreaseSpeed'] = [QLabel('Increase Speed', self), 370, 30]
        self.labels['DecreaseSpeed'] = [QLabel('Decrease Speed', self), 530, 40]
        for _, k in self.labels.items(): # Arrange labels in grid
            l = k[0]
            l.setFont(fontSmall)
            l.setStyleSheet(defaults.STYLE_LABEL_GAMEPAD)
            l.move(k[1], k[2])
            l.adjustSize()


class stageInitializer(QObject):
    '''Initialize stage'''
    stageInitialized = pyqtSignal() # Emitted when stage is initialized
    stageInstance = pyqtSignal(object) # Returns stage instance

    def __init__(self, MODEL = 'HLD117', COM_PORT = defaults.STAGE_DEF_COM_PORT):
        super().__init__()
        self.stageModel = MODEL
        self.COMPort = COM_PORT

    def stage_initialize(self):
        stage0 = stage(model = self.stageModel) # Initialize stage
        stage0.connect(self.COMPort)
        stage0.identify()
        self.stageInstance.emit(stage0)
        self.stageInitialized.emit()
        '''
        How to return the stage position to make life easier?
        Po-Ting Shen
        05/12/2023
        '''
        #return stage0.get_position()


class stageMotion(QObject):
    '''Complex stage motion and scan patterns. Run in a separate thread.'''
    finished = pyqtSignal()
    currentPosition = pyqtSignal(float, float, list, list)
    stopped = False

    def __init__(self, mainGUI):
        '''Parameters must be set by caller for any method to work.'''
        super().__init__()
        self.parameters = [] # Parameters from caller, placeholder value
        self.mainGUI = mainGUI

    def goto_and_wait(self, xTarget, yTarget):
        '''Move to set x and y. Wait for stage to finish moving.'''
        try:
            self.parameters.stage.goto(xTarget, yTarget)
            while int(self.parameters.stage.busy()) > 0:
                time.sleep(0.1)
        except Exception as exc:
            print('Could not move stage:\n{}'.format(exc))
            return

    def multiwell(self):
        '''Multiwell scan: move to a number of positions in a sequence, stop and
           dwell at each'''
        ### Read parameters
        acquisitions = self.parameters.acquisitions
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
                ### Calculate positons. Note: stage y axis is inverted.
                if xWells > 1 and yWells > 1:
                    xPos = x1 + x*xWellSep*np.cos(angle) - y*yWellSep*np.sin(angle)
                    yPos = y1 + -1 * x*xWellSep*np.sin(angle) + -1 * y*yWellSep*np.cos(angle)
                else:
                    xPos = x1 + x*xWellSep*np.cos(angle) - y*yWellSep*np.cos(angle)
                    yPos = y1 + -1 * x*xWellSep*np.sin(angle) + -1 * y*yWellSep*np.sin(angle)
                positions.append([xPos, yPos])
        if self.parameters.reverse:
            positions.reverse()
        ### Start timer
        start = timer()
        ### Scan positions
        numPositions = len(positions)
        for a in range(0, acquisitions):
            if self.stopped:
                break
            for i, p in enumerate(positions):
                if self.stopped:
                    print('Stage scan interrupted by user')
                    break
                self.goto_and_wait(p[0], p[1])
                acqStatus = [acquisitions, a + 1]
                self.currentPosition.emit(p[0], p[1], positions, acqStatus) # Send to plot
                # time.sleep(dwellTime)
                print('Acquisition {:.0f}, position {:.0f}'.format(a + 1, i + 1))
                targetTime = ((a * dwellTime * numPositions)) + ((i + 1) * dwellTime)
                while timer()-start < targetTime:
                    print('Time: {:.3f} s'.format(timer()-start), end='\r')
                    sleep(defaults.DEF_SLEEP_INTERVAL)
                print('') # End line
        self.stopped = False
        self.finished.emit()

    def stop(self):
        '''Set stop flag. Connect to UI stop button.'''
        self.stopped = True


class stageMotionParameters():
    '''Holds stage motion parameters, used by threaded run processes'''

    def __init__(self):
        self.stage = [] # Stage instance
        self.acquisitions = defaults.DEF_NUMBER_OF_ACQ # Number of acquisitions
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
        self.reverse = False # Reverse pattern direction


class stageMotionWindow(QMainWindow):
    '''GUI for stage motion control'''
    # Define a signal that accepts a tuple
    current_stage_position = pyqtSignal(tuple)
    def __init__(self, mainGUI, model = 'HLD117'):
        super().__init__()
        self.paramNames = ['x_um', 'y_um', 'v_um_per_s', 'a_um_per_s2']
        self.mainGUI = mainGUI
        self.stage = mainGUI.stage
        self.stage.set_acc() # Return acceleration to default
        self.stage.set_speed() # Return speed to default
        self.stage.joystick(enable = False) # Disable hardware joystick
        self.parameters = stageMotionParameters() # Passed to "run"
        self.threadMW = [] # Multiwell thread
        self.workerMW = [] # Multiwell worker
        self.threadG = None # Gamepad thread
        self.workerG = None # Gamepad worker
        self.gamepadBindingsWindow = gamepadBindingsWindow()
        if model in ['H117', 'h117']:
            self.xTravel = defaults.H117_X_TRAVEL_UM
            self.yTravel = defaults.H117_Y_TRAVEL_UM
        else:
            self.xTravel = defaults.HLD117_X_TRAVEL_UM
            self.yTravel = defaults.HLD117_Y_TRAVEL_UM
        self.make_gui()
    def get_stage(self):
        return self.stage
    def center_window(self):
        '''Center main application window on screen'''
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    # def closeEvent(self, event): # Redefined from parent QMainWindow
    #     '''Show warning dialog on close.'''
    #     event.accept()

    def gamepad_bindings(self):
        '''View gamepad bindings'''
        self.gamepadBindingsWindow.show()

    def goto(self, xTarget=-1, yTarget=-1):
        '''Move to set x and y. Wait for the stage to finish moving.'''
        if xTarget == -1:
            xTarget = float(self.inputField['xSet'][0].text())
        if yTarget == -1:
            yTarget = float(self.inputField['ySet'][0].text())
        print('Moving stage to ({:.0f} μm, {:.0f} μm)'.format(xTarget, yTarget))
        try:
            self.stage.goto(xTarget, yTarget)
            while int(self.stage.busy()) > 0:
                time.sleep(0.1)
            self.update_readings()

        except Exception as exc:
            print('Could not move stage:\n{}'.format(exc))
            return

    def goto_gamepad(self):
        """Control stage with gamepad; keep references until the thread finishes."""
        if self.threadG is not None:
            return
        self.threadG = QThread()
        self.workerG = gamepad(self.stage, self.inputField['stepSet'][0].text())
        self.workerG.moveToThread(self.threadG)
        self.workerG.readingsReady.connect(self.apply_gamepad_readings,
                                          Qt.ConnectionType.QueuedConnection)
        self.workerG.failed.connect(self.gamepad_error, Qt.ConnectionType.QueuedConnection)
        self.workerG.stopped.connect(self.workerG.deleteLater)
        # quit() is thread-safe; direct delivery lets stop_gamepad() wait safely.
        self.workerG.stopped.connect(self.threadG.quit, Qt.ConnectionType.DirectConnection)
        self.threadG.started.connect(self.workerG.read)
        self.threadG.finished.connect(self.gamepad_finished)
        self.threadG.start()

    @pyqtSlot(str)
    def update_gamepad_step(self, text):
        if self.workerG is not None:
            self.workerG.set_step_text(text)

    @pyqtSlot(float, float, float, float)
    def apply_gamepad_readings(self, x, y, speed, acceleration):
        if (self.workerG is not None and self.sender() is self.workerG
                and not self.workerG.stop_requested.is_set()):
            self.apply_readings(x, y, speed, acceleration)

    @pyqtSlot(str)
    def gamepad_error(self, message):
        print('Gamepad error: {}'.format(message))

    @pyqtSlot()
    def gamepad_finished(self):
        if self.threadG is not None and self.sender() is self.threadG:
            self.release_gamepad()

    def release_gamepad(self):
        thread = self.threadG
        self.threadG = None
        self.workerG = None
        self.inputMethods['gp'][0].setChecked(False)
        if thread is not None:
            thread.deleteLater()

    def stop_gamepad(self):
        """Wait for stage commands to finish before handing control to another caller."""
        if self.threadG is None:
            return True
        self.workerG.request_stop()
        if not self.threadG.wait(3000):
            print('Gamepad is still stopping; retry after the current stage command finishes.')
            return False
        self.release_gamepad()
        return True

    def disable_stage_inputs(self):
        if not self.stop_gamepad():
            return False
        self.stage.joystick(enable=False)
        self.inputMethods['hw'][0].setChecked(False)
        print('All stage joysticks disabled')
        return True

    def goto_joystick(self, joystickPosition):
        '''Move stage according to software joystick position'''
        angle = joystickPosition[0]
        speed = joystickPosition[1]
        print('Joystick angle : {}, speed: {}'.format(angle, speed))

    def joystick(self, selected='hardware'):
        '''Enables or disables hardware joystick, software joystick, and gamepad'''
        if selected == 'hardware':
            if self.inputMethods['hw'][0].isChecked():
                # self.hwJoystickEnable.setChecked(True)
                # self.inputMethods['hw'][0].setChecked(True)
                try:
                    self.stage.joystick(enable=True)
                    print('Hardware joystick enabled')
                except Exception as exc:
                    print('Could not enable hardware joystick:\n{}'.format(exc))
                    self.inputMethods['hw'][0].setStyleSheet(defaults.STYLE_BUTTON_JOY_FAULT)
                    self.inputMethods['hw'][0].setChecked(False)
                    self.inputMethods['hw'][0].setCheckable(False)
            else:
                # self.hwJoystickEnable.setChecked(False)
                # self.inputMethods['hw'][0].setChecked(False)
                self.stage.joystick(enable=False)
                print('Hardware joystick disabled')
        elif selected == 'software':
            if self.inputMethods['sw'][0].isChecked():
                # self.swJoystickEnable.setChecked(False)
                self.inputMethods['sw'][0].setChecked(False)
                # print('Software joystick enabled')
                print('Software joystick not implemented')
                self.inputMethods['sw'][0].setStyleSheet(defaults.STYLE_BUTTON_JOY_FAULT)
            else:
                pass
                # print('Software joystick disabled')
        elif selected == 'gamepad':
            if self.inputMethods['gp'][0].isChecked():
                # self.gamepadEnable.setChecked(True)
                # self.inputMethods['gp'][0].setChecked(True)
                self.goto_gamepad()
                print('Gamepad enabled')
            else:
                # self.gamepadEnable.setChecked(False)
                # self.inputMethods['gp'][0].setChecked(False)
                if not self.stop_gamepad():
                    self.inputMethods['gp'][0].setChecked(True)
                print('Gamepad disabled')

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
        self.setGeometry(0, 0, 600, 800)
        font = QFont()
        font.setFamily(defaults.FONT_FAMILY)
        font.setPointSize(defaults.FONT_SIZE)
        fontSmall = QFont()
        font.setFamily(defaults.FONT_FAMILY)
        fontSmall.setPointSize(defaults.FONT_SIZE_SMALL)
        ### Set title, icon and center window
        self.setWindowTitle('Stage Motion')
        self.setWindowIcon(QIcon('icons/stage.ico'))
        self.center_window()
        ### Actions
        exitAction = QAction(QIcon(None), 'Close Window', self)
        exitAction.setShortcut('Ctrl+W')
        exitAction.setToolTip('Close stage motion window')
        exitAction.triggered.connect(lambda: self.close())
        updateAction = QAction(QIcon(None), 'Update readings', self)
        updateAction.setShortcut('Ctrl+R')
        updateAction.setToolTip('Update x/y stage position readings')
        updateAction.triggered.connect(lambda: self.update_readings())
        gamepadBindingsAction = QAction(QIcon(None), 'Gamepad bindings', self)
        gamepadBindingsAction.setShortcut('Ctrl+G')
        gamepadBindingsAction.setToolTip('View gamepad bindings')
        gamepadBindingsAction.triggered.connect(lambda: self.gamepad_bindings())
        ### Control options
        # self.hwJoystickEnable = QAction(QIcon(None), 'Enable hardware joystick',
        #                                 self, checkable=True, checked=True)
        # self.swJoystickEnable = QAction(QIcon(None), 'Enable software joystick',
        #                                 self, checkable=True, checked=False)
        # self.gamepadEnable = QAction(QIcon(None), 'Enable gamepad',
        #                              self, checkable=True, checked=False)
        ### Connect control options
        # self.hwJoystickEnable.triggered.connect(lambda: self.joystick(selected='hardware'))
        # self.swJoystickEnable.triggered.connect(lambda: self.joystick(selected='software'))
        # self.gamepadEnable.triggered.connect(lambda: self.joystick(selected='gamepad'))
        ### Pattern options
        self.reverse = QAction(QIcon(None), 'Reverse pattern', self, checkable=True)
        self.reverse.setShortcut('Ctrl+R')
        self.reverse.setToolTip('Reverse pattern direction')
        self.timeBehavior = QAction(QIcon(None), 'Include move time in step', self, checkable=True)
        self.timeBehavior.setToolTip('Stage move time is included in step total')
        self.timeBehavior.setChecked(True)
        self.timeBehavior.setEnabled(False)
        ### Menus
        self.menubar = self.menuBar()
        self.menubar.setStyleSheet(defaults.STYLE_MENUBAR)
        fileMenu = self.menubar.addMenu('Actions')
        fileMenu.setStyleSheet(defaults.STYLE_MENU)
        fileMenu.addAction(exitAction)
        fileMenu.addAction(updateAction)
        # controlMenu = self.menubar.addMenu('Control')
        # controlMenu.setStyleSheet(defaults.STYLE_MENU)
        # controlMenu.addAction(self.hwJoystickEnable)
        # controlMenu.addAction(self.swJoystickEnable)
        # controlMenu.addAction(self.gamepadEnable)
        patternMenu = self.menubar.addMenu('Patterns')
        patternMenu.setStyleSheet(defaults.STYLE_MENU)
        patternMenu.addAction(self.reverse)
        patternMenu.addAction(self.timeBehavior)
        helpMenu = self.menubar.addMenu('Help')
        helpMenu.setStyleSheet(defaults.STYLE_MENU)
        helpMenu.addAction(gamepadBindingsAction)
        ### Configure main grid layout
        self.container = QWidget()
        self.container.setStyleSheet(defaults.STYLE_CONTAINER)
        self.setCentralWidget(self.container)
        self.grid = QGridLayout()
        self.container.setLayout(self.grid)
        self.grid.setSpacing(10)
        ### Stage controls - container
        self.stgControls = QWidget()
        self.stgControls.setStyleSheet(defaults.STYLE_CONTAINER)
        self.stgControls.setFont(font)
        self.grid.addWidget(self.stgControls, 0, 0, 2, 6)
        ### Stage controls - Grid layout
        self.stgControlsGrid = QGridLayout()
        self.stgControls.setLayout(self.stgControlsGrid)
        self.stgControlsGrid.setSpacing(10)
        ### Stage controls - Input method selectors
        self.inputMethods = dict() # [label, row, col, rowSpan, colSpan]
        self.inputMethods['hw'] = [QPushButton('HW\nJOY'), 0, 0, 2, 1]
        self.inputMethods['hw'][0].setToolTip('Enable hardware joystick')
        self.inputMethods['sw'] = [QPushButton('SW\nJOY'), 0, 1, 2, 1]
        self.inputMethods['sw'][0].setToolTip('Enable software joystick')
        self.inputMethods['gp'] = [QPushButton('GAME\nPAD'), 0, 2, 2, 1]
        self.inputMethods['gp'][0].setToolTip('Enable gamepad')
        for _, k in self.inputMethods.items(): # Arrange labels in grid
            k[0].setCheckable(True)
            # k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(fontSmall)
            k[0].setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            k[0].setStyleSheet(defaults.STYLE_BUTTON_JOY)
            self.stgControlsGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Stage controls - Labels
        self.stgLabels = dict() # [label, row, col, rowSpan, colSpan]
        self.stgLabels['x'] = [QLabel('x (μm)'), 0, 3, 1, 1]
        self.stgLabels['y'] = [QLabel('y (μm)'), 0, 4, 1, 1]
        self.stgLabels['v'] = [QLabel('v (μm/s)'), 0, 5, 1, 1]
        self.stgLabels['a'] = [QLabel('a (μm/s²)'), 0, 6, 1, 1]
        self.stgLabels['step'] = [QLabel('step (μm)'), 0, 7, 1, 1]
        for _, k in self.stgLabels.items(): # Arrange labels in grid
            k[0].setFont(fontSmall)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.stgControlsGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Stage controls - input fields
        blankLine = ''
        initStep = '{:.0f}'.format(defaults.STAGE_DEF_X_STEP_UM)
        self.inputField = dict() # to collect all input fields
        self.inputField['xSet'] = [QLineEdit(blankLine), 1, 3, 1, 1]
        self.inputField['ySet'] = [QLineEdit(blankLine), 1, 4, 1, 1]
        self.inputField['vSet'] = [QLineEdit(blankLine), 1, 5, 1, 1]
        self.inputField['aSet'] = [QLineEdit(blankLine), 1, 6, 1, 1]
        self.inputField['stepSet'] = [QLineEdit(initStep), 1, 7, 1, 1]
        for _, k in self.inputField.items(): # Arrange in grid
            k[0].setFont(fontSmall)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.stgControlsGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Plot: stage position
        self.plotCanvas = mplCanvas(width=5, height=4)
        self.plotCanvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.plotCanvas.axes.set_aspect('equal')
        self.plotCanvas.axes.set_xlabel('x (μm)')
        xTravel = self.xTravel
        xMax = 1.1 * xTravel / 2
        xMin = -1 * xMax
        self.plotCanvas.axes.set_xlim(xMin, xMax)
        self.plotCanvas.axes.set_ylabel('y (μm)')
        yTravel = self.yTravel
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
        self.grid.addWidget(self.plotCanvas, 2, 1, 4, 4)
        ### Tabs widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(defaults.STYLE_TABS)
        self.tabs.setFont(font)
        self.grid.addWidget(self.tabs, 7, 0, 5, 6)
        ### Position tab - Base layout
        self.tabPos = QWidget()
        self.tabPos.setStyleSheet(defaults.STYLE_CONTAINER)
        self.tabs.addTab(self.tabPos, 'Position')
        ### Position tab - Grid layout
        self.tabPosGrid = QGridLayout()
        self.tabPos.setLayout(self.tabPosGrid)
        self.tabPosGrid.setSpacing(10)
        ### Position tab - Labels: header
        self.labels = dict() # [label, row, col, rowSpan, colSpan]
        self.labels['Read'] = [QLabel('Read'), 5, 1, 1, 1]
        self.labels['Set'] = [QLabel('Set'), 5, 2, 1, 1]
        self.labels['Start'] = [QLabel('Joystick'), 5, 3, 1, 3]
        # self.labels['Start'] = [QLabel('Start'), 5, 3, 1, 1]
        # self.labels['Stop'] = [QLabel('Stop'), 5, 4, 1, 1]
        # self.labels['Step'] = [QLabel('Step'), 5, 5, 1, 1]
        for _, k in self.labels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.tabPosGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Position tab - Labels: parameters
        # self.paramLabels = dict() # [label, row, col, rowSpan, colSpan]
        # self.paramLabels['x'] = [QLabel('x (μm)'), 6, 0, 1, 1]
        # self.paramLabels['y'] = [QLabel('y (μm)'), 7, 0, 1, 1]
        # self.paramLabels['v'] = [QLabel('v (μm/s)'), 8, 0, 1, 1]
        # self.paramLabels['a'] = [QLabel('a (μm/s²)'), 9, 0, 1, 1]
        # for _, k in self.paramLabels.items(): # Arrange labels in grid
        #     k[0].setFont(font)
        #     k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
        #     self.tabPosGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Position tab - Labels: readings
        blankLine = ''
        self.readingLabels = dict()
        for x, param in enumerate(self.paramNames):
            row = x + 6 # Start from row 6
            labelName = '{}'.format(param)
            self.readingLabels[labelName] = [QLabel(blankLine), row, 1, 1, 1]
        for _, k in self.readingLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_READ_ALT)
            self.tabPosGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Position tab - Input fields: x/y set/start/stop/step and v/a
        # blankLine = ''
        # self.inputField = dict() # to collect all input fields
        # self.inputField['xSet'] = [QLineEdit(blankLine), 6, 2, 1, 1]
        # self.inputField['xStart'] = [QLineEdit(blankLine), 6, 3, 1, 1]
        # self.inputField['xStop'] = [QLineEdit(blankLine), 6, 4, 1, 1]
        # self.inputField['xStep'] = [QLineEdit(blankLine), 6, 5, 1, 1]
        # self.inputField['ySet'] = [QLineEdit(blankLine), 7, 2, 1, 1]
        # self.inputField['yStart'] = [QLineEdit(blankLine), 7, 3, 1, 1]
        # self.inputField['yStop'] = [QLineEdit(blankLine), 7, 4, 1, 1]
        # self.inputField['yStep'] = [QLineEdit(blankLine), 7, 5, 1, 1]
        # self.inputField['vSet'] = [QLineEdit(blankLine), 8, 2, 1, 1]
        # self.inputField['aSet'] = [QLineEdit(blankLine), 9, 2, 1, 1]
        # for _, k in self.inputField.items(): # Arrange in grid
        #     k[0].setFont(font)
        #     k[0].setStyleSheet(defaults.STYLE_INPUT)
        #     self.tabPosGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Position tab - Joystick
        # self.swJoystick = Joystick()
        # self.swJoystick.joystickInput.connect(self.goto_joystick)
        # self.tabPosGrid.addWidget(self.swJoystick, 6, 3, 4, 3)
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
        self.multiwellLabels['firstWell'] = [QLabel('Bottom Left (μm)'),
                                                                     0, 3, 1, 1]
        self.multiwellLabels['lastWell'] = [QLabel('Top Right (μm)'),
                                                                     0, 4, 1, 1]
        self.multiwellLabels['header2'] = [QLabel(''), 3, 0, 1, 5]
        self.multiwellLabels['dwell'] = [QLabel('Dwell time (s): '), 4, 1, 1, 1]
        self.multiwellLabels['acquisitions'] = [QLabel('Acquisitions: '), 4, 3, 1, 1]
        # self.multiwellLabels['dwell'][0].setAlignment(Qt.AlignCenter)
        for _, k in self.multiwellLabels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.tabMultiwellGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Adjust alignment of select labels
        self.multiwellLabels['dwell'][0].setStyleSheet(defaults.STYLE_LABEL_EMPH_CENTER)
        self.multiwellLabels['acquisitions'][0].setStyleSheet(defaults.STYLE_LABEL_EMPH_CENTER)
        ### Multiwell tab - Input fields
        mwDef = ['{:.0f}'.format(defaults.DEF_WELLS_X),
                 '{:.0f}'.format(defaults.DEF_WELLS_Y),
                 '{:.0f}'.format(defaults.DEF_WELL_SEP_X_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_SEP_Y_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_ORIGIN_X_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_ORIGIN_Y_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_CORNER_X_UM),
                 '{:.0f}'.format(defaults.DEF_WELL_CORNER_Y_UM),
                 '{:.0f}'.format(defaults.DEF_NUMBER_OF_ACQ),
                 '{:.3f}'.format(defaults.DEF_DWELL_TIME_S)]
        self.mwInputField = dict() # to collect all input fields
        self.mwInputField['xWells'] = [QLineEdit(mwDef[0]), 1, 1, 1, 1]
        self.mwInputField['xWells'][0].setToolTip('Number of wells along x')
        self.mwInputField['yWells'] = [QLineEdit(mwDef[1]), 2, 1, 1, 1]
        self.mwInputField['yWells'][0].setToolTip('Number of wells along y')
        self.mwInputField['xWellSep'] = [QLineEdit(mwDef[2]), 1, 2, 1, 1]
        self.mwInputField['xWellSep'][0].setToolTip('Wells separation along x')
        self.mwInputField['yWellSep'] = [QLineEdit(mwDef[3]), 2, 2, 1, 1]
        self.mwInputField['yWellSep'][0].setToolTip('Wells separation along y')
        self.mwInputField['wellx1'] = [QLineEdit(mwDef[4]), 1, 3, 1, 1]
        self.mwInputField['wellx1'][0].setToolTip('x coordinate of bottom left well in scan')
        self.mwInputField['welly1'] = [QLineEdit(mwDef[5]), 2, 3, 1, 1]
        self.mwInputField['welly1'][0].setToolTip('y coordinate of bottom left well in scan')
        self.mwInputField['wellx2'] = [QLineEdit(mwDef[6]), 1, 4, 1, 1]
        self.mwInputField['wellx2'][0].setToolTip('x coordinate of top right well in scan')
        self.mwInputField['welly2'] = [QLineEdit(mwDef[7]), 2, 4, 1, 1]
        self.mwInputField['welly2'][0].setToolTip('y coordinate of top right well in scan')
        self.mwInputField['acquisitions'] = [QLineEdit(mwDef[8]), 4, 4, 1, 1]
        self.mwInputField['acquisitions'][0].setToolTip('Number of acquisitions')
        self.mwInputField['dwell'] = [QLineEdit(mwDef[9]), 4, 2, 1, 1]
        self.mwInputField['dwell'][0].setToolTip('Time to wait at each well')
        for _, k in self.mwInputField.items(): # Arrange in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.tabMultiwellGrid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Buttons
        self.btn = dict() # Contains buttons: [btn, row, col, rowSpan, colSpan]
        self.btn['Start'] = [QPushButton('Start'), 12, 0, 2, 3]
        self.btn['Start'][0].setToolTip('Start stage scan')
        self.btn['Stop'] = [QPushButton('Stop'), 12, 3, 2, 3]
        self.btn['Stop'][0].setToolTip('Stop stage scan')
        for x, k in self.btn.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            # k[0].setFocusPolicy(Qt.NoFocus)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            k[0].setStyleSheet(defaults.STYLE_ARMED)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Set stretch
        for row in range(0, 14):
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
        self.inputMethods['hw'][0].clicked.connect(lambda: self.joystick(selected='hardware'))
        self.inputMethods['sw'][0].clicked.connect(lambda: self.joystick(selected='software'))
        self.inputMethods['gp'][0].clicked.connect(lambda: self.joystick(selected='gamepad'))
        self.inputField['stepSet'][0].textChanged.connect(self.update_gamepad_step)
        '''
        Connecting to mainGUI to report stage positions.
        Po-Ting
        06/12/23
        '''
        self.current_stage_position.connect(self.mainGUI.update_coordinates_from_stageMotionWindow)
        self.current_stage_position.connect(self.mainGUI.snakeBrowser.update_coordinates_from_stageMotionWindow)
    def run(self):
        '''Run stage scan'''
        if self.tabs.currentIndex() not in [1]:
            print('Not implemented.')
            self.btn['Start'][0].setChecked(False)
        elif self.tabs.currentIndex() == 1:
            print('Running multiwell scan.')
            self.run_multiwell()

    def run_multiwell(self):
        '''Run multiwell holder scan'''
        if not self.disable_stage_inputs():
            self.btn['Start'][0].setChecked(False)
            return
        ### Lock GUI controls
        self.lock_controls()
        # self.statusbar.showMessage('Busy')
        ### Read, calculate and compile experiment parameters
        self.parameters.xWells = int(self.mwInputField['xWells'][0].text())
        self.parameters.yWells = int(self.mwInputField['yWells'][0].text())
        if (self.parameters.xWells == 1) and (self.parameters.yWells == 1):
            print('Cannot run pattern with only one well.')
            self.lock_controls(lock=False)
            self.btn['Start'][0].setChecked(False)
            return
        self.parameters.acquisitions = int(self.mwInputField['acquisitions'][0].text())
        self.parameters.stage = self.stage
        self.parameters.xWellSep = int(self.mwInputField['xWellSep'][0].text())
        self.parameters.yWellSep = int(self.mwInputField['yWellSep'][0].text())
        self.parameters.x1 = int(self.mwInputField['wellx1'][0].text())
        self.parameters.x2 = int(self.mwInputField['wellx2'][0].text())
        self.parameters.y1 = int(self.mwInputField['welly1'][0].text())
        ### Stage y axis is reversed. Angle formula must take that into account.
        y1Inv = -1 * int(self.mwInputField['welly1'][0].text())
        y2Inv = -1 * int(self.mwInputField['welly2'][0].text())
        self.parameters.y2 = int(self.mwInputField['welly2'][0].text())
        self.parameters.dwellTime = float(self.mwInputField['dwell'][0].text())
        x0 = self.parameters.x2 - self.parameters.x1
        y0 = y2Inv - y1Inv
        xMW = (self.parameters.xWells - 1) * self.parameters.xWellSep
        yMW = (self.parameters.yWells - 1) * self.parameters.yWellSep
        if (xMW == 0) or (yMW == 0): # Angle is between first and last well
            angle = np.arctan2(y0, x0)
        else: # Angle is that of the multiwell holder
            angle = np.arctan2(y0, x0) - np.arctan2(yMW, xMW)
        print('Multiwell holder angle : {:.2f}°.'.format(angle* 360 / (2 * np.pi)))
        self.parameters.xCornerRel = x0
        self.parameters.yCornerRel = y0
        self.parameters.xLength = xMW
        self.parameters.yLength = yMW
        self.parameters.angle = angle
        if self.reverse.isChecked():
            self.parameters.reverse = True
        else:
            self.parameters.reverse = False
        ### Parameter checks
        # if self.parameters.start == self.parameters.end: # Requested limits are equal
        #     print('Limits cannot be equal.')
        #     self.btn['Start'][0].setChecked(False)
        #     # GUIInstance.btn['Stop'][0].setChecked(False)
        #     self.btn['Sweep'][0].setChecked(False)
        #     return
        ### Run stage scan in separate thread
        self.threadMW = QThread()
        self.workerMW = stageMotion(self)
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
        # if self.mainGUI.stagePlotCanvas != []:
        #     ### If there is a full main UI with a stage plot, update that, too
        #     self.workerMW.currentPosition.connect(self.update_plot_external)
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

    def update_plot(self, x=0, y=0, pattern=[], acquisitions = [1, 1]):
        '''Update stage position plot'''
        self.plotCanvas.clear_plots()
        if not pattern == []:
            for p in range (0, len(pattern) - 1):
                p1 = pattern[p]
                p2 = pattern[p + 1]
                xLine = [p1[0], p2[0]]
                yLine = [p1[1], p2[1]]
                line = self.plotCanvas.axes.plot(xLine, yLine, 'k', zorder = 2)
                self.plotCanvas.plots.append(line[0]) # Index to get actual object
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
                arrow = self.plotCanvas.axes.arrow(xArrow, yArrow,
                                                   dxArrow, dyArrow,
                                                   lw = 1,
                                                   length_includes_head = True,
                                                   head_length = arrowLength,
                                                   head_width = arrowLength,
                                                   color = 'k')
                self.plotCanvas.plots.append(arrow)
        plot = self.plotCanvas.axes.scatter(x, y,
                                            c = defaults.STG_COLORS['marker'],
                                            marker = '+',
                                            zorder = 10)
        self.plotCanvas.plots.append(plot)
        if (np.abs(x) < 1000) or (np.abs(y) < 1000):
            textStr = '{:.0f}, {:.0f}'.format(x, y)
        else:
            textStr = '{:.0f},\n{:.0f}'.format(x, y)
        text = self.plotCanvas.axes.text(x + 2000, y + 0, textStr,
                        color = defaults.STG_COLORS['text'],
                        fontsize = 10)
        self.plotCanvas.plots.append(text)
        acqNum = acquisitions[0]
        acqCur = acquisitions[1]
        if acqNum > 1:
            acqTextStr = 'Acquisition: {:.0f} / {:.0f}'.format(acqCur, acqNum)
            acqText = self.plotCanvas.axes.text(-58000, -35000, acqTextStr,
                            color = defaults.STG_COLORS['acqText'],
                            fontsize = 10)
            self.plotCanvas.plots.append(acqText)
        titleString = 'Stage Position: x {:.0f} μm, y  {:.0f} μm'.format(x, y)
        self.plotCanvas.axes.set_title(titleString)
        self.plotCanvas.figure.canvas.draw()

    def update_plot_external(self, x=0, y=0, pattern=[], acquisitions = [1, 1]):
        '''Update plot in external UI'''
        self.mainGUI.stagePlotCanvas.clear_plots()
        plot = self.mainGUI.stagePlotCanvas.axes.scatter(x, y,
                                            c = defaults.STG_COLORS['marker'],
                                            marker = '+',
                                            zorder = 10)
        self.mainGUI.stagePlotCanvas.plots.append(plot)
        if (np.abs(x) < 1000) or (np.abs(y) < 1000):
            textStr = '{:.0f}, {:.0f}'.format(x, y)
        else:
            textStr = '{:.0f},\n{:.0f}'.format(x, y)
        text = self.mainGUI.stagePlotCanvas.axes.text(x + 2000, y + 0, textStr,
                        color = defaults.STG_COLORS['text'],
                        fontsize = 10,
                        zorder = 11)
        self.mainGUI.stagePlotCanvas.plots.append(text)
        titleString = 'Stage Position: x {:.0f} μm, y  {:.0f} μm'.format(x, y)
        self.mainGUI.stagePlotCanvas.axes.set_title(titleString)
        self.mainGUI.stagePlotCanvas.figure.canvas.draw()

    def update_readings(self):
        '''Update stage parameter readings.'''
        (x_um, y_um) = self.stage.get_position()
        # print('Stage position: {:.0f} μm, {:.0f} μm'.format(x_um, y_um))
        v_um_s = self.stage.get_speed()
        a_um_s2 = self.stage.get_acc()
        self.apply_readings(x_um, y_um, v_um_s, a_um_s2)

    def apply_readings(self, x_um, y_um, v_um_s, a_um_s2):
        """Apply a snapshot on the GUI thread, including both Qt-backed plots."""
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
        if self.mainGUI.stagePlotCanvas != []:
            ### If there is a full main UI with a stage plot, update that, too
            self.update_plot_external(x_um, y_um)
            #Emit signals to the mainWindow
            stage_position = (x_um, y_um)
            self.current_stage_position.emit((stage_position[0], stage_position[1]))



class stageStartupDialog(QDialog):
    '''Show a dialog when stage is starting up.'''

    def __init__(self, COM_PORT = defaults.STAGE_DEF_COM_PORT):
        super().__init__()
        self.COMPort = COM_PORT
        self.make_dialog()

    def center_window(self):
        '''Center main application window on screen'''
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

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
        # self.setWindowModality(Qt.ApplicationModal) # Disable rest of UI
        ### Dialog text
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        initString = 'Initializing stage (COM port {:.0f}). Please wait.'.format(self.COMPort)
        self.textBox = QLabel(initString)
        self.textBox.setFont(self.font)
        self.textBox.setStyleSheet(defaults.STYLE_LABEL_ALT)
        self.layout.addWidget(self.textBox)
        self.center_window()