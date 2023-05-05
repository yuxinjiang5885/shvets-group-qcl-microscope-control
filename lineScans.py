'''
A "lineScans" object consists a full frame of linescans.
'''
from typing import _SpecialForm


class lineScans:


    def __init__(self, directions, numbers, units, rawVoltages, wavelengths, Xs, Ys):

        '''
        Constructor
        '''
        self.directions = directions   # Scan directions: list
        self.numbers = numbers   # Scan numbers: list
        self.units = units   # Scan units: list
        self.rawVoltages = rawVoltages   # rawVoltages: list of lists. Each list within is a linescan of raw voltages
        self.wavelengths = wavelengths   # Wavelengths: list of lists of scalars
        self.Xs = Xs   # X positions: list of arrays. Each array carries the X-coordinates of each list of rawVoltages.
        self.Ys = Ys   # Y positions: list of arrays. Each array carries the Y-coordinates of each list of rawVoltages.
        '''
        Constants
        '''
        self.INTERP_MULTIPLIER = 10 # Multiply scan line lengths by this factor
        self.plotView  = 'above'   # Plot view: looking stage from above or below
        self.interpolate = True    # Interpolate between voltage points


    def readFiles(self, fileLoc):
        '''
        Construct a "lineScans" from a given String folder location.
        '''
        os = __import__('os')
        np = __import__('numpy')
        fileList = os.listdir(fileLoc)

        for file in fileList: # List files in data folder
            if file.endswith('.txt'):
                filePath = os.path.join(fileLoc, file)
                print('Processing "{}".'.format(file))
                fileParts = file.split('_')
                if 'scan' not in fileParts[0]: # If not a data file
                    print('Not a valid data file.')
                    continue
                scanID = int(fileParts[0][4:])
                if scanID not in self.numbers:
                    self.directions.append([])
                    self.numbers.append(scanID)
                    self.units.append([])
                    self.rawVoltages.append([])
                    self.wavelengths.append([])
                    self.Xs.append([])
                    self.Ys.append([])
                    scanIndex = -1
                else:
                    scanIndex = self.numbers.index(scanID)
                if 'w' in fileParts[1]:
                    w = float(fileParts[1][3:8])
                    if w not in self.wavelengths[scanIndex]:
                        self.wavelengths[scanIndex].append(w)
                        if 'um' in file:
                            u = 'um'
                        else:
                            u = 'cm⁻¹'
                        self.units[scanIndex].append(u)
                    ### Read X or Y array, but not raw positions
                    if 'X' in fileParts[2] and len(fileParts) < 4:
                        X = np.loadtxt(filePath, delimiter=' ')
                        self.Xs[scanIndex].append(X)
                    if 'Y' in fileParts[2] and len(fileParts) < 4:
                        Y = np.loadtxt(filePath, delimiter=' ')
                        self.Ys[scanIndex].append(Y)
                    ### Read scan direction
                    if 'V' in fileParts[2] and len(fileParts) > 3:
                        d = fileParts[3]
                        self.directions[scanIndex].append(d)
                        self.rawVoltages[scanIndex].append([])

    def alignment(self):
        '''
        Align different lines in a raw lineScans.
        '''
        np = __import__('numpy')

        for si, n in enumerate(self.numbers):
            for wi, (d, u, w) in enumerate(zip(self.directions[si], self.units[si], self.wavelengths[si])):

                try:
                    '''
                    posLines = Xs or Ys depending on the scan direction d in self.directions.
                    '''
                    posLines = []
                    startPositions = []
                    endPositions = []
                    lineLengths = []

                    if d in ['x']:
                        posLines = self.Ys
                        rows = len(self.Ys[si][wi])

                    else:
                        posLines = self.Xs
                        rows = len(self.Xs[si][wi])

                    for posLine in posLines:
                        lineLengths.append(len(posLine))
                        startPositions.append(min(posLine))
                        endPositions.append(max(posLine))
                    '''
                    Fill the above lists
                    '''
                    maxLineLength = max(lineLengths)
                    minStart = min(startPositions)
                    maxEnd = max(endPositions)
                    fineLineLength = maxLineLength * self.INTERP_MULTIPLIER
                    finePosLine = np.linspace(minStart, maxEnd, fineLineLength)
                    V = np.zeros((rows, len(finePosLine)))


                    for li, (pl, sl) in enumerate(zip(posLines, self.rawVoltages)):
                            for fpi, fp in enumerate(finePosLine):
                                posIndex = (np.abs(pl - fp)).argmin()
                                if self.interpolate:
                                    if pl[0] < pl[-1]: # If scanned forwards
                                        ps = 1
                                    else: # If scanned backwards
                                        ps = -1
                                    if ps * fp < ps * pl[0]: # If before the first recorded position
                                        V[li][fpi] = sl[posIndex]
                                    elif ps * fp > ps * pl[-1]:  # If after the last recorded position
                                        V[li][fpi] = sl[posIndex]
                                    else: # If in-between
                                        plPart = np.delete(pl, posIndex)
                                        posIndex2 = (np.abs(plPart - fp)).argmin()
                                        v1 = sl[posIndex]
                                        v2 = sl[posIndex2]
                                        distance1 = np.abs(fp - pl[posIndex])
                                        distance2 = np.abs(pl[posIndex2] - fp)
                                        rat1 = distance1 / (distance1 + distance2)
                                        rat2 = distance2 / (distance1 + distance2)
                                        V[li][fpi] = rat1 * v1 + rat2 * v2
                                else:
                                    V[li][fpi] = sl[posIndex]
                    self.rawVoltages[si][wi] = V
                except Exception as exc:
                    print('Could not process data:\n{}'.format(exc))


    def plot(self, *options):
        '''
        Generate plot(s) from a processed lineScans object to the output directory as a png
        '''
        os = __import__('os')
        np = __import__('numpy')
        plt = __import__('matplotlib.pyplot')
        mpl = __import__('matplotlib')
        outFilePath = options.get('outFilePath',"C:\Users\Discovery\Downloads")
        for n, U, V, W, X, Y in zip(self.numbers, self.units, self.rawVoltages, self.wavelengths, self.Xs, self.Ys):
            for w in W:
                wIndex = W.index(w)
                v = V[wIndex]
                figure = plt.figure(figsize=(5, 4))
                axes = figure.add_subplot(1, 1, 1)
                axes.set_aspect('equal')
                axes.set_xlabel('x (μm)')
                axes.set_ylabel('y (μm)')
                xMin = np.min(X[wIndex])
                xMax = np.max(X[wIndex])
                yMin = np.min(Y[wIndex])
                yMax = np.max(Y[wIndex])
                axes.set_xlim(xMin, xMax)
                axes.set_ylim(yMin, yMax)
                if self.plotView in ['above', 'Above']:
                    axes.invert_xaxis()
                    Z = np.flip(v, axis = 0)
                else:
                    Z = v
                ### Show image
                img = axes.imshow(Z,
                    cmap = mpl.cm.inferno,
                    alpha = 1.,
                    interpolation = 'none',
                    extent = (xMin, xMax, yMin, yMax),
                    zorder = 80)
                figure.show()
                if U[-1] in ['um']:
                    units = '{:.3f}um'.format(w)
                else:
                    units = '{:.0f}ic'.format(w)
                outFileString = '{}_scan{:03.0f}_{}'.format(expFolder, n, units)
                if self.interpolate:
                    outFileString += '_interp{:.0f}'.format(self.INTERP_MULTIPLIER)
                outFileName = '{}.{}'.format(outFileString, 'png')
                plt.savefig(outFilePath, dpi=300, bbox_inches='tight', pad_inches=0.01)




