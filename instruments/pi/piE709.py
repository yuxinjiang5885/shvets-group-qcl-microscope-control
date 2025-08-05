from pipython import GCSDevice
with GCSDevice('E-709') as pidevice:
    pidevice.InterfaceSetupDlg()
    print(pidevice.qIDN())
    currPos=pidevice.qPOS()
    print(currPos)
    pidevice.MOV(1, 65)
    currPos=pidevice.qPOS(1)
    print(currPos)
pidevice.CloseConnection()