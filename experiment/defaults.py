'''
defaults
Giovanni Sartorello (srtgnn@gmail.com)
Default values for MIRcat spectral scan UI
Python 3.10.5 on Windows 10
Created 2020-Oct-20
'''

'''NI PCIe channels. Should be binary strings (b'') for compatibility
   Use NI MAX to verify device and channel names.'''

PCI_CH_X = b'Dev1/ai0'
PCI_CH_Y = b'Dev1/ai1'
PCI_TRIG = b'/Dev1/PFI12'

'''Stage ports and parameters
   One set for the HLD117 in 147, one for the H117 in BE13.'''

### HLD117 parameters (linear drive, 147)
HLD117_COM_PORT = 3
HLD117_MAX_SPEED = 30000 # Maximum stage speed, um/s, found in Prior demo app
HLD117_MAX_ACC = 142750 # Maximum stage acceleration, um/s^2, found in Prior demo app
HLD117_X_TRAVEL_UM = 120000 # um
HLD117_Y_TRAVEL_UM = 80000 # um

### H117 parameters (stepper motors, BE13)
H117_COM_PORT = 7
H117_MAX_SPEED = 15000 # Maximum stage speed, um/s, found in Prior demo app
H117_MAX_ACC = 28550 # Maximum stage acceleration, um/s^2, found in Prior demo app
H117_X_TRAVEL_UM = 114000 # um
H117_Y_TRAVEL_UM = 75000 # um

### Common parameters
STAGE_DEF_X_STEP_UM = 1000 # um
STAGE_DEF_Y_STEP_UM = 1000 # um

### Generic default port, should never be needed in practice
STAGE_DEF_COM_PORT = 3

'''Color dictionaries'''

NEW_TAB10 = {'blue' : '#4e79a7',
             'orange' : '#f28e2b',
             'red' : '#e15759',
             'cyan' : '#76b7b2',
             'green' : '#59a14e',
             'yellow' : '#edc949',
             'violet' : '#b07aa2',
             'pink' : '#ff9da7',
             'brown' : '#9c755f',
             'gray' : '#bab0ac'} # New Tableau 10 palette
GS_COLORS = {'background': '#1f1f1f',
             'bg-alt': '#e6e6e6',
             'bg-fault': '#1f1f1f',
             'bg-operating': '#e6e6e6',
             'bg-warn': '#d75a3e',
             'border': '#404040',
             'border-alt': '#303030',
             'border-fault': '#ff0000',
             'border-operating': '#00ff00',
             'border-warn': '#d75a3e',
             'hover': '#353535',
             'hover-alt': '#d8d8d8',
             'hover-warn': '#b73e26',
             'menu': '#0c0c0d',
             'text': '#b9b9b9',
             'text-alt': '#141414',
             'text-lo': '#989898',
             'text-lo-alt': '#505050',
             'text-hi': '#cf8730',
             'warning': '#d75a3e'}
SOLARIZED = {'base03' : '#002b36',
             'base02': '#073642',
             'base01': '#586e75',
             'base00': '#657b83',
             'base0': '#839496',
             'base1': '#93a1a1',
             'base2': '#eee8d5',
             'base3': '#fdf6e3',
             'yellow': '#b58900',
             'orange': '#cb4b16',
             'red': '#dc322f',
             'magenta': '#d33682',
             'violet': '#6c71c4',
             'blue': '#268bd2',
             'cyan': '#2aa198',
             'green': '#859900'}
STG_COLORS = {'acqText': '#FFFFFF',
              'edge': '#99CCCC',
              'fill' : '#336666',
              'marker' : '#FF0000',
              'pattern' : '#3333CC',
              'text' : '#FF0000'}

'''Colors'''

DARK_PLOT_AXES = GS_COLORS['text']
DARK_PLOT_BACKGROUND = GS_COLORS['background']
DEFAULT_PLOT_AXES = '#000000'
DEFAULT_PLOT_BACKGROUND = '#FFFFFF'
PLOT_COLOR = NEW_TAB10['blue']
PLOT_COLOR_REF = NEW_TAB10['green']
PLOT_COLOR_T = NEW_TAB10['red']
PLOT_COLOR_DARK = '#0000FF'
PLOT_COLOR_REF_DARK = '#00FF00'
PLOT_COLOR_T_DARK = '#FF0000'

