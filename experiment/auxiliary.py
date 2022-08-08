'''
auxiliary
Giovanni Sartorello (srtgnn@gmail.com)
Classes used by the QCL UI to store parameters data
Python 3.10.5 on Windows 10
Created 2022-Aug-05
'''

import numpy as np
import experiment.defaults as defaults

class experimentParameters():
    '''Holds experiment parameters'''

    def __init__(self):
        self.acquisitions = 0 # Number of acquisitions
        self.acq_time_interval_s = 300 # Interval between acquisitions, s
        self.end = 100 # Placeholder value, no unit
        self.laser = [] # Placeholder value
        self.latestDir = 0 # Latest experiment directory, placeholder value
        self.notes = [] # Placeholder value
        self.qcl = [] # QCL modules to be used, placeholder value
        self.ranges = [] # Placeholder value
        self.refDir = '' # Reference experiment directory
        self.reference = np.zeros((1, 2)) # Placeholder value
        self.sampleNumber = defaults.DEF_SAMPLES
        self.sampleRate = defaults.DEF_SAMPLERATE
        self.speed = 1 # Placeholder value, no unit
        self.start = 0 # Placeholder value, no unit
        self.step = 1 # Placeholder value, no unit
        self.sweeping = True # By default, use the sweep routine
        self.sweepLimits = [] # Placeholder value
        self.units = 'um' # By default, wavelengths in micrometers
        self.useRef = False # By default, do not use reference


class hyperspectralSlice():
    '''Holds a wavelength slice of scanning imaging data'''

    def __init__(self):
        self.wavelength = 0
        self.X = []
        self.Y = []
        self.Z = []


class scanningImagingData():
    '''Holds data from scanning imaging experiments.
       Organized by pattern, each pattern organized by wavelength/wavenumber.'''

    def __init__(self):
        '''Prepare variables to hold data.
           All these are lists of vectors, matrices or lists.
           Data structure:

           XY SCANNING PATTERN (one element of each of the list variables)
                + ------ indices               (list)
                + ------ V VOLTAGES            (list of matrices, one per wl/wn)
                + ------ V_temp VOLTAGES       (list of lists, one per wl/wn)
                + ------ W WAVELENGTHS/NUMBERS (list)
                + ------ X POSITIONS           (vector)
                + ------ Y POSITIONS           (vector)
        '''
        self.indices = [] # YX indices for temporary voltage list
        self.V = []       # Voltage averages matrix: X columns, Y rows
        self.Vtemp = []  # Voltage non-averaged list, used during acquisition
        self.W = []       # Wavelengths or wavenumbers
        self.X = []       # X positions vector
        self.Y = []       # Y positions vector

    def add_V(self, index = -1):
        '''Make zero matrices to hold voltages, one per wl/wn.
           X are columns, Y rows.
           Use immediately after "add_W", "add_X" and "add_Y" to match index.'''
        self.V.append([])
        for wi, _ in enumerate(self.W[index]):
            self.V[-1].append([])
            self.V[-1][wi] = np.zeros((self.X[index].size, self.Y[index].size))

    def add_Vtemp(self, index = -1):
        '''Make lists to hold voltages during acquisition, one per wl/wn.
           Use immediately after "add_W", "add_X" and "add_Y" to match index.'''
        self.Vtemp.append([])
        for wi, _ in enumerate(self.W[index]):
            self.Vtemp[-1].append([])
            # self.Vtemp[-1][wi].append([])


class scanningImagingParameters():
    '''Holds experiment parameters for scanning imaging.'''

    def __init__(self):
        # self.acquisitions = 0 # Number of acquisitions
        # self.acq_time_interval_s = 300 # Interval between acquisitions, s
        self.data = scanningImagingData() # Holds acquired data
        # self.end = 100 # Placeholder value, no unit
        self.laser = [] # Laser instance, laceholder value
        self.latestDir = 0 # Latest experiment directory, placeholder value
        # self.notes = [] # Placeholder value\
        self.qcl = [] # QCL modules to be used, placeholder value
        self.patterns = [] # Scanning imaging patters, placeholder value
        self.patternIndices = [] # Indices of pattern positions, placeholder value
        self.ranges = [] # Wavelength/wavenumber ranges, placeholder value
        self.refDir = '' # Reference experiment directory
        # self.reference = np.zeros((1, 2)) # Placeholder value
        self.sampleNumbers = [] # Sample numbers, placeholder value
        self.sampleRates = [] # Sample rates, placeholder value
        self.scanMode = 'step_one'
        self.speeds = [] # Sweeping speeds, placeholder value
        self.stage = [] # Stage instance, laceholder value
        # self.start = 0 # Placeholder value, no unit
        # self.step = 1 # Placeholder value, no unit
        # self.sweeping = True # By default, use the sweep routine
        # self.sweepLimits = [] # Placeholder value
        self.units = 'um' # By default, wavelengths in micrometers
        # self.useRef = False # By default, do not use reference
        self.wlwnList = [] # List of wavelengths (um) or wavenumbers (cm^-1)