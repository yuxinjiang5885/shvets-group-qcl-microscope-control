'''
scan_windows
Giovanni Sartorello (srtgnn@gmail.com)
UI elements for imaging scanning
Python 3.10.5 on Windows 10
Created 2022-Jun-24
'''

import experiment.defaults as defaults
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QComboBox,
                             QGridLayout,
                             QLabel,
                             QLineEdit,
                             QPushButton,
                             QTabWidget,
                             QTextEdit,
                             QSizePolicy,
                             QWidget)

class scanBrowser(QTabWidget):
    '''Multi-tab scan browser'''

    def __init__(self, mainGUI):
        super().__init__()
        self.mainGUI = mainGUI
        self.setDocumentMode(True)
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_scan_tab)
        self.tabBarDoubleClicked.connect(self.add_scan_tab)
        self.tabTitleSeparator = ' '
        self.scans = []
        # self.toolbar = QToolBar('Scan tabs')
        # self.addToolBar(self.toolbar)
        # self.newTabAction = QAction('New Scan')
        # self.newTabAction.setShortcut('Ctrl+T')
        # self.newTabAction.triggered.connect(self.add_scan_tab())
        # self.toolbar.addAction(self.newTabAction)
        self.add_scan_tab()

    def add_scan_tab(self):
        '''Add a new tab with scan parameters'''
        scan = scanUI(self.mainGUI)
        scans = len(self.scans)
        scan.scanID = scans
        scanLabel = 'Scan{}{:.0f}'.format(self.tabTitleSeparator, scan.scanID)
        self.scans.append(scan)
        ti = self.addTab(scan, scanLabel)
        self.setCurrentIndex(ti)

    # def add_scan_tab_double_click(self):
    #     '''Add tab by double-clicking the tabs bar'''
    #     self.add_scan_tab()

    def close_scan_tab(self, ti):
        '''Close tab'''
        if self.count() < 2: ### If there are fewer than 1 tabs
            print('Cannot close the last scan tab.')
            return
        for si, s in enumerate(self.scans):
            if s == []:
                continue
            currentTabTitle = self.tabText(ti)
            currentTabTitleParts = currentTabTitle.split(self.tabTitleSeparator)
            currentScanID = currentTabTitleParts[-1]
            if int(currentScanID) == int(s.scanID):
                self.scans[si] = []
                # print(self.scans)
        self.removeTab(ti)
        self.scans = [s for s in self.scans if s]
        self.rename_scans()

    def rename_scans(self):
        '''Rename all scans after one has been closed'''
        for si, s in enumerate(self.scans):
            s.scanID = si
            scanLabel = 'Scan{}{:.0f}'.format(self.tabTitleSeparator, si)
            self.setTabText(si, scanLabel)



