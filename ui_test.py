#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QAction, qApp, QApplication, QMainWindow)

class Window(QMainWindow):
    '''A simple window'''

    def __init__(self):
        super().__init__()
        self.make_gui()

    def make_gui(self):
        '''Create main GUI window'''
        self.menuBar()
        self.statusBar()
        exitAction = QAction(QIcon(None), 'Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(qApp.quit)
        fileMenu = self.menuBar().addMenu('Actions')
        fileMenu.addAction(exitAction)
        self.show()


if __name__ == '__main__':
    APP = QApplication([])
    GUI1 = Window()
    sys.exit(APP.exec_())
