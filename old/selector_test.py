import sys
from PyQt5.QtWidgets import (QApplication,
                             QGridLayout,
                             QMainWindow,
                             QPushButton,
                             QWidget,
                             QSizePolicy)

class testWindow(QMainWindow):
    '''Test window with four buttons'''

    def __init__(self):
        super().__init__()
        self.make_gui()

    def make_gui(self):
        '''Set layout'''
        self.setGeometry(0, 0, 300, 400)
        self.container = QWidget()
        self.setCentralWidget(self.container)
        self.grid = QGridLayout()
        self.container.setLayout(self.grid)
        '''Make four buttons'''
        self.buttons = dict() # [QPushButton, row, column, rowSpan, colSpan]
        for x in range(1, 5):
            btnName = 'button{:.0f}'.format(x)
            btnText = 'Button {:.0f}'.format(x)
            self.buttons[btnName] = [QPushButton(btnText), x - 1, 0, 1, 1]
        '''Arrange buttons in grid'''
        for x, (_, k) in enumerate(self.buttons.items()):
            k[0].setCheckable(False)
            k[0].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.grid.addWidget(k[0], k[1], k[2], k[3], k[4])
            k[0].clicked.connect(lambda: self.button_action(x+1))
        '''Alternative connection method'''
        # self.buttons['button1'][0].clicked.connect(lambda: self.button_action(1))
        # self.buttons['button2'][0].clicked.connect(lambda: self.button_action(2))
        # self.buttons['button3'][0].clicked.connect(lambda: self.button_action(3))
        # self.buttons['button4'][0].clicked.connect(lambda: self.button_action(4))
        self.show()

    def button_action(self, number):
        print('Button {:.0f}'.format(number))

if __name__ == '__main__':
    APP = QApplication(sys.argv)
    GUI1 = testWindow()
    sys.exit(APP.exec_())