class scanUI(QWidget):
    '''Widget with scan controls'''

    def __init__(self, mainGUI):
        super().__init__()
        self.mainGUI = mainGUI
        self.grid = QGridLayout()
        self.setLayout(self.grid)
        self.scanID = -1
        self.sizeOrSteps = 'steps' # Scan defined by size or number of steps
        self.make_ui()

    def make_ui(self):
        '''Create UI for scan parameters'''
        font = QFont()
        font.setFamily(defaults.FONT_FAMILY)
        font.setPointSize(defaults.FONT_SIZE_MEDIUM)
        ### Labels
        self.labels = dict() # [label, row, col, rowSpan, colSpan]
        self.labels['Origin'] = [QLabel('Origin'), 0, 1, 1, 1]
        self.labels['Step'] = [QLabel('Step (μm)'), 0, 2, 1, 1]
        self.labels['x'] = [QLabel('x'), 1, 0, 1, 1]
        self.labels['y'] = [QLabel('y'), 2, 0, 1, 1]
        self.labels['RasterDir'] = [QLabel('Raster direction'), 3, 0, 1, 1]
        self.labels['SamplingRate'] = [QLabel('Sampl. Rate (Hz)'),
                                            5, 1, 1, 1]
        self.labels['SamplesPerWl'] = [QLabel('Sampl. per Wl.'),
                                            5, 2, 1, 1]
        self.labels['Speed'] = [QLabel('Speed (μm/s)'), 5, 3, 1, 1]
        for _, k in self.labels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Buttons
        self.buttons = dict() # [button, row, col, rowSpan, colSpan]
        self.buttons['ScanSizeSteps'] = [QPushButton('Scan steps'), 0, 3, 1, 1]
        # 'Scan size\n(μm)'
        self.buttons['ScanSizeSteps'][0].setToolTip('Toggle between scan size and number of steps')
        self.buttons['WlWn'] = [QPushButton('Wls.\n(μm)'), 7, 0, 2, 1]
        self.buttons['WlWn'][0].setToolTip('Toggle between wavelengths and wavenumbers')
        for x, k in self.buttons.items(): # Arrange buttons in grid
            k[0].setCheckable(True)
            k[0].setFont(font)
            k[0].setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            k[0].setStyleSheet(defaults.STYLE_BUTTON_UNIT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Input fields
        self.inputFields = dict()
        self.inputFields['xOrig'] = [QLineEdit('{}'.format(
                                    defaults.IMAG_SCAN_ORIGIN_X_UM )), 1, 1, 1, 1]
        self.inputFields['xOrig'][0].setToolTip('Scan x origin')
        self.inputFields['yOrig'] = [QLineEdit('{}'.format(
                                    defaults.IMAG_SCAN_ORIGIN_Y_UM )), 2, 1, 1, 1]
        self.inputFields['yOrig'][0].setToolTip('Scan y origin')
        self.inputFields['xStep'] = [QLineEdit('{}'.format(
                                    defaults.IMAG_SCAN_STEP_X_UM )), 1, 2, 1, 1]
        self.inputFields['xStep'][0].setToolTip('Scan x step')
        self.inputFields['yStep'] = [QLineEdit('{}'.format(
                                    defaults.IMAG_SCAN_STEP_Y_UM )), 2, 2, 1, 1]
        self.inputFields['yStep'][0].setToolTip('Scan y step')
        self.inputFields['xSizeSteps'] = [QLineEdit('{}'.format(
                                    defaults.IMAG_SCAN_SIZE_X_UM )), 1, 3, 1, 1]
        self.inputFields['xSizeSteps'][0].setToolTip('Scan x size or steps')
        self.inputFields['ySizeSteps'] = [QLineEdit('{}'.format(
                                    defaults.IMAG_SCAN_SIZE_X_UM )), 2, 3, 1, 1]
        self.inputFields['ySizeSteps'][0].setToolTip('Scan x size or steps')
        self.inputFields['samplingRate'] = [QLineEdit('{}'.format(
                                    defaults.DEF_SAMPLERATE)), 6, 1, 1, 1]
        self.inputFields['samplingRate'][0].setToolTip(
                                    'Acquisition card sampling rate')
        self.inputFields['samplesPerWl'] = [QLineEdit('{}'.format(
                                    defaults.DEF_SAMPLES_IMAGING)), 6, 2, 1, 1]
        self.inputFields['samplesPerWl'][0].setToolTip(
                                    'Voltage points per wavelength/wavenumber step')
        self.inputFields['speed'] = [QLineEdit('{}'.format(
                                    defaults.MAX_SWEEP_SPEED_UM)), 6, 3, 1, 1]
        self.inputFields['speed'][0].setToolTip('Sweep speed')
        for _, k in self.inputFields.items(): # Arrange labels in grid
            k[0].returnPressed.connect(lambda: self.mainGUI.update_scanning_imaging_plot_patterns())
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Drop-down raster pattern direction selector
        self.scanDropdowns = dict()
        self.scanDropdowns['RasterDir'] = [QComboBox(), 4, 0, 1, 2]
        self.scanDropdowns['RasterDir'][0].addItem('Longest side', 0)
        self.scanDropdowns['RasterDir'][0].addItem('Along x', 1)
        self.scanDropdowns['RasterDir'][0].addItem('Along y', 2)
        for x, k in self.scanDropdowns.items(): # Arrange buttons in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_COMBOBOX)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Text field for list of wavelengths or wavenumbers
        self.wlwnList = QTextEdit(defaults.IMAG_SCAN_WL_LIST)
        self.wlwnList.setFont(font)
        self.wlwnList.setStyleSheet(defaults.STYLE_TEXT)
        self.wlwnList.setToolTip('List of wavelengths (format: 1000, 1100:1200, ...)')
        self.grid.addWidget(self.wlwnList, 7, 1, 2, 3)
        ### Connect buttons to actions
        self.buttons['ScanSizeSteps'][0].clicked.connect(lambda: self.switch_scan_size_steps())

    def switch_scan_size_steps(self):
        '''Switch between scan size and number of steps'''
        for s in self.mainGUI.scanBrowser.scans:
            if s.sizeOrSteps in ['Steps', 'steps']:
                s.sizeOrSteps = 'size'
                s.buttons['ScanSizeSteps'][0].setText('Scan size (μm)')
                xStep = int(s.inputFields['xStep'][0].text())
                yStep = int(s.inputFields['yStep'][0].text())
                xSteps = int(s.inputFields['xSizeSteps'][0].text())
                ySteps = int(s.inputFields['ySizeSteps'][0].text())
                xSize = xStep * xSteps
                ySize = yStep * ySteps
                s.inputFields['xSizeSteps'][0].setText('{:.0f}'.format(xSize))
                s.inputFields['ySizeSteps'][0].setText('{:.0f}'.format(ySize))
            else:
                s.sizeOrSteps = 'steps'
                s.buttons['ScanSizeSteps'][0].setText('Scan steps')
                xStep = int(s.inputFields['xStep'][0].text())
                yStep = int(s.inputFields['yStep'][0].text())
                xSize = int(s.inputFields['xSizeSteps'][0].text())
                ySize = int(s.inputFields['ySizeSteps'][0].text())
                xSteps = int(xSize / xStep)
                ySteps = int(ySize / yStep)
                s.inputFields['xSizeSteps'][0].setText('{:.0f}'.format(xSteps))
                s.inputFields['ySizeSteps'][0].setText('{:.0f}'.format(ySteps))
