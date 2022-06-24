'''
scan_windows
Giovanni Sartorello (srtgnn@gmail.com)
UI elements for imaging scanning
Python 3.10.5 on Windows 10
Created 2022-Jun-24
'''

import experiment.defaults as defaults
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QGridLayout,
                             QLabel,
                             QLineEdit,
                             QPushButton,
                             QTabWidget,
                             QTextEdit,
                             QSizePolicy,
                             QWidget)

class scan_browser(QTabWidget):
    '''Multi-tab scan browser'''

    def __init__(self):
        super().__init__()
        self.setDocumentMode(True)
        self.setTabsClosable(True)
        self.scans = []
        # self.addTab(self.scanUI, 'Scan 1')
        self.new_scan()

    def new_scan(self, label = 'Scan'):
        '''Add a new tab with scan parameters'''
        scan = scan_ui()
        self.scans.append(scan)
        i = self.addTab(scan, label)
        self.setCurrentIndex(i)

class scan_ui(QWidget):
    '''Widget with scan controls'''

    def __init__(self):
        super().__init__()
        self.grid = QGridLayout()
        self.setLayout(self.grid)
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
        for _, k in self.labels.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_LABEL_EMPH)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Buttons
        self.buttons = dict() # [button, row, col, rowSpan, colSpan]
        self.buttons['ScanSizeN'] = [QPushButton('Scan size\n(μm)'), 0, 3, 1, 1]
        self.buttons['ScanSizeN'][0].setToolTip('Toggle between scan size and number of points')
        self.buttons['WlWn'] = [QPushButton('Wls.\n(μm)'), 3, 0, 1, 1]
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
        self.inputFields['xSizeN'] = [QLineEdit('{}'.format(
                                    defaults.IMAG_SCAN_SIZE_X_UM )), 1, 3, 1, 1]
        self.inputFields['xSizeN'][0].setToolTip('Scan x size')
        self.inputFields['ySizeN'] = [QLineEdit('{}'.format(
                                    defaults.IMAG_SCAN_SIZE_X_UM )), 2, 3, 1, 1]
        self.inputFields['ySizeN'][0].setToolTip('Scan x size')
        for _, k in self.inputFields.items(): # Arrange labels in grid
            k[0].setFont(font)
            k[0].setStyleSheet(defaults.STYLE_INPUT)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
        ### Text field for list of wavelengths or wavenumbers
        self.wlwnList = QTextEdit('')
        self.wlwnList.setFont(font)
        self.wlwnList.setStyleSheet(defaults.STYLE_TEXT)
        self.wlwnList.setToolTip('List of wavelengths (format: 1000, 1100:1200, ...)')
        self.grid.addWidget(self.wlwnList, 3, 1, 4, 4)
