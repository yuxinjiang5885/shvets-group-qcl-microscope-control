'''
auxiliary
Giovanni Sartorello (srtgnn@gmail.com)
Classes used by the QCL UI to store parameters data
Python 3.10.5 on Windows 10
Created 2022-Aug-05
'''

import numpy as np
import csv
import experiment.defaults as defaults
from scipy.io import savemat

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
                + ------ Vtemp VOLTAGES        (list of lists, one per wl/wn)
                + ------ W WAVELENGTHS/NUMBERS (list)
                + ------ X POSITIONS           (vector)
                + ------ Xcont POSITIONS       (list of lists, one per wl/wn)
                + ------ Y POSITIONS           (vector)
                + ------ Ycont POSITIONS       (list of lists, one per wl/wn)
        '''
        self.indices = [] # YX indices for temporary voltage list
        self.V = []       # Voltage averages matrix: X columns, Y rows
        self.Vtemp = []   # Voltage non-averaged list, used during acquisition
        self.W = []       # Wavelengths or wavenumbers
        self.X = []       # X positions vector
        self.Xcont = []   # X positions matrix for continuous scanning
        self.Xtemp = []   # X positions for continuous scanning, unformatted
        self.Y = []       # Y positions vector
        self.Ycont = []   # Y positions matrix for continuous scanning
        self.Ytemp = []   # Y positions for continuous scanning, unformatted

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
        for _, _ in enumerate(self.W[index]):
            self.Vtemp[-1].append([])

    def add_XYcont(self, index = -1):
        '''Make lists to hold x/y positions for continuous scanning.
           One per X/Y per wl/wn.
           Use immediately after "add_W", "add_X" and "add_Y" to match index.'''
        self.Xcont.append([])
        self.Ycont.append([])
        for _, _ in enumerate(self.W[index]):
            self.Xcont[-1].append([])
            self.Ycont[-1].append([])

    def add_XYtemp(self, index = -1):
        '''Make lists to hold x/y positions during continuous scanning.
           One per X/Y per wl/wn.
           Use immediately after "add_W", "add_X" and "add_Y" to match index.'''
        self.Xtemp.append([])
        self.Ytemp.append([])
        for _, _ in enumerate(self.W[index]):
            self.Xtemp[-1].append([])
            self.Ytemp[-1].append([])


class scanningImagingParameters():
    '''Holds experiment parameters for scanning imaging.'''

    def __init__(self):
        self.data = scanningImagingData() # Holds acquired data
        self.fastPatterns = [] # Fast scanning imaging patters, placeholder value
        self.laser = [] # Laser instance, laceholder value
        self.latestDir = 0 # Latest experiment directory, placeholder value
        self.qcl = [] # QCL modules to be used, placeholder value
        self.patterns = [] # Scanning imaging patters, placeholder value
        self.patternIndices = [] # Indices of pattern positions, placeholder value
        self.ranges = [] # Wavelength/wavenumber ranges, placeholder value
        self.sampleNumbers = [] # Sample numbers, placeholder value
        self.sampleRates = [] # Sample rates, placeholder value
        self.scanDir = [] # List of scan direction (each 'x' or 'y')
        self.scanMode = 'step_one'
        self.speeds = [] # Sweeping speeds, placeholder value
        self.stage = [] # Stage instance, placeholder value
        self.units = 'um' # By default, wavelengths in micrometers
        self.wlwnList = [] # List of wavelengths (um) or wavenumbers (cm^-1)
        self.xParameters = [] # Axis x scan parameters
        self.yParameters = [] # Axis y scan parameters
        self.pi_scanner = [] # Objective scanner instance, placeholder value
        self.pi_scanner_widget = [] # Objective scanner widget instance, placeholder value

'''
class of snakeScanParameters and snakeScanData
05/12/23
Po-Ting Shen
'''
class snakeScanParameters(scanningImagingParameters):
    '''Holds experiment parameters for snake scans.'''
    def __init__(self):
        super().__init__()
        self.data = snakeScanData()
        self.maxStageSpeed = defaults.HLD117_REC_SPEED
        self.scanMode = 'snake_scan'


class snakeScanData(scanningImagingData):
    '''Holds only the parameters to recover spatial information.'''
    def __init__(self):
        super().__init__()
        self.snakeScans = []
        self.dataCh1 = []
        self.dataCh2 = []
        self.sampleNumber = defaults.DEF_SAMPLES_SNAKESCAN
        self.savedStagePosition = (0, 0)
        self.xPixels = 0
        self.yPixels = 0
        self.xPixelRes = defaults.SNAKE_SCAN_RES_X_UM
        self.yPixelRes = defaults.SNAKE_SCAN_RES_Y_UM
        self.trigIndent = defaults.SNAKE_TRIG_INDENT
        self.returnDrift = defaults.HLD117_X_RETURN_DRIFT_UM

    def add_nested(self, index = -1):
        '''
        Setting up the nested lists of dataCh1, dataCh2, and SnakeScans
        Follow the design pattern of Vtemp.
        Each pattern
                    \
                    Each channel
                                \
                                Each wavelength (wavenumber)
        '''
        self.dataCh1.append([])
        self.dataCh2.append([])
        self.snakeScans.append([])
        self.X.append([])
        self.Y.append([])
        for _, _ in enumerate(self.W[index]):
            self.dataCh1[-1].append([])
            self.dataCh2[-1].append([])
            self.snakeScans[-1].append([])
            self.X[-1].append([])
            self.Y[-1].append([])

    def finishSnakeScan(self, pattern_idx, wlwn_idx,
                         wlUnits = 'um',
                         filepath = defaults.DEF_TEST_FOLDER):
        '''
        Finish one snake scan per wlwn.
        Prerequisite: After a snake scan is complete.
        <dataCh1>: list of measured numpy array of channel 1
        <dataCh2>: list of measured numpy array of channel 2
        <sampleNumber>: How many readings per trigger
        '''
        idx = pattern_idx
        jdx = wlwn_idx
        voltageLines = []

        for counter, (ch1, ch2) in enumerate(zip(self.dataCh1[idx][jdx], self.dataCh2[idx][jdx])):
            #print(counter)
            _ = np.sqrt(np.add(np.square(ch1), np.square(ch2)))
            tmp_list = _.tolist()
            #print(len(tmp_list))
            if counter%2 == 1:
                tmp_list.reverse()
                #print('Backward scan line data reversed.')

            voltageLine = []
            for i in range(len(tmp_list)):
                if i == 0:
                    continue
                if i%self.sampleNumber == self.sampleNumber-1:
                    avg = sum(tmp_list[(i-self.sampleNumber+1):(i+1)])/self.sampleNumber
                    voltageLine.append(avg)
            voltageLines.append(voltageLine)
        print('How many lines are there in a snake scan: ' + str(len(voltageLines)))
        print('What is the length of each line: ' + str(len(voltageLines[0])))

        #Append voltageLines to snakeScans[idx][jdx]
        self.snakeScans[idx][jdx]= np.array(voltageLines)
        self.writeSnakeScan(idx,jdx, wlUnits, filepath)

    def writeSnakeScan(self, pattern_idx, wlwn_idx,
                    wlUnits,
                    filepath):
        '''
        Write one snake scan to csv.
        Prerequisite: use within finishSnakeScan
        Local variables:
        <filepath>: where to save the files
        <lineScan>: a list of lists. Each list is a scan line of voltageLines.
        '''
        idx = pattern_idx
        jdx = wlwn_idx
        filename = '\\lineScan_' + str(self.W[idx][jdx]).replace(".", "_") + wlUnits +'.csv'
        filepath = filepath + filename

        lineScan = self.snakeScans[idx][jdx]

        with open(filepath, 'w', newline="") as f:
            # using csv.writer method from CSV package
            write = csv.writer(f)
            for line in lineScan:
                #Write item to outcsv
                write.writerow(line)

    def guiFormat(self):
        '''
        Format snakescan data to its parent class's (scanningImagingData's) format for GUI to work
        Prerequisite: After all the patterns are done
        '''
        self.V = self.snakeScans
        self.Xcont = self.X
        self.Ycont = self.Y

    def saveMat(self, wlUnits: str):
        '''
        Stack each wavelength/wavenumber of a pattern to one 3d numpy datacube.
        Save those datacubes to one .mat file.
        '''
        hypercube_dict = {}

        hypercube_dict['wlUnits'] = wlUnits

        for idx, pattern in enumerate(self.snakeScans):
            temp_list = []

            for jdx, wlwn in enumerate(self.W[idx]):
                temp_list.append(self.snakeScans[idx][jdx])

            hypercube = np.stack(temp_list, axis = 2)
            wn = np.array(self.W[idx])

            key = f'pattern{idx}'
            hypercube_dict[key] = hypercube
            key = f'wn{idx}'
            hypercube_dict[key] = wn

        # Save the dictionary to a .mat file
        savemat('hcubes.mat', hypercube_dict)






class repeatSnakeScanParameters(snakeScanParameters):
    '''Holds experiment parameters for repeated snake scans.'''
    def __init__(self):
        super().__init__()
        self.data = snakeScanData()
        self.maxStageSpeed = defaults.HLD117_REC_SPEED
        self.scanMode = 'repeat_snake_scan'
        self.timeStamps = {}








