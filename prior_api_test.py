'''
This is for unit testing the new methods in hld117.py
'''

import instruments.hld117 as hld117
from instruments.ni_daq import MultiChannelAnalogInput as MultiAI
import instruments.mircat as mircat
import time
import experiment.defaults as defaults
from timeit import default_timer as timer
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cmap
import csv
import math
'''Helper methods'''
def writeDataToCsv(lineScan, filepath = 'C:\\Users\\Discovery\\Desktop\\Today tests\\lineScan.csv'):
    '''
    <lineScan>: a list of lists. Each list is a scan line of voltageLines.
    '''
    with open(filepath, 'w', newline="") as f:
        # using csv.writer method from CSV package
        write = csv.writer(f)
        for line in lineScan:
            #Write item to outcsv
            write.writerow(line)

def cleanData(dataCh1, dataCh2,sampleNumber):
    '''
    <dataCh1>: list of measured numpy array of channel 1
    <dataCh2>: list of measured numpy array of channel 2
    <sampleNumber>: How many readings
    Output: A list of lists. Each list is a scan line of voltages.
    '''
    voltageLines = []
    counter = 0
    #print('Channel 1 data line numbers:'+ str(len(dataCh1)))
    #print('Channel 2 data line numbers:'+ str(len(dataCh2)))
    for ch1, ch2 in zip(dataCh1, dataCh2):
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
            if i%sampleNumber == sampleNumber-1:
                avg = sum(tmp_list[(i-sampleNumber+1):(i+1)])/sampleNumber
                voltageLine.append(avg)

        voltageLines.append(voltageLine)
        counter+=1

    lineScans = voltageLines

    return lineScans


def plotLinescans(lineScans, scanTime: float, stageSpeed: int):
    '''
    <lineScans>: A list of lists. Each list is a scan line of voltages.
    '''
    data = np.array(lineScans)
    plt.imshow(data, cmap=cmap.inferno)
    plt.title('Scan Time (s): ' + str(math.ceil(scanTime)) + '\nMax Stage Speed (micron/s): ' + str(stageSpeed))
    plt.colorbar()
    plt.show()


def makeTuneList(startingWL: float, endingWL: float, wlSteps: int):
    tuneList = []
    wlList = np.linspace(start = startingWL, stop = endingWL, num = wlSteps).tolist()
    for wl in wlList:
        qcl = 0
        if wl < 6:
            qcl = 1
        elif wl < 7.1:
            qcl = 2
        elif wl < 8:
            qcl = 3
        else:
            qcl = 4
        wl = float(format(wl,".3g"))
        tuneList.append((wl,qcl))
    return tuneList

def setLaser(qcl: int, wl: float):
    '''
    Set laser from initital status (laser constructor) to emission at <w> um emission
    Using <qcl> laser module
    Returns the laser object
    '''
    laser = mircat.laser()
    laser.connect()
    laser.arm()
    laser.stabilize()
    laser.tune(qcl, wl, wlUnits='um')
    laser.enable()

    return laser

def setStage(X0: int, Y0: int):
    '''
    Set the stage from initial status to connection the stage.
    Move the stage to <X0>, <Y0>.
    Reset <X0>, <Y0> as the new (0,0). (The trigger mechanism only works this way.)
    Return the stage object
    '''
    testStage = hld117.stage()
    testStage.connect()
    print('Stage connected.')
    testStage.goto(X0, Y0)
    while int(testStage.busy()) > 0:
        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
    testStage.set_position()

    return testStage

'''End Helper methods'''
def testLaser():
    testLaser = mircat.laser()
    testLaser.connect()
    testLaser.arm()
    testLaser.stabilize()
    '''
    Choose QCL = 2 for 6-7 um
    '''
    testLaser.tune(qcl = 2, wl = 6, wlUnits = 'um')
    time.sleep(10)
    testLaser.tune(qcl = 2, wl = 7, wlUnits = 'um')
    time.sleep(10)
    '''
    Be careful when enabling the laser emission.
    '''
    testLaser.enable()
    time.sleep(10)

    testLaser.disable()
    time.sleep(3)

    testLaser.disarm()
    time.sleep(3)

    testLaser.disconnect()