'''Colormaps'''

# DEFAULT_COLORMAP = plt.cm.Spectral

'''Directories and file names'''

DEF_DATA_DIRECTORY = 'C:\\Data\\_experiment_data'
DEF_SCAN_IMAG_SUBFOLDER = 'scanningimaging'
DEF_FILENAME = '_wl-um_x-v_y-v_r-v.txt' # Append to data files
# DEF_FILENAME_XY = '_stg-x-um_stg-y-um_wl-um_lia-x-v_lia-y-v_lia-r-v.txt' # Append to data files
DEF_FILENAME_SCAN_IMAG_X = '_X-um.txt' # For scanning imaging experiments
DEF_FILENAME_SCAN_IMAG_Y = '_Y-um.txt' # For scanning imaging experiments
DEF_FILENAME_SCAN_IMAG_V = '_V-V.txt' # For scanning imaging experiments
LOG_FILENAME = 'experiment.log'

'''MIRcat QCL parameters'''

### MIRcat default pulse parameters
### These cannot be queried from the laser
MIN_PULSERATE_HZ = 100
MIN_PULSEWIDTH_NS = 20

### MIRcat default wavelength parameters
### Limits changed to have maximum power in overlap regions
MIN_WL_QCL1_UM = 5.12 # um
# MIN_WL_QCL2_UM = 5.85 # um # Actual limit
MIN_WL_QCL2_UM = 5.95 # um # Restricted limit
# MIN_WL_QCL3_UM = 6.83 # um # Actual limit
# MIN_WL_QCL3_UM = 7.1 # um # Restricted limit
MIN_WL_QCL3_UM = 7.05 # um # Revised restricted limit
MIN_WL_QCL4_UM = 8.20 # um
# MAX_WL_QCL1_UM = 6.04 # um # Actual limit
MAX_WL_QCL1_UM = 5.95 # um # Restricted limit
# MAX_WL_QCL2_UM = 7.16 # um # Actual limit
# MAX_WL_QCL2_UM = 7.1 # um # Restricted limit
MAX_WL_QCL2_UM = 7.05 # um # Revised restricted limit
MAX_WL_QCL3_UM = 7.69 # um
MAX_WL_QCL4_UM = 11.3 # um

### MIRcat default wavenumber parameters
### Limits changed to have maximum power in overlap regions
MIN_WN_QCL1_INVCM = 1953.1 # cm^-1
# MIN_WN_QCL2_INVCM = 1709.4 # cm^-1 # Actual limit
MIN_WN_QCL2_INVCM = 1692.0 # cm^-1 # Restricted limit
# MIN_WN_QCL3_INVCM = 1464.1 # cm^-1 # Actual limit
# MIN_WN_QCL3_INVCM = 1408.5 # cm^-1 # Restricted limit
MIN_WN_QCL3_INVCM = 1418.5 # cm^-1 # Revised restricted limit
MIN_WN_QCL4_INVCM = 1219.5 # cm^-1
# MAX_WN_QCL1_INVCM = 1655.6 # cm^-1 # Actual limit
MAX_WN_QCL1_INVCM = 1692.0 # cm^-1 # Restricted limit
# MAX_WN_QCL2_INVCM = 1396.6 # cm^-1 # Actual limit
# MAX_WN_QCL2_INVCM = 1408.5 # cm^-1 # Restricted limit
MAX_WN_QCL2_INVCM = 1418.5 # cm^-1 # Revised estricted limit
MAX_WN_QCL3_INVCM = 1300.4 # cm^-1
MAX_WN_QCL4_INVCM = 885.0 # cm^-1

### Deprecated MIRcat parameters
### These are now read from the laser directly
# MAX_CURR_QCL1_MILLIAMP = 450 # mA
# MAX_CURR_QCL2_MILLIAMP = 825 # mA
# MAX_CURR_QCL3_MILLIAMP = 575 # mA
# MAX_CURR_QCL4_MILLIAMP = 950 # mA
# NUMBER_OF_QCLS = 4
### These are unused
# DEF_PULSERATE_HZ = 100 # kHz
# DEF_PULSEWIDTH_NS = 500 # ns

