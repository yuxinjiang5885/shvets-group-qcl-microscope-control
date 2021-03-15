'''
defaults
Giovanni Sartorello (srtgnn@gmail.com)
Default values for MIRcat spectral scan UI
Python 3.8.3 on Windows 10
Created 2020-Oct-20
'''

import matplotlib.pyplot as plt

### NI PCIe channels. Should be binary strings (b'') for compatibility
### Use NI MAX to verify device and channel names.
PCI_CH_X = b'Dev1/ai0'
PCI_CH_Y = b'Dev1/ai1'
PCI_TRIG = b'/Dev1/PFI12'

# Color dictionaries
newTab10 = {'blue' : '#4e79a7', 'orange' : '#f28e2b', 'red' : '#e15759',
            'cyan' : '#76b7b2', 'green' : '#59a14e', 'yellow' : '#edc949',
            'violet' : '#b07aa2', 'pink' : '#ff9da7', 'brown' : '#9c755f',
            'gray' : '#bab0ac'} # New Tableau 10 palette
GS_COLORS = {'background': '#1f1f1f',
             'bg-alt': '#e6e6e6',
             'bg-warn': '#d75a3e',
             'border': '#404040',
             'border-alt': '#303030',
             'border-warn': '#d75a3e',
             'hover': '#353535',
             'hover-alt': '#d8d8d8',
             'hover-warn': '#b73e26',
             'menu': '#0c0c0d',
             'text': '#b9b9b9',
             'text-alt': '#141414',
             'text-lo': '#989898',
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
DEFAULT_COLORMAP = plt.cm.Spectral # Default colormap

# Directories
DEF_DATA_DIRECTORY = 'C:\\Data\\_experiment_data'
DEF_FILENAME = '_wl-um_x-v_y-v_r-v.txt' # Append to data files

# MIRcat default parameters
# Limits changed to have maximum power in overlap regions
DEF_PULSERATE_HZ = 100 # kHz
DEF_PULSEWIDTH_NS = 500 # ns
MIN_WN_QCL1_INVCM = 1953.1 # cm^-1
# MIN_WN_QCL2_INVCM = 1709.4 # cm^-1 # Actual limit
MIN_WN_QCL2_INVCM = 1692.0 # cm^-1 # Restricted limit
# MIN_WN_QCL3_INVCM = 1464.1 # cm^-1 # Actual limit
# MIN_WN_QCL3_INVCM = 1408.5 # cm^-1 # Restricted limit
MIN_WN_QCL3_INVCM = 1418.5 # cm^-1 # Revised restricted limit
MIN_WN_QCL4_INVCM = 1219.5 # cm^-1
MIN_WL_QCL1_UM = 5.12 # um
# MIN_WL_QCL2_UM = 5.85 # um # Actual limit
MIN_WL_QCL2_UM = 5.95 # um # Restricted limit
# MIN_WL_QCL3_UM = 6.83 # um # Actual limit
# MIN_WL_QCL3_UM = 7.1 # um # Restricted limit
MIN_WL_QCL3_UM = 7.05 # um # Revised restricted limit
MIN_WL_QCL4_UM = 8.20 # um
MAX_CURR_QCL1_MILLIAMP = 450 # mA
MAX_CURR_QCL2_MILLIAMP = 825 # mA
MAX_CURR_QCL3_MILLIAMP = 575 # mA
MAX_CURR_QCL4_MILLIAMP = 950 # mA
# MAX_WN_QCL1_INVCM = 1655.6 # cm^-1 # Actual limit
MAX_WN_QCL1_INVCM = 1692.0 # cm^-1 # Restricted limit
# MAX_WN_QCL2_INVCM = 1396.6 # cm^-1 # Actual limit
# MAX_WN_QCL2_INVCM = 1408.5 # cm^-1 # Restricted limit
MAX_WN_QCL2_INVCM = 1418.5 # cm^-1 # Revised estricted limit
MAX_WN_QCL3_INVCM = 1300.4 # cm^-1
MAX_WN_QCL4_INVCM = 885.0 # cm^-1
# MAX_WL_QCL1_UM = 6.04 # um # Actual limit
MAX_WL_QCL1_UM = 5.95 # um # Restricted limit
# MAX_WL_QCL2_UM = 7.16 # um # Actual limit
# MAX_WL_QCL2_UM = 7.1 # um # Restricted limit
MAX_WL_QCL2_UM = 7.05 # um # Revised restricted limit
MAX_WL_QCL3_UM = 7.69 # um
MAX_WL_QCL4_UM = 11.3 # um
NUMBER_OF_QCLS = 4
WL_MAXIMUMS_INVCM = [MAX_WN_QCL1_INVCM,
                     MAX_WN_QCL2_INVCM,
                     MAX_WN_QCL3_INVCM,
                     MAX_WN_QCL4_INVCM]
WL_MAXIMUMS_UM = [MAX_WL_QCL1_UM,
                  MAX_WL_QCL2_UM,
                  MAX_WL_QCL3_UM,
                  MAX_WL_QCL4_UM]
WL_MINIMUMS_INVCM = [MIN_WN_QCL1_INVCM,
                     MIN_WN_QCL2_INVCM,
                     MIN_WN_QCL3_INVCM,
                     MIN_WN_QCL4_INVCM]
WL_MINIMUMS_UM = [MIN_WL_QCL1_UM,
                  MIN_WL_QCL2_UM,
                  MIN_WL_QCL3_UM,
                  MIN_WL_QCL4_UM]
MAX_SWEEP_SPEED_UM = 0.5
MAX_SWEEP_SPEED_INVCM = 100

# NI PCIe card sampling default parameters
# DEF_SAMPLERATE = 1000 # Hz
# DEF_SAMPLERATE = 1000000 # Hz
DEF_SAMPLERATE = 100000 # Hz
# DEF_SAMPLES = 100
# DEF_SAMPLES = 320
DEF_SAMPLES = 32

# Default scan/sweep parameters
DEF_WL_START_UM = 5.2 # Default scan/sweep start wavelength, um
DEF_WL_END_UM = 5.8 # Default scan/sweep end wavelength, um
DEF_WL_STEP_UM = 0.1 # Default scan/sweep wavelength step, um

# UI look and feel settings
COL_WIDTH = 100
FONT_FAMILY = 'Open Sans Semibold'
FONT_SIZE = 12
NUMBER_OF_ROWS = 14 # UI grid template rows
NUMBER_OF_COLS = 11 # UI grid template columns
MSG_TIMEOUT = 1000 # ms
ROW_HEIGHT = 20
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
STYLE_BAR = ''' QMenuBar {{
        background-color: {};
        color: {};
    }}'''.format(GS_COLORS['menu'],
                 GS_COLORS['text'])
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
STYLE_UNITBUTTON = '''QPushButton {{
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
STYLE_CONTAINER = '''QWidget {{
        background-color: {};
    }}'''.format(GS_COLORS['background'])
STYLE_LABEL_EMPH = '''QLabel {{
        color:{};
        qproperty-alignment: AlignLeft;
    }}'''.format(GS_COLORS['text'])
STYLE_INPUT = '''QLineEdit {{
        color: {};
        border: 2px solid {};
        border-radius: 5px;
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-lo'],
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
STYLE_LABEL_READ = '''QLabel {{
        color:{};
        qproperty-alignment: AlignCenter;
    }}'''.format(GS_COLORS['text-lo'])
STYLE_LABEL_UNIT = '''QLabel {{
        color:{};
        qproperty-alignment: AlignLeft;
        qproperty-alignment: AlignMiddle;
    }}'''.format(GS_COLORS['text-lo'])
STYLE_TEXT = '''QTextEdit {{
        color: {};
        border: 2px solid {};
        border-radius: 5px;
    }}'''.format(GS_COLORS['text-lo'],
                 GS_COLORS['border'])
