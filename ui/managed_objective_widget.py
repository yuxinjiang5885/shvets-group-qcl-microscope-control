"""Lazy experimental Objective adapter; hardware imports occur only on live open."""
import numpy as np
from types import FunctionType
from PyQt6.QtCore import QThread, QTimer, pyqtSlot
from PyQt6.QtWidgets import QPushButton

from ui.localization_orchestration import Activity, OwnershipError
from ui.objective_daq_lifecycle import ObjectiveDaqLifecycle


class _HardwareView:
    def __init__(self, raw, owner):
        self._raw, self._owner = raw, owner

    def __getattr__(self, name):
        self._owner.check_execution()
        value = self._owner.hardware_call(getattr, self._raw, name)
        if callable(value):
            if name == 'wait_until_ready':
                def wait(*args, **kwargs):
                    result = value(*args, **kwargs)
                    # The legacy stage wait prints on timeout and returns None.
                    # Its return is not proof of idle; require fresh acknowledgement.
                    busy = self._raw.busy()
                    if type(busy) not in (str, int) or str(busy) != '0':
                        raise OwnershipError('objective_stage_idle_unconfirmed')
                    return result
                return lambda *a, **k: self._owner.hardware_call(wait, *a, **k)
            return lambda *a, **k: self._owner.hardware_call(value, *a, **k)
        return value


class _ScannerView:
    def __init__(self, scanner, owner):
        object.__setattr__(self, '_scanner', scanner)
        object.__setattr__(self, 'pidevice', _HardwareView(scanner.pidevice, owner))

    def __getattr__(self, name):
        return getattr(self._scanner, name)

    def __setattr__(self, name, value):
        setattr(self._scanner, name, value)