### QCL wavelength/qavenumber ranges
WN_MAXIMUMS_INVCM = [MAX_WN_QCL1_INVCM,
                     MAX_WN_QCL2_INVCM,
                     MAX_WN_QCL3_INVCM,
                     MAX_WN_QCL4_INVCM]
WL_MAXIMUMS_UM = [MAX_WL_QCL1_UM,
                  MAX_WL_QCL2_UM,
                  MAX_WL_QCL3_UM,
                  MAX_WL_QCL4_UM]
WN_MINIMUMS_INVCM = [MIN_WN_QCL1_INVCM,
                     MIN_WN_QCL2_INVCM,
                     MIN_WN_QCL3_INVCM,
                     MIN_WN_QCL4_INVCM]
WL_MINIMUMS_UM = [MIN_WL_QCL1_UM,
                  MIN_WL_QCL2_UM,
                  MIN_WL_QCL3_UM,
                  MIN_WL_QCL4_UM]

'''Experiment parameters'''

### Default NI PCIe card sampling parameters
# DEF_SAMPLERATE = 1000 # Hz
# DEF_SAMPLERATE = 1000000 # Hz
DEF_SAMPLERATE = 100000 # Hz
# DEF_SAMPLES = 100
# DEF_SAMPLES = 320
DEF_SAMPLES = 32
DEF_SAMPLES_IMAGING = 1

### Default scan/sweep parameters
DEF_WL_START_UM = 5.2 # Default scan/sweep start wavelength, um
DEF_WL_END_UM = 5.8 # Default scan/sweep end wavelength, um
DEF_WL_STEP_UM = 0.1 # Default scan/sweep wavelength step, um

### Default sweep parameters
MAX_SWEEP_SPEED_UM = 0.5
MAX_SWEEP_SPEED_INVCM = 100

### Multiwell holder and scan parameters
DEF_WELLS_X = 8 # Default number of wells along x
DEF_WELLS_Y = 2 # Default number of wells along y
DEF_WELL_SEP_X_UM = 10000 # Default well separation along x, um
DEF_WELL_SEP_Y_UM = 10000 # Default well separation along y, um
DEF_WELL_ORIGIN_X_UM = -35000 # Default position of origin well, x, um
DEF_WELL_ORIGIN_Y_UM = 5000 # Default position of origin well, y, um
DEF_WELL_CORNER_X_UM = 35000 # Default position of top corner well, x, um
DEF_WELL_CORNER_Y_UM = -5000 # Default position of top corner well, y, um
DEF_DWELL_TIME_S = 4 # Default dwell time, s
DEF_NUMBER_OF_ACQ = 1 # Default number of acquisitions
DEF_SLEEP_INTERVAL = 0.1 # Default sleep interval for move cycle, s

### Default imaging scan parameters
IMAG_SCAN_ORIGIN_X_UM = 0
IMAG_SCAN_ORIGIN_Y_UM = 0
# IMAG_SCAN_STEP_X_UM = 10
# IMAG_SCAN_STEP_Y_UM = 10
# IMAG_SCAN_SIZE_X_UM = 100
# IMAG_SCAN_SIZE_Y_UM = 100
IMAG_SCAN_STEP_X_UM = 4000
IMAG_SCAN_STEP_Y_UM = 4000
IMAG_SCAN_SIZE_X_UM = 4
IMAG_SCAN_SIZE_Y_UM = 4
IMAG_SCAN_WL_LIST = '6.7'
IMAG_SCAN_STEP_BUSY_WAIT = 0.01 # Stage busy query wait time, s

'''Gamepad parameters'''

GAMEPAD_UPDATE_INTERVAL_S = 0.1 # update interval for the gamepad loop, s
JOY_DEADZONE = 0.10 # Threshold for thumbstick deadzone

'''UI look and feel'''

### Fonts
FONT_FAMILY = 'Open Sans Semibold'
FONT_SIZE = 12
FONT_SIZE_MEDIUM = 11
FONT_SIZE_SMALL = 10
FONT_SIZE_TINY = 8

### UI parameters
COL_WIDTH = 100
NUMBER_OF_ROWS = 14 # UI grid template rows
NUMBER_OF_COLS = 12 # UI grid template columns
MSG_TIMEOUT = 1000 # ms
ROW_HEIGHT = 20

