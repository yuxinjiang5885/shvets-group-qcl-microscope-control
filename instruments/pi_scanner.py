'''
Pi_scanner.py
This module provides a GUI for controlling a PI objective scanner,
as well as autofocus functionality.
Steven Huang
Created 2025-Aug-07
'''



from pipython import GCSDevice, pitools  # for PI objective scanner
from instruments.ni_daq import MultiChannelAnalogInput
from experiment.defaults import PCI_CH_X, PCI_CH_Y

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QTextEdit, QApplication,
    QHBoxLayout, QLabel, QLineEdit, QCheckBox  # <-- Add QCheckBox
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QTextCursor  # Add this import at the top
import sys

from standalone_stage_ui_h117 import MODEL

class piScanner:
    """Class for holding connection to the PI E-709 piezo controller"""

    RANGE_MIN = 0
    RANGE_MAX = 400

    def __init__(self):
        self.target_x = None
        self.target_y = None
        self.rangemax = self.RANGE_MAX
        self.rangemin = self.RANGE_MIN
        self.af_min = -10
        self.af_max = 10
        self.af_step = 1
        self.autofocus_on_imaging = False

        self._setup_pidevice()

    def _setup_pidevice(self):
        CONTROLLERNAME = 'E-709'
        STAGES = [None]
        REFMODES = [None]
        self.pidevice = GCSDevice(CONTROLLERNAME)
        self.pidevice.ConnectUSB(serialnum='0125033134')  # Update serialnum if needed
        # self.pidevice.InterfaceSetupDlg() # use if serialnum doesn't work
        print('connected: {}'.format(self.pidevice.qIDN().strip()))
        pitools.startup(self.pidevice, stages=STAGES, refmodes=REFMODES)



