'''
software_joystick
Giovanni Sartorello (srtgnn@gmail.com)
Software joystick test
Adapted from https://stackoverflow.com/a/55899694
Created 2022-Apr-06
'''

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject, pyqtSignal, QPointF, QLineF, QRectF
from PyQt5.QtGui import QIntValidator, QIcon, QFont, QPainter
from PyQt5.QtWidgets import QWidget


class Joystick(QWidget):
    joystickInput = pyqtSignal(list)

    def __init__(self, parent=None):
        super(Joystick, self).__init__(parent)
        self.setMinimumSize(100, 100)
        self.movingOffset = QPointF(0, 0)
        self.grabCenter = False
        self.__maxDistance = 50

    def paintEvent(self, event):
        painter = QPainter(self)
        bounds = QRectF(-self.__maxDistance, -self.__maxDistance, self.__maxDistance * 2, self.__maxDistance * 2).translated(self._center())
        painter.drawEllipse(bounds)
        painter.setBrush(Qt.black)
        painter.drawEllipse(self._centerEllipse())

    def _centerEllipse(self):
        if self.grabCenter:
            return QRectF(-20, -20, 40, 40).translated(self.movingOffset)
        return QRectF(-20, -20, 40, 40).translated(self._center())

    def _center(self):
        return QPointF(self.width()/2, self.height()/2)

    def _boundJoystick(self, point):
        limitLine = QLineF(self._center(), point)
        if (limitLine.length() > self.__maxDistance):
            limitLine.setLength(self.__maxDistance)
        return limitLine.p2()

    def joystickDirection(self):
        if not self.grabCenter:
            return 0
        normVector = QLineF(self._center(), self.movingOffset)
        currentDistance = normVector.length()
        angle = normVector.angle()
        distance = min(currentDistance / self.__maxDistance, 1.0)
        return(angle, distance)

    def mousePressEvent(self, ev):
        self.grabCenter = self._centerEllipse().contains(ev.pos())
        return super().mousePressEvent(ev)

    def mouseReleaseEvent(self, event):
        self.grabCenter = False
        self.movingOffset = QPointF(0, 0)
        # print(self.joystickDirection())
        self.joystickInput.emit([self.joystickDirection()])
        self.update()

    def mouseMoveEvent(self, event):
        if self.grabCenter:
            # print("Moving")
            self.movingOffset = self._boundJoystick(event.pos())
            self.update()
        # print(self.joystickDirection())
        self.joystickInput.emit([self.joystickDirection()])