### Style sheets
STYLE_ARMED = '''QPushButton {{
        background-color: {};
        border: 2px solid {};
        border-radius: 5px;
        color: {};
    }}
    QPushButton:checked {{
        background-color: {};
        border: 2px solid {};
        color: {};
    }}
    QPushButton:hover {{
        background-color: {};
    }}
    QPushButton:checked:hover {{
        background-color: {};
    }}'''.format(GS_COLORS['background'],
                 GS_COLORS['border'],
                 GS_COLORS['text'],
                 GS_COLORS['bg-warn'],
                 GS_COLORS['border-alt'],
                 GS_COLORS['text-alt'],
                 GS_COLORS['hover'],
                 GS_COLORS['hover-warn'])
STYLE_BUTTON = '''QPushButton {{
        background-color: {};
        border: 2px solid {};
        border-radius: 5px;
        color: {};
    }}
    QPushButton:checked {{
        background-color: {};
        border: 2px solid {};
        color: {};
    }}
    QPushButton:hover {{
        background-color: {};
    }}
    QPushButton:checked:hover {{
        background-color: {};
    }}'''.format(GS_COLORS['background'],
                 GS_COLORS['border'],
                 GS_COLORS['text'],
                 GS_COLORS['bg-alt'],
                 GS_COLORS['border-alt'],
                 GS_COLORS['text-alt'],
                 GS_COLORS['hover'],
                 GS_COLORS['hover-alt'])
STYLE_BUTTON_JOY = '''QPushButton {{
        background-color: {};
        border: 2px solid {};
        border-radius: 4px;
        width: 40px;
        color: {};
    }}
    QPushButton:checked {{
        background-color: {};
        border: 2px solid {};
        color: {};
    }}
    QPushButton:hover {{
        background-color: {};
    }}
    QPushButton:checked:hover {{
        background-color: {};
    }}'''.format(GS_COLORS['background'],
                 GS_COLORS['border'],
                 GS_COLORS['text'],
                 GS_COLORS['bg-operating'],
                 GS_COLORS['border-operating'],
                 GS_COLORS['text-alt'],
                 GS_COLORS['hover'],
                 GS_COLORS['hover-alt'])
STYLE_BUTTON_JOY_FAULT = '''QPushButton {{
        background-color: {};
        border: 2px solid {};
        border-radius: 4px;
        width: 40px;
        color: {};
    }}
    QPushButton:checked {{
        background-color: {};
        border: 2px solid {};
        color: {};
    }}
    QPushButton:hover {{
        background-color: {};
    }}
    QPushButton:checked:hover {{
        background-color: {};
    }}'''.format(GS_COLORS['background'],
                 GS_COLORS['border'],
                 GS_COLORS['text'],
                 GS_COLORS['bg-fault'],
                 GS_COLORS['border-fault'],
                 GS_COLORS['text'],
                 GS_COLORS['hover'],
                 GS_COLORS['hover'])
STYLE_BUTTON_UNIT = '''QPushButton {{
        background-color: {};
        border: 2px solid {};
        border-radius: 5px;
        color: {};
    }}
    QPushButton:checked {{
        background-color: {};
        border: 2px solid {};
        color: {};
    }}
    QPushButton:hover {{
        background-color: {};
    }}
    QPushButton:checked:hover {{
        background-color: {};
    }}'''.format(GS_COLORS['background'],
                 GS_COLORS['border'],
                 GS_COLORS['text'],
                 GS_COLORS['background'],
                 GS_COLORS['border'],
                 GS_COLORS['text'],
                 GS_COLORS['hover'],
                 GS_COLORS['hover'])
STYLE_COMBOBOX =''' QComboBox {{
        color: {};
        border: 2px solid {};
        border-radius: 5px;
    }}
    ::drop-down {{
        width: 25px;
    }}
    ::down-arrow {{
        border-radius: 2px;
        border: 2px solid {};
        image: url(icons/arrow.png);
        height: 14px;
        width: 14px;
    }}
    ::down-arrow:on {{
        top: 1px;
        left: 1px;
    }}
    QListView {{
        border: 1px solid {};
        border-radius: 5px;
        color: {};
    }}
    '''.format(GS_COLORS['text-lo'],
               GS_COLORS['border'],
               GS_COLORS['border'],
               GS_COLORS['border'],
               GS_COLORS['text-lo'])