def testStageRes():
    testStage = hld117.stage()
    testStage.connect()
    x,y = testStage.encoder_res()
    print('x encoder resolution: '+ str(x) + ' encoder counts per micron.')
    print('y encoder resolution: '+ str(y) + ' encoder counts per micron.')
    (x, y) = testStage.get_position()
    print('x position: '+ str(x) + ' microns.')
    print('y position: '+ str(y) + ' microns.')
    testStage.disconnect()


def testArmTrigger():
    testStage = hld117.stage()
    testStage.connect()
    print('Stage connected.')
    testStage.goto(x = 0, y= 0)
    while int(testStage.busy()) > 0:
        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
    (x, y) = testStage.get_position()
    print('x position: '+ str(x) + ' microns.')
    print('y position: '+ str(y) + ' microns.')

    testStage.set_speed(v = 30000)
    (speed) = testStage.get_speed()
    print('stage speed: '+ str(speed) + ' microns per sec.')

    testStage.arm_trigger(F = 20, D = 20*2, A = 'X', N = 100, P = 'P' , W = 10)
    print('Trigger armed.')

    testStage.goto(x = 4*100, y= 0)

    testStage.disconnect()
    print('Stage disconnected.')


def testMakeSnakes():
    testStage = hld117.stage()
    paths = testStage.make_snakes(X0 = 0.1, Y0 = 0.1, dX = 2, dY = 2, M = 100, N = 100)
    print(paths[0])
    print(paths[1])
    print(paths[99])


def testSnakeTriggers(X0: float, Y0: float, xPixels: int, yPixels: int, stepSize: int, trigIndent: int,
                      returnDrift = defaults.HLD117_X_RETURN_DRIFT_UM):
    '''
    <X0>: starting x position of the snake                          float
    <Y0>: starting y position of the snake                          float
    <xPixels>: number of pixels in x direction                      int
    <yPixels>: number of pixels in y direction                      int
    <stepSize>: um per pixel                                        int
    <trigIndent>: starting encoding distance (um) for each trigger  int
    '''
    ### Initialize stage and paths
    testStage = setStage(X0 = X0, Y0 = Y0)
    paths = testStage.make_snakes(X0 = 0, Y0 = 0, xIndent=trigIndent, dX = stepSize, dY = stepSize,  M = xPixels, N = yPixels, returnDrift=returnDrift)

    ### Start snake scan
    testStage.goto(x = 0, y = 0)
    testStage.set_speed(v = 30000)
    startRun = timer()
    for path in paths:
        print('Scanning line ' + str(2*path['i']+1) + ' (forward)')
        testStage.goto(int(path['X0']),int(path['Y0']))
        testStage.arm_trigger(F = hld117.H117_TRIG_RES*trigIndent, D = hld117.H117_TRIG_RES*stepSize, A = 'X', N = xPixels, P = 'P' , W = 1)
        testStage.goto(int(path['X1']),int(path['Y0']))
        while int(testStage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
        testStage.goto(int(path['X1']),int(path['Y1']))
        print('Scanning line ' + str(2*path['i']+2) + ' (backward)')
        testStage.arm_trigger(F = hld117.H117_TRIG_RES*(xPixels*stepSize + path['drift']), D = -hld117.H117_TRIG_RES*stepSize, A = 'X', N = xPixels, P = 'P' , W = 1)
        testStage.goto(int(path['X0'] + path['drift']),int(path['Y1']))
        while int(testStage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
    endRun = timer()
    print('Scan complete (%.3f s).' % (endRun-startRun))
    ### End Snake scan
    testStage.goto(x = 0, y = 0)
    while int(testStage.busy()) > 0:
        time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
    testStage.disconnect()

def testSnakeScan(X0: int, Y0: int, xPixels: int, yPixels: int, stepSize: int, trigIndent= 1,
                  v = 30000, returnDrift = defaults.HLD117_X_RETURN_DRIFT_UM,
                  sampleNumber = defaults.DEF_SAMPLES_SNAKESCAN, sampleRate = defaults.DEF_SAMPLERATE, isHyperspectral = False, testStage = None):
    '''
    <X0>: starting x position of the snake                          float
    <Y0>: starting y position of the snake                          float
    <xPixels>: number of pixels in x direction                      int
    <yPixels>: number of pixels in y direction                      int
    <stepSize>: um per pixel                                        int
    <v>: max stage speed (um/s)                                     int
    <trigIndent>: skipped encoding distance (um) for each trigger   int
    <returnDrift> to calibrate the backward scan drift              float
    '''


    ### Initialize stage, paths, data retrieval
    if not isHyperspectral:
        testStage = setStage(X0 = X0, Y0 = Y0)
    paths = testStage.make_snakes(X0 = 0, Y0 = 0, xIndent=trigIndent, dX = stepSize, dY = stepSize, M = xPixels, N = yPixels, returnDrift = returnDrift)
    dataCh1 = []
    dataCh2 = []


    ### Setup, start triggered acquisition task
    multipleAI = MultiAI([defaults.PCI_CH_X, defaults.PCI_CH_Y])
    multipleAI.configure_triggered(defaults.PCI_SNAKE_TRIG, sampleNumber, sampleRate)
    multipleAI.stream_to_disk()
    multipleAI.start_task()


    ### Start snake scan
    testStage.goto(x = 0, y = 0)
    testStage.set_speed(v = v)
    startRun = timer()
    for path in paths:
        print('Scanning line ' + str(2*path['i']+1) + ' (forward)')
        testStage.goto(int(path['X0']),int(path['Y0']))
        while int(testStage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

        testStage.arm_trigger(F = hld117.H117_TRIG_RES*trigIndent, D = hld117.H117_TRIG_RES*stepSize, A = 'X', N = xPixels, P = 'P' , W = 1)
        #print('Trigger armed.')
        testStage.goto(int(path['X1']),int(path['Y0']))
        while int(testStage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
        #print('Stage arrived destination.')
        data_forward = multipleAI.read_line(xPixels*sampleNumber)
        dataCh1.append(data_forward[0])
        dataCh2.append(data_forward[1])

        testStage.goto(int(path['X1']),int(path['Y1']))
        while int(testStage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)

        print('Scanning line ' + str(2*path['i']+2) + ' (backward)')
        testStage.arm_trigger(F = hld117.H117_TRIG_RES*(xPixels*stepSize + path['drift']), D = -hld117.H117_TRIG_RES*stepSize, A = 'X', N = xPixels, P = 'P' , W = 1)
        testStage.goto(int(path['X0'] + path['drift']),int(path['Y1']))
        while int(testStage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)
        data_backward = multipleAI.read_line(xPixels*sampleNumber)
        dataCh1.append(data_backward[0])
        dataCh2.append(data_backward[1])

    endRun = timer()
    print('Scan complete (%.3f s).' % (endRun-startRun))
    ### End Snake scan

    ### Stop, clear triggered acquisition task
    multipleAI.stop_task() # Stop acquisition task
    multipleAI.clear_task()
    testStage.goto(x = 0, y = 0)
    while int(testStage.busy()) > 0:
            time.sleep(defaults.IMAG_SCAN_STEP_BUSY_WAIT)


    ### Clean the data and plot.
    voltageLines = cleanData(dataCh1, dataCh2, sampleNumber)
    print('Retrieved '+ str(len(voltageLines))+ ' scan lines (unit: volt).')

    if not isHyperspectral:
        writeDataToCsv(voltageLines)
        plotLinescans(voltageLines, scanTime=endRun-startRun, stageSpeed=v)
        testStage.disconnect()

    return voltageLines, testStage


def testSnakeScanWithLaser(X0: float, Y0: float, xPixels: int, yPixels: int, stepSize: int,
                           qcl: int, wl: float,
                           trigIndent = 1,
                           v = 30000,
                           returnDrift = defaults.HLD117_X_RETURN_DRIFT_UM,
                           sampleNumber = defaults.DEF_SAMPLES_SNAKESCAN, sampleRate = defaults.DEF_SAMPLERATE):
    '''
    setLaser + test Snakescan
    '''
    testLaser = setLaser(qcl, wl)

    testSnakeScan(X0, Y0, xPixels, yPixels, stepSize, trigIndent, v, returnDrift)

    print('Rep. rate (Hz):')
    print(testLaser.get_pulse_rate(qcl))
    print('Pulse width (ns):')
    print(testLaser.get_pulse_width(qcl))

    testLaser.disable()
    testLaser.disarm()
    testLaser.disconnect()

def hyperspectral(X0: float, Y0: float, xPixels: int, yPixels: int, stepSize: int,
                           startingWL: float, endingWL: float, wlSteps: int,
                           trigIndent = 1,
                           v = 30000,
                           returnDrift = defaults.HLD117_X_RETURN_DRIFT_UM,
                           sampleNumber = defaults.DEF_SAMPLES_SNAKESCAN, sampleRate = defaults.DEF_SAMPLERATE):
    '''
    Tune laser after each snake scan.
    '''
    testStage = setStage(X0 = X0, Y0 = Y0)
    tuneList = makeTuneList(startingWL, endingWL, wlSteps)
    isLaserOn = False
    for tune in tuneList:
        if not isLaserOn:
            testLaser = setLaser(qcl = tune[1], wl = tune[0])
            isLaserOn = True
        else:
            testLaser.tune(qcl = tune[1], wl = tune[0])
        lineScan, testStage = testSnakeScan(X0, Y0, xPixels, yPixels, stepSize, trigIndent, v, returnDrift, isHyperspectral=True, testStage=testStage)
        filepath = 'C:\\Users\\Discovery\\Desktop\\Today tests\\lineScan_'+ str(tune[0]).replace(".", "_") + 'um.csv'
        writeDataToCsv(lineScan, filepath = filepath)
        print('Rep. rate (Hz):')
        print(testLaser.get_pulse_rate(tune[1]))
        print('Pulse width (ns):')
        print(testLaser.get_pulse_width(tune[1]))
    testStage.disconnect()
    testLaser.disable()
    testLaser.disarm()
    testLaser.disconnect()





#testStageRes()
#testArmTrigger()
#testMakeSnakes()
#tuneList = makeTuneList(startingWL = 5.65, endingWL = 7, wlSteps = 70)
#print(tuneList)
#testSnakeTriggers(0,0,100,1,2,trigIndent= 50)


#   Test laser
'''
Working parameters
'''
#testLaser()
#testSnakeScanWithLaser(0,0,200,200,2, qcl = 2, wl = 6, returnDrift= -16)
#testSnakeScan(0,0,200,200,2, v = 3000, returnDrift= 191, trigIndent= 200)
#testSnakeScan(0,0,150,75,2,v=3000,returnDrift= -8)

#testSnakeScan(0,0,400,150,2, v=2000, returnDrift=-6)

hyperspectral(0,0,400,150,2,startingWL=5.65,endingWL=7, wlSteps=70, v=2000, returnDrift= -6)
'''
'''
#testSnakeScan(0,0,600,300,2, v=2000, returnDrift=-6)
# Current test line pixel limit: 600
#testSnakeScan(-100,-100,100,50,2,1)
#testSnakeScanWithLaser(0,0,100,50,2, qcl = 2, wl = 6)