def managed_objective_class(base_class):
    """Overrides exist before the inherited constructor connects its Qt signals."""
    class ManagedObjectiveWidget(base_class):
        def __init__(self, scanner, stage, owner):
            self.objective_owner = owner
            owner.widget = self
            scanner_view = _ScannerView(scanner, owner)
            stage_view = _HardwareView(stage, owner)
            owner.run('initialize', lambda: super(ManagedObjectiveWidget, self).__init__(
                scanner_view, stage_instance=stage_view))
            self.cancel_snake_button = QPushButton('Cancel Snake workflow', self)
            self.cancel_snake_button.clicked.connect(self.cancel_snake)
            self.layout.addWidget(self.cancel_snake_button)
            self.ownership_timer = QTimer(self)
            self.ownership_timer.setInterval(200)
            self.ownership_timer.timeout.connect(self.refresh_ownership)
            self.ownership_timer.start()  # Cached state only; never polls hardware.
            self.refresh_ownership()

        def _setup_daq(self):
            # The legacy constructor calls this virtual method before any reads.
            self.sample_number, self.sample_rate = 10, 10000
            self.daq = None

        def _legacy_motion(self, name):
            # Preserve the legacy algorithm, but observe errors from PI's wait
            # helper even when the legacy callback catches them internally.
            function = getattr(base_class, name)
            namespace = dict(function.__globals__)
            if 'pitools' in namespace:
                namespace['pitools'] = _HardwareView(namespace['pitools'], self.objective_owner)
            private = FunctionType(function.__code__, namespace, function.__name__,
                                   function.__defaults__, function.__closure__)
            private.__kwdefaults__ = function.__kwdefaults__
            return private(self)

        def _invoke(self, operation, callback, *, nested=False):
            owner = self.objective_owner
            # V1 does not run GUI autofocus from Snake/Repeat worker threads.
            if QThread.currentThread() != self.thread():
                raise OwnershipError('worker_origin_objective_unsupported_in_V1')
            if nested and owner.executing_here():
                owner.check_execution()
                return callback()
            try:
                return owner.run(operation, callback)
            except Exception as error:
                # This is the Qt UI boundary. The lifecycle has already retained
                # failures and attempted cleanup; errors are reported, never retried.
                self.append_text_signal.emit('Objective not completed: ' + str(error))
                owner.bridge.window.auto_relocation.failures_label.setText(
                    'Objective not completed: ' + str(error))
                return False
            finally:
                self.refresh_ownership()

        def acquire_data(self, silent=False):
            def acquire():
                data = self.objective_owner.acquire_data()
                result = float(np.mean(np.sqrt(np.asarray(data[0])**2 + np.asarray(data[1])**2)))
                if not silent:
                    self.append_text_signal.emit(f'Mean: {result}\n')
                return result
            return self._invoke('acquire_signal', acquire, nested=True)

        def move_to_position(self):
            return self._invoke('move_to', lambda: self._legacy_motion('move_to_position'))

        def autofocus(self):
            return self._invoke('autofocus', lambda: self._legacy_motion('autofocus'))

        def acquire_position(self):
            return self._invoke('acquire_position', super().acquire_position, nested=True)

        def acquire_stage_position(self):
            return self._invoke('acquire_stage_position', super().acquire_stage_position, nested=True)

        def move_stage_to_target(self):
            return self._invoke('move_stage_to_target', super().move_stage_to_target)

        def _update_autofocus_on_imaging(self, state):
            if state:
                try:
                    self.objective_owner.bridge.check_objective_admission(self.objective_owner)
                    self.snake_autofocus_settings()
                except Exception as error:
                    self.autofocus_on_imaging_checkbox.setChecked(False)
                    self.append_text_signal.emit('Autofocus on Imaging unavailable: '+str(error))
                    return
            self.piScanner.autofocus_on_imaging = bool(state)

        def snake_autofocus_settings(self):
            from ui.snake_autofocus_service import SnakeAutofocusSettings
            if QThread.currentThread() != self.thread():
                raise OwnershipError('settings_snapshot_requires_GUI_thread')
            return SnakeAutofocusSettings(float(self.target_x_textbox.text()),
                float(self.target_y_textbox.text()), float(self.autofocus_range_min.text()),
                float(self.autofocus_range_max.text()), float(self.autofocus_step.text()),
                self.rangemin, self.rangemax)

        def cancel_snake(self):
            parent = self.objective_owner.bridge.snake_parent
            if parent is not None: parent.request_cancellation()

        @pyqtSlot(object)
        def receive_snake_autofocus_telemetry(self, event):
            """GUI-only display; never ownership evidence or a hardware action."""
            from ui.snake_workflow import SnakeAutofocusTelemetry
            try:
                bridge = self.objective_owner.bridge
                if (QThread.currentThread() != self.thread()
                        or not isinstance(event, SnakeAutofocusTelemetry)
                        or getattr(bridge.window, 'pi_scanner_widget', None) is not self
                        or not bridge.managed_objective(self)):
                    return
                parent = bridge.snake_parent or getattr(bridge, 'last_snake_parent', None)
                if (parent is None or parent.token != event.parent_token
                        or parent.generation != event.parent_generation):
                    return
                current = self.objective_owner.current
                if (current is not None and current.generation > event.child_generation
                        and current.operation != 'snake_autofocus'):
                    return
                # One worker's queued signals retain order across wavelengths.
                # Last completed parent accepts trailing events until a newer run
                # or manual operation supersedes it. Hidden widgets remain valid.
                units = {'invcm': 'cm^-1', 'um': 'µm'}.get(event.units, event.units)
                context = f'requested wavelength {event.requested_wavelength} {units}'
                if event.qcl is not None: context += f' | QCL {event.qcl}'
                if event.kind == 'start':
                    text = f'Snake autofocus start | {context}'
                elif event.kind == 'point' and event.point is not None:
                    text = (f'Snake autofocus | {context} | PI {event.point.position:g} µm'
                            f' | Signal {event.point.signal:.6g} V')
                elif event.kind == 'result' and event.result is not None:
                    result = event.result
                    if (result.outcome == 'SUCCESS' and result.cleanup_verified
                            and result.stage_restored and result.pi_verified):
                        text = (f'Snake autofocus complete | {context}'
                                f' | Best PI {result.best_position:g} µm'
                                f' | Best signal {result.best_signal:.6g} V')
                    else:
                        text = f'Snake autofocus failed | {context} | {result.outcome}: {result.detail}'
                else:
                    return
                self.append_text_signal.emit(text)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Snake autofocus display failed')

        def refresh_ownership(self):
            owner = self.objective_owner
            with owner.bridge.controller.registration.lock:
                try:
                    owner.bridge.check_objective_admission(owner)
                    enabled = True
                except OwnershipError:
                    enabled = False
            for name in ('button', 'move_button', 'acquire_pos_button', 'autofocus_button',
                         'acquire_stage_pos_button', 'move_stage_button'):
                getattr(self, name).setEnabled(enabled)
            try:
                self.snake_autofocus_settings()
                valid = True
            except (ValueError, RuntimeError): valid = False
            self.autofocus_on_imaging_checkbox.setEnabled(enabled and valid)
            parent = owner.bridge.snake_parent
            self.cancel_snake_button.setEnabled(parent is not None and parent.worker_active)
            trace_parent = parent or owner.bridge.last_snake_parent
            if trace_parent is not None:
                state = (trace_parent.token, enabled, self.cancel_snake_button.isEnabled())
                if getattr(self, '_snake_controls_trace', None) != state:
                    self._snake_controls_trace = state
                    trace_parent.trace('controls_refresh', hardware_enabled=enabled, cancel_enabled=state[2])

        def closeEvent(self, event):
            if not self.objective_owner.released():
                event.ignore()
                return
            super().closeEvent(event)  # Hide/reuse; no task exists when RELEASED.

    return ManagedObjectiveWidget


def create_managed_objective(window, *, base_class=None, backend=None):
    bridge = window.localization_bridge
    if QThread.currentThread() != window.thread():
        raise OwnershipError('worker_origin_objective_unsupported_in_V1')
    if base_class is None:
        from instruments.pi_scanner import piScanner_widget
        base_class = piScanner_widget
    owner = ObjectiveDaqLifecycle(bridge, backend)
    try:
        return managed_objective_class(base_class)(window.pi_scanner, window.stage, owner)
    except BaseException as error:
        # Keep the owner registered after partial construction; never lose evidence.
        with bridge.controller.registration.lock:
            if owner.current is None:
                bridge.objective_owner = None  # Admission denied before any hardware access.
            else:
                owner.fail(error)
                owner.state = 'UNCERTAIN'
                bridge.controller.report_activity(Activity.OBJECTIVE_DAQ, True)
        raise