STYLE_CONTAINER = '''QWidget {{
        background-color: {};
    }}'''.format(GS_COLORS['background'])
STYLE_GAMEPAD_BINDINGS_WINDOW = '''QMainWindow {{
        background-image: url(images/xbox_controller_white_resize.jpg);
        background-position: center;
        background-repeat: no-repeat;
    }}'''.format()
STYLE_INPUT = '''QLineEdit {{
        color: {};
        border: 2px solid {};
        border-radius: 5px;
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-lo'],
                 GS_COLORS['border'])
STYLE_INPUT_LOCKED = '''QLineEdit {{
        color: {};
        border: 2px solid {};
        border-radius: 5px;
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-lo-alt'],
                 GS_COLORS['border'])
STYLE_INPUT_LOCKED_WARN = '''QLineEdit {{
        color: {};
        border: 2px solid {};
        border-radius: 5px;
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['warning'],
                 GS_COLORS['border'])
STYLE_INPUT_ALT = '''QLineEdit {{
        background-color: {};
        color: {};
        border: 2px solid {};
        border-radius: 5px;
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['bg-alt'],
                 GS_COLORS['text-alt'],
                 GS_COLORS['border-alt'])
STYLE_LABEL_ALT = '''QLabel {{
        color:{};
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-hi'])
STYLE_LABEL_EMPH = '''QLabel {{
        color:{};
        qproperty-alignment: AlignLeft;
    }}'''.format(GS_COLORS['text'])
STYLE_LABEL_EMPH_CENTER = '''QLabel {{
        color:{};
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text'])
STYLE_LABEL_GAMEPAD = '''QLabel {{
        background-color:#ffffff;
        color:#000000;
        qproperty-alignment: AlignLeft;
    }}'''.format()
STYLE_LABEL_READ = '''QLabel {{
        color:{};
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-lo'])
STYLE_LABEL_READ_ALT = '''QLabel {{
        color:{};
        qproperty-alignment: AlignLeft;
    }}'''.format(GS_COLORS['text-hi'])
STYLE_LABEL_UNIT = '''QLabel {{
        color:{};
        qproperty-alignment: AlignLeft;
        qproperty-alignment: AlignMiddle;
    }}'''.format(GS_COLORS['text-lo'])
STYLE_LIST_WIDGET = '''QListWidget {{
        border: 2px solid {};
        border-radius: 5px;
        color:{};
    }}
    ::item {{
        color:{};
        background-color: {};
    }}'''.format(GS_COLORS['border'],
            GS_COLORS['bg-alt'],
            GS_COLORS['text-lo'],
            'transparent')
STYLE_MENU = ''' QMenu {{
        background-color: {};
        color: {};
    }}'''.format(GS_COLORS['menu'],
            GS_COLORS['text'])
STYLE_MENUBAR = ''' QMenuBar {{
        background-color: {};
        color: {};
    }}'''.format(GS_COLORS['menu'],
                 GS_COLORS['text'])
STYLE_STATUSBAR = ''' QStatusBar {{
        background: {};
        color: {};
    }}'''.format(GS_COLORS['menu'],
                 GS_COLORS['text'])
STYLE_TABS = '''QTabWidget::pane {{
        background: {};
        border: 2px solid {};
    }}
    QTabBar::tab {{
        background: {};
        border: 2px solid {};
        border-bottom: 0px solid #FFFFFF;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        color: {};
        min-width: 24ex;
        padding: 4px;
    }}
    QTabBar::tab:selected {{
        background: {};
        border-color: {};
        color: {};
    }}
    QTabBar::tab:hover {{
        background: {};
        border-color: {};
    }}'''.format(GS_COLORS['bg-alt'],
                 GS_COLORS['border'],
                 GS_COLORS['background'],
                 GS_COLORS['border-alt'],
                 GS_COLORS['text-lo-alt'],
                 GS_COLORS['border'],
                 GS_COLORS['border'],
                 GS_COLORS['text-lo'],
                 GS_COLORS['hover'],
                 GS_COLORS['border-alt'])
STYLE_TEXT = '''QTextEdit {{
        color: {};
        border: 2px solid {};
        border-radius: 5px;
    }}'''.format(GS_COLORS['text-lo'],
                 GS_COLORS['border'])