class piScanner_widget(QWidget):
    # Signals for thread-safe GUI updates
    append_text_signal = pyqtSignal(str)
    set_position_signal = pyqtSignal(str)
    set_setpoint_signal = pyqtSignal(str)
    set_stage_position_signal = pyqtSignal(str)
    set_target_x_signal = pyqtSignal(str)
    set_target_y_signal = pyqtSignal(str)
    trim_textbox_signal = pyqtSignal()  # <-- Add this signal

    # piScanner object needs to be created first to connect to PI device
    def __init__(self, piScanner, stage_instance=None, parent=None):
        super().__init__(parent)
        self.piScanner = piScanner
        self.rangemin = self.piScanner.RANGE_MIN
        self.rangemax = self.piScanner.RANGE_MAX
        self.setWindowTitle("PI objective scanner/focus controller")
        self.layout = QVBoxLayout(self)
        self._setup_ui()
        self._setup_daq()
        if stage_instance is not None:
            self.stage = stage_instance
        else:
            from instruments.hld117 import stage
            from experiment.defaults import STAGE_DEF_COM_PORT
            self.stage = stage(model='HLD117')
            self.stage.connect(STAGE_DEF_COM_PORT)
            self.stage.identify()

        # Connect signals to slots for thread-safe GUI updates
        self.append_text_signal.connect(self._append_textbox)
        self.set_position_signal.connect(self.position_textbox.setText)
        self.set_setpoint_signal.connect(self.setpoint_textbox.setText)
        self.set_stage_position_signal.connect(self.stage_position_textbox.setText)
        self.set_target_x_signal.connect(self.target_x_textbox.setText)
        self.set_target_y_signal.connect(self.target_y_textbox.setText)

        # Initialize the scanner position text box
        self._show_initial_position()

        #Initialize the stage position text box
        self.acquire_stage_position()

        # Acquire and display initial stage position
        # Set initial value if piScanner.target_x and piScanner.target_y is not None
        if self.piScanner.target_x is not None and self.piScanner.target_y is not None:
            self.target_x_textbox.setText(str(self.piScanner.target_x))
            self.target_y_textbox.setText(str(self.piScanner.target_y))
        else:
            try:
                pos = self.stage.get_position()  # Should return (x, y)
                self.stage_position_textbox.setText(f"{pos[0]:.2f}, {pos[1]:.2f}")
                self.target_x_textbox.setText(f"{pos[0]:.2f}")
                self.target_y_textbox.setText(f"{pos[1]:.2f}")
            except Exception as e:
                self.stage_position_textbox.setText(f"Error: {e}")

    def _setup_ui(self):
        # --- PI E-709 (pidevice) Controls ---
        pidevice_layout = QVBoxLayout()

        # Signal output
        self.textbox = QTextEdit(self)
        self.textbox.setReadOnly(True)
        pidevice_layout.addWidget(QLabel("Signal Output"))
        pidevice_layout.addWidget(self.textbox)

        # Current position display
        pidevice_layout.addWidget(QLabel("Current Position (um)"))
        self.position_textbox = QLineEdit(self)
        self.position_textbox.setReadOnly(True)
        self.position_textbox.setPlaceholderText("Current position will be displayed here...")
        self.position_textbox.setMaximumWidth(100)
        pidevice_layout.addWidget(self.position_textbox)

        # Setpoint input
        pidevice_layout.addWidget(QLabel("Setpoint (um)"))
        self.setpoint_textbox = QLineEdit(self)
        self.setpoint_textbox.setPlaceholderText("Enter position to move to...")
        self.setpoint_textbox.setMaximumWidth(100)
        pidevice_layout.addWidget(self.setpoint_textbox)


        # Note about range limits
        pidevice_layout.addWidget(QLabel(f"Note: range_min is {self.piScanner.RANGE_MIN} and range_max is {self.piScanner.RANGE_MAX} (micrometers)"))

        # Autofocus parameter text boxes
        autofocus_param_layout = QHBoxLayout()
        autofocus_param_layout.addWidget(QLabel("AF Min"))
        self.autofocus_range_min = QLineEdit(self)
        self.autofocus_range_min.setText(str(self.piScanner.af_min))
        self.autofocus_range_min.setMaximumWidth(60)
        autofocus_param_layout.addWidget(self.autofocus_range_min)
        self.autofocus_range_min.textChanged.connect(self._update_autofocus_range_min)

        autofocus_param_layout.addWidget(QLabel("AF Max"))
        self.autofocus_range_max = QLineEdit(self)
        self.autofocus_range_max.setText(str(self.piScanner.af_max))
        self.autofocus_range_max.setMaximumWidth(60)
        autofocus_param_layout.addWidget(self.autofocus_range_max)
        self.autofocus_range_max.textChanged.connect(self._update_autofocus_range_max)

        autofocus_param_layout.addWidget(QLabel("AF Step"))
        self.autofocus_step = QLineEdit(self)
        self.autofocus_step.setText(str(self.piScanner.af_step))
        self.autofocus_step.setMaximumWidth(60)
        autofocus_param_layout.addWidget(self.autofocus_step)
        self.autofocus_step.textChanged.connect(self._update_autofocus_step)
        pidevice_layout.addLayout(autofocus_param_layout)

        # PI E-709 Buttons
        pidevice_button_layout = QHBoxLayout()
        self.button = QPushButton("Acquire Signal", self)
        self.button.clicked.connect(self.acquire_data)
        pidevice_button_layout.addWidget(self.button)

        self.move_button = QPushButton("Move To", self)
        self.move_button.clicked.connect(self.move_to_position)
        pidevice_button_layout.addWidget(self.move_button)

        self.acquire_pos_button = QPushButton("Acquire Position", self)
        self.acquire_pos_button.clicked.connect(self.acquire_position)
        pidevice_button_layout.addWidget(self.acquire_pos_button)

        self.autofocus_button = QPushButton("Autofocus", self)
        self.autofocus_button.clicked.connect(self.autofocus)
        pidevice_button_layout.addWidget(self.autofocus_button)

        pidevice_layout.addLayout(pidevice_button_layout)
        self.layout.addLayout(pidevice_layout)

        # --- Stage Controls (bottom) ---
        stage_layout = QVBoxLayout()

        stage_layout.addWidget(QLabel("Stage Current Position (X, Y), mm"))
        self.stage_position_textbox = QLineEdit(self)
        self.stage_position_textbox.setReadOnly(True)
        self.stage_position_textbox.setPlaceholderText("X, Y coordinates")
        self.stage_position_textbox.setMaximumWidth(180)
        stage_layout.addWidget(self.stage_position_textbox)

        # Target position inputs
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target Position X (mm):"))
        self.target_x_textbox = QLineEdit(self)
        self.target_x_textbox.setPlaceholderText("X")
        self.target_x_textbox.setMaximumWidth(80)
        target_layout.addWidget(self.target_x_textbox)
        self.target_x_textbox.textChanged.connect(self._update_target_x)

        target_layout.addWidget(QLabel("Target Position Y (mm):"))
        self.target_y_textbox = QLineEdit(self)
        self.target_y_textbox.setPlaceholderText("Y")
        self.target_y_textbox.setMaximumWidth(80)
        target_layout.addWidget(self.target_y_textbox)
        stage_layout.addLayout(target_layout)
        self.target_y_textbox.textChanged.connect(self._update_target_y)

        # Stage Buttons
        stage_button_layout = QHBoxLayout()
        self.acquire_stage_pos_button = QPushButton("Acquire Current Position", self)
        self.acquire_stage_pos_button.clicked.connect(self.acquire_stage_position)
        stage_button_layout.addWidget(self.acquire_stage_pos_button)

        self.move_stage_button = QPushButton("Move To Target Position", self)
        self.move_stage_button.clicked.connect(self.move_stage_to_target)
        stage_button_layout.addWidget(self.move_stage_button)

        stage_layout.addLayout(stage_button_layout)
        self.layout.addLayout(stage_layout)

        # --- Autofocus on Imaging Checkbox  ---
        self.autofocus_on_imaging_checkbox = QCheckBox("Autofocus on Imaging", self)
        self.autofocus_on_imaging_checkbox.setChecked(self.piScanner.autofocus_on_imaging)
        self.layout.addWidget(self.autofocus_on_imaging_checkbox)
        self.autofocus_on_imaging_checkbox.stateChanged.connect(self._update_autofocus_on_imaging)

    def _setup_daq(self):
        channels = [PCI_CH_X, PCI_CH_Y]
        self.daq = MultiChannelAnalogInput(channels)
        self.sample_number = 10
        self.sample_rate = 10000
        self.daq.configure(self.sample_number, self.sample_rate)

    def _show_initial_position(self):
        self.acquire_position()
        try:
            currPos = self.piScanner.pidevice.qPOS(1)
            self.setpoint_textbox.setText(f"{currPos[1]}")
        except Exception:
            self.setpoint_textbox.setText("Error displaying position")


    def _update_target_x(self, text):
        try:
            self.piScanner.target_x = float(text)
        except ValueError:
            self.piScanner.target_x = None

    def _update_target_y(self, text):
        try:
            self.piScanner.target_y = float(text)
        except ValueError:
            self.piScanner.target_y = None

    def _update_autofocus_range_min(self, text):
        try:
            self.piScanner.af_min = float(text)
        except ValueError:
            self.piScanner.af_min = None

    def _update_autofocus_range_max(self, text):
        try:
            self.piScanner.af_max = float(text)
        except ValueError:
            self.piScanner.af_max = None

    def _update_autofocus_step(self, text):
        try:
            self.piScanner.af_step = float(text)
        except ValueError:
            self.piScanner.af_step = None

    def _update_autofocus_on_imaging(self, state):
        """Update the autofocus_on_imaging variable in piScanner when the checkbox state changes."""
        self.piScanner.autofocus_on_imaging = bool(state)


    def acquire_data(self, silent=False):
        if not silent:
            self.append_text_signal.emit("Acquiring data...")
        # Acquire real data from the DAQ
        data = self.daq.acquire(self.sample_number)
        channel1 = np.array(data[0])
        channel2 = np.array(data[1])
        result = np.sqrt(channel1**2 + channel2**2)
        mean_result = np.mean(result)
        if not silent:
            self.append_text_signal.emit(f"Mean: {mean_result}\n")
        return mean_result

    def move_to_position(self):
        # Get the position from the setpoint_textbox
        position_text = self.setpoint_textbox.text().strip()
        if not position_text:
            self.set_setpoint_signal.emit("Please enter a position value.")
            return
        try:
            position = float(position_text)
        except ValueError:
            self.set_setpoint_signal.emit("Invalid position value.")
            return

        # Limit the valid position to within rangemin and rangemax
        if not (self.rangemin <= position <= self.rangemax):
            self.set_setpoint_signal.emit(
                f"Position out of range! Must be between {self.rangemin} and {self.rangemax}."
            )
            return

        # Move the PI E-709 piezo controller to the specified position and display current position
        try:
            self.piScanner.pidevice.MOV(1, position)
            pitools.waitontarget(self.piScanner.pidevice, axes=1)
            currPos = self.piScanner.pidevice.qPOS(1)
            self.set_position_signal.emit(f"{currPos[1]}")
            self.acquire_data()  # Acquire data after moving
            return position
        except Exception as e:
            self.set_position_signal.emit(f"Move failed: {e}")

    def acquire_position(self):
        # Acquire and display the current position of the PI E-709 device
        try:
            currPos = self.piScanner.pidevice.qPOS(1)
            self.set_position_signal.emit(f"{currPos[1]}")
            return currPos[1]
        except Exception as e:
            self.set_position_signal.emit(f"Acquire position failed: {e}")

    def autofocus(self):
        self.append_text_signal.emit("autofocus in progress...")

        # Save original stage position before moving
        try:
            original_stage_pos = self.stage.get_position()  # (x, y)
        except Exception as e:
            self.append_text_signal.emit(f"Could not get original stage position: {e}")
            return


        # Move stage to target position at the beginning
        try:
            target_x = float(self.target_x_textbox.text())
            target_y = float(self.target_y_textbox.text())
            self.stage.goto(target_x, target_y)
            self.stage.wait_until_ready(timeout=10)  # Wait for the stage to finish moving
            self.acquire_stage_position()
        except Exception as e:
            self.append_text_signal.emit(f"Could not move stage to target position: {e}")
            return

        # Save original piezo position (for autofocus sweep)
        try:
            currPos = self.piScanner.pidevice.qPOS(1)
            original_piezo_position = float(currPos[1])
        except Exception as e:
            self.append_text_signal.emit(f"Could not get current piezo position: {e}")
            return

        try:
            range_min = float(self.autofocus_range_min.text())
            range_max = float(self.autofocus_range_max.text())
            step = float(self.autofocus_step.text())
        except ValueError:
            self.append_text_signal.emit("Invalid autofocus range or step size.")
            return

        # Display autofocus range and stage coordinates
        min_pos = original_piezo_position + range_min
        max_pos = original_piezo_position + range_max
        self.append_text_signal.emit(
            f"Autofocus range: {min_pos:.2f} to {max_pos:.2f} (step {step})"
        )
        self.append_text_signal.emit(
            f"Autofocus performed at stage position: X={target_x:.2f}, Y={target_y:.2f}"
        )

        # Generate positions centered at current piezo position
        positions = np.arange(min_pos, max_pos + step, step)
        results = []

        for pos in positions:
            # Limit the valid position to within rangemin and rangemax
            if not (self.rangemin <= pos <= self.rangemax):
                self.append_text_signal.emit(f"Skipped position {pos:.2f} (out of range)")
                continue
            try:
                self.piScanner.pidevice.MOV(1, pos)
                pitools.waitontarget(self.piScanner.pidevice, axes=1)
                currPos = self.piScanner.pidevice.qPOS(1)
                self.set_position_signal.emit(f"Current position: {currPos[1]}")
                mean_result = self.acquire_data(silent=True)  # Silence output
                results.append((pos, mean_result))
                self.append_text_signal.emit(f"Position {pos:.2f}: Mean = {mean_result:.4f}")
            except Exception as e:
                self.append_text_signal.emit(f"Move/acquire failed at {pos:.2f}: {e}")

        if results:
            # Find position with maximum mean_result
            best_pos, best_mean = max(results, key=lambda x: x[1])
            self.append_text_signal.emit(f"Autofocus best position: {best_pos:.2f} (Mean = {best_mean:.4f})")
            print(f"Autofocus best position: {best_pos:.2f} (Mean = {best_mean:.4f})")
            try:
                self.piScanner.pidevice.MOV(1, best_pos)
                pitools.waitontarget(self.piScanner.pidevice, axes=1)
                currPos = self.piScanner.pidevice.qPOS(1)
                self.set_position_signal.emit(f"{currPos[1]}")
                self.set_setpoint_signal.emit(f"{currPos[1]}")
            except Exception as e:
                self.append_text_signal.emit(f"Failed to move to best position: {e}")
        else:
            self.append_text_signal.emit("Autofocus found no valid positions.")


        # Move stage back to original position at the end
        try:
            self.stage.goto(original_stage_pos[0], original_stage_pos[1])
            self.stage.wait_until_ready(timeout=10)  # Wait for the stage to finish moving
            self.acquire_stage_position()
        except Exception as e:
            self.append_text_signal.emit(f"Failed to return stage to original position: {e}")

        # Finally, acquire the current stage position
        self.acquire_stage_position()
        print("autofocus finished. ")
        self.trim_textbox_signal.emit()  # <-- Use signal instead of direct call

    def acquire_stage_position(self):
        """Acquire and display the current stage X, Y position."""
        try:
            pos = self.stage.get_position()  # Should return (x, y)
            self.set_stage_position_signal.emit(f"{pos[0]:.2f}, {pos[1]:.2f}")
        except Exception as e:
            self.set_stage_position_signal.emit(f"Error: {e}")

    def move_stage_to_target(self):
        """Move stage to the target X, Y position."""
        try:
            x = float(self.target_x_textbox.text())
            y = float(self.target_y_textbox.text())
            self.stage.goto(x, y)
            self.stage.wait_until_ready(timeout=10)  # Wait for the stage to finish moving
            self.acquire_stage_position()
        except Exception as e:
            self.set_stage_position_signal.emit(f"Move failed: {e}")

    def trim_textbox(self):
        """Trim the textbox, limiting to the last 100 lines."""
        current_text = self.textbox.toPlainText()
        lines = current_text.split('\n')
        if len(lines) > 100:
            lines = lines[-100:]
        self.textbox.setPlainText('\n'.join(lines))
        self.textbox.moveCursor(QTextCursor.MoveOperation.End)

    # Replace all direct textbox.append calls with this slot
    def _append_textbox(self, text):
        current_text = self.textbox.toPlainText()
        lines = current_text.split('\n')
        lines.append(text)
        if len(lines) > 100:
            lines = lines[-100:]
        self.textbox.setPlainText('\n'.join(lines))
        self.textbox.moveCursor(QTextCursor.MoveOperation.End)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    scanner = piScanner()
    widget = piScanner_widget(scanner)
    widget.show()
    sys.exit(app.exec())