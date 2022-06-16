'''
plot_widgets
Giovanni Sartorello (srtgnn@gmail.com)
Plot widgets for MIRcat spectral scan UI
Version 1
Python 3.8.3 on Windows 10
Created 2020-Oct-20
'''

import matplotlib as mpl
import matplotlib.pyplot as plt
# from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigCanvas
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigCanvas

class mplCanvas(FigCanvas):
    '''Matplotlib canvas embeddable in QT5.'''

    def __init__(self, parent=None, width=4, height=4):
        self.figure = plt.figure(figsize=(width, height))
        super().__init__(self.figure)
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.images = [] # Stores images plotted with "imshow"
        self.plots = [] # Stores lines plotted with "plot"

    def clear_plots(self):
        for pl in self.plots:
            pl.remove()
        self.plots = [] # Re-initialize list

    def plot_line(self, X, Y, color=[0, 0, 0]):
        '''Call plot_surface to plot data'''
        plot = self.axes.plot(X, Y, color=color)
        self.plots.append(plot[0])
        self.figure.canvas.draw()

    def recolor(self, axesColor = [0, 0, 0], backgroundColor = [1, 1, 1],
                      plotColor = [0.5, 0.5, 0.5]):
        '''Recolor axes, labels, ticks and background'''
        self.axes.spines['bottom'].set_color(axesColor)
        self.axes.spines['left'].set_color(axesColor)
        self.axes.spines['right'].set_color(axesColor)
        self.axes.spines['top'].set_color(axesColor)
        self.axes.xaxis.label.set_color(axesColor)
        self.axes.yaxis.label.set_color(axesColor)
        self.axes.tick_params(axis='both', colors=axesColor)
        title = self.axes.get_title()
        self.axes.set_title(title, color = axesColor)
        self.axes.set_facecolor(backgroundColor)
        self.figure.patch.set_facecolor(backgroundColor)
        if len(self.plots) > 0:
            self.plots[0].set_color(plotColor)
        self.draw()
