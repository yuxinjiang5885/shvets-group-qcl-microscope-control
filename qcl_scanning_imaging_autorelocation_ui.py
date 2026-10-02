"""Experimental UI entry point. Default is hardware-independent registration only.

--hardware explicitly opts into ALL existing mainWindow startup side effects:
MIRcat/Prior/PI connections and stage speed/acceleration/joystick configuration.
The old module is never imported by the default/offline path. The hardware window
offers separately confirmed H-only and H+V development scans. Full live
Locate Marker defaults disabled; --supervised-translation-only permits a reviewed H+V test.
Target motion remains unavailable.
"""
import argparse
import sys
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PyQt6.QtCore import QTimer
from ui.auto_relocation_widget import AutoRelocationWidget, auto_location_scroll
from ui.operational_localization_bridge import OperationalLocalizationBridge, MAIN_COMMANDS
from ui.localization_orchestration import OwnershipError, Command
from ui.stage_command_dispatcher import qt_main_thread_target
from ui.persistent_prior_owner import PersistentPriorOwner, constructor_with_proxy
from ui.legacy_daq_tracking import invoke_acquisition


class OfflineAutoRelocationWindow(QMainWindow):
    """Safe standalone panel host; does not simulate operational instrument controls."""
    def __init__(self, *, developer_mode=False):
        super().__init__()
        self.setWindowTitle('Auto Relocation — OFFLINE ONLY')
        self.resize(1400, 1000)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.auto_relocation = AutoRelocationWidget(developer_mode=developer_mode)
        self.auto_location_scroll=auto_location_scroll(self.auto_relocation)
        self.tabs.addTab(self.auto_location_scroll, 'Auto Relocation')


def operational_window_class(base_class=None, *, owner_factory=None, translation_launch_enabled=False,
                             developer_mode=False, objective_widget_factory=None):
    """Lazy subclass, with an injectable inert base for offline contract tests.

    Do not call without a fake base during offline validation: importing the
    legacy module loads vendor libraries, and its constructor starts hardware.
    Experimental overrides guard callbacks and defer close while leased.
    The real experimental path injects one persistent-owner proxy before inherited
    startup. H/H+V owns a separately configured DAQ task; production H+V needs explicit opt-in.
    """
    use_owner = base_class is None or owner_factory is not None
    live_trace = base_class is None
    if base_class is None:
        from qcl_scanning_imaging_ui import mainWindow
        base_class = mainWindow
        if objective_widget_factory is None:
            from ui.managed_objective_widget import create_managed_objective
            objective_widget_factory = create_managed_objective

    class AutoRelocationMainWindow(base_class):
        def __init__(self):
            owner = None
            if use_owner:
                if 'stageInitializer' not in base_class.__init__.__code__.co_names:
                    raise RuntimeError('base_constructor_has_no_stage_initializer_injection_point')
                context = SimpleNamespace()
                namespace = base_class.__init__.__globals__
                owner = (owner_factory(context) if owner_factory else PersistentPriorOwner(context,
                    model=namespace['STAGE_MODEL'], port=namespace['STAGE_COM_PORT']))
                proxy = owner.start()
                try:
                    constructor_with_proxy(base_class, proxy)(self)
                except BaseException:
                    owner.shutdown()
                    raise
            else:
                super().__init__()  # Existing inert UI fixtures only.
            self.translation_launch_enabled = translation_launch_enabled
            self.prior_owner = owner
            self.auto_relocation = AutoRelocationWidget(developer_mode=developer_mode)
            self.auto_location_scroll=auto_location_scroll(self.auto_relocation)
            self.tabs.addTab(self.auto_location_scroll, 'Auto Location')
            if owner is not None:
                # Authorization executes in the caller; the proxy queues every
                # native call to its single persistent owner, not Qt main thread.
                self.localization_bridge = OperationalLocalizationBridge(self,
                    self.auto_relocation.orchestration, executor=lambda call, timeout: call())
                owner.on_uncertain = self.localization_bridge.owner_uncertain
            else:
                self.stage_execution_target = qt_main_thread_target()
                self.localization_bridge = OperationalLocalizationBridge(self, self.auto_relocation.orchestration,
                    submit=self.stage_execution_target.submit)
            self.localization_bridge.install_guards()
            if live_trace:
                try:
                    from pathlib import Path
                    from uuid import uuid4
                    from ui.snake_trace import SnakeTraceWriter
                    self.localization_bridge.snake_trace_writer = SnakeTraceWriter(
                        Path.cwd() / 'localization_runs' / ('snake_trace_' + uuid4().hex + '.jsonl'))
                except Exception as error:
                    self.localization_bridge.snake_trace_error = str(error)
            from ui.hardware_ownership_diagnostics import hardware_ownership_snapshot
            self.auto_relocation.hardware_diagnostics_provider = lambda: hardware_ownership_snapshot(self)
            self.h_only_runner = None
            if owner is not None:
                from ui.h_only_controls import HOnlyRunner, HOnlyControls
                self.h_only_runner = HOnlyRunner(self)
                self.h_only_controls = HOnlyControls(self)
                self.auto_relocation.layout().insertWidget(4,self.h_only_controls)
            self.auto_relocation.refresh_hardware_diagnostics()
            self.localization_display_timer = QTimer(self)
            self.localization_display_timer.setInterval(200)
            self.localization_display_timer.timeout.connect(self.auto_relocation.refresh)
            self.localization_display_timer.start()  # Cached Python state only; no instrument polling.

        def closeEvent(self, event):
            bridge = getattr(self, 'localization_bridge', None)
            runner = getattr(self, 'h_only_runner', None)
            if runner is not None and runner.busy:
                bridge.request_close()
                bridge.trace_snake('close_deferred_reason', reason='localization_runner_busy')
                event.ignore()
                return
            if bridge is not None and not bridge.request_close():
                event.ignore()
                self.auto_relocation.refresh()
                return
            parent = bridge.snake_parent if bridge is not None else None
            if parent is not None and parent.completed:
                bridge.trace_snake('shutdown_begin', path='completed_quarantine')
                # Terminal quarantine is not running acquisition. Do not invoke
                # the legacy close handler's unbounded PI/laser calls or guarded
                # stage disconnect, and do not attest release to permit exit.
                import logging
                logging.getLogger(__name__).warning('Snake shutdown: workflow=%s, uncertain=%s; see Snake breadcrumbs',
                                                   parent.workflow_outcome, parent.uncertain)
                stop = getattr(getattr(self, 'stageMotionWindow', None), 'stop_gamepad', None)
                try:
                    bridge.trace_snake('gamepad_shutdown_begin')
                    if callable(stop) and not stop():
                        bridge.trace_snake('close_deferred_reason', reason='gamepad_still_stopping')
                        event.ignore()
                        return
                    bridge.trace_snake('gamepad_shutdown_complete')
                    owner = self.prior_owner
                    if owner is not None:
                        bridge.trace_snake('prior_shutdown_begin', uncertain=owner.uncertain)
                        safe = owner.shutdown() if not owner.uncertain else False
                        if not safe:
                            bridge.trace_snake('prior_retirement_begin')
                            if not owner.retire_quarantined():
                                bridge.trace_snake('close_deferred_reason', reason='prior_native_execution_pending')
                                event.ignore()  # Native call has not returned; never terminate it.
                                return
                        bridge.trace_snake('prior_shutdown_complete', native_cleanup_verified=safe)
                except Exception as error:
                    bridge.trace_snake('close_deferred_reason', reason='shutdown_exception', error=str(error))
                    event.ignore()
                    self.auto_relocation.failures_label.setText('Shutdown unconfirmed: ' + str(error))
                    return
                bridge.dispatcher.shutdown()
                bridge.trace_snake('legacy_shutdown_skipped', reason='completed_quarantine_policy')
                self.localization_display_timer.stop()
                widget = getattr(self, 'pi_scanner_widget', None)
                if bridge.managed_objective(widget):
                    widget.ownership_timer.stop()
                    widget.hide()
                event.accept()
                bridge.trace_snake('close_accepted')
                return
            if bridge is not None:
                active = [r for r in bridge.blockers() if r.startswith(('legacy_activity:',
                          'legacy_thread_state_unknown:', 'legacy_callback_active'))]
                if active:
                    bridge.trace_snake('close_deferred_reason', reason='legacy_activity', blockers=tuple(active))
                    event.ignore()
                    return
            try:
                if bridge is not None:
                    bridge.trace_snake('shutdown_begin', path='normal')
                    bridge.trace_snake('legacy_shutdown_begin')
                super().closeEvent(event)  # Stops gamepad; proxy disconnect owns cleanup.
                if bridge is not None:
                    bridge.trace_snake('legacy_shutdown_complete', accepted=event.isAccepted())
                widget = getattr(self, 'pi_scanner_widget', None)
                if bridge is not None and event.isAccepted() and bridge.managed_objective(widget):
                    widget.close()
                if self.prior_owner is not None and event.isAccepted():
                    if not self.prior_owner.shutdown():
                        event.ignore()
                if bridge is not None and event.isAccepted() and not bridge.dispatcher.shutdown():
                    event.ignore()
                if bridge is not None:
                    bridge.trace_snake('close_accepted' if event.isAccepted() else 'close_deferred_reason',
                                       reason=None if event.isAccepted() else 'legacy_or_owner_shutdown_unconfirmed')
            except Exception as error:
                if bridge is not None:
                    bridge.trace_snake('close_deferred_reason', reason='normal_shutdown_exception', error=str(error))
                event.ignore()
                self.auto_relocation.failures_label.setText('Shutdown unconfirmed: ' + str(error))

        def continue_localization_close(self):
            return self.localization_bridge.continue_close(self.close)

        def stage_set(self, instance):
            bridge = getattr(self, 'localization_bridge', None)
            if bridge is not None:
                bridge.frame_event('session_replacement')
                raise OwnershipError('stage_session_replacement_requires_bridge_reconstruction')
            return super().stage_set(instance)

    def wrap(name, command):
        def guarded(self, *args, **kwargs):
            callback = getattr(super(AutoRelocationMainWindow, self), name)
            bridge = getattr(self, 'localization_bridge', None)
            if bridge is None:  # Original constructor/startup; no localization exists yet.
                return callback(*args, **kwargs)
            try:
                def authorized_callback():
                    if command in (Command.SPECTRUM,Command.REPEAT_SCAN,Command.MULTIWELL,
                                   Command.SNAKE_SCAN,Command.IMAGING):
                        return invoke_acquisition(callback,bridge.mark_legacy_daq_uncertain,*args,snake_bridge=bridge,**kwargs)
                    if command is Command.OBJECTIVE_MOVE:
                        # Construction itself configures NI; partial construction
                        # failure must not escape tracking via an unset attribute.
                        bridge.mark_legacy_daq_uncertain('objective_widget_creation_or_reopen')
                    return callback(*args,**kwargs)
                return bridge.dispatch(command, authorized_callback)
            except OwnershipError as error:
                self.auto_relocation.failures_label.setText('Command blocked: ' + str(error))
                return False
        return guarded

    for name, command in MAIN_COMMANDS.items():
        if hasattr(base_class, name):
            setattr(AutoRelocationMainWindow, name, wrap(name, command))

    if hasattr(base_class, 'show_pi_scanner_widget'):
        objective_guard = wrap('show_pi_scanner_widget', Command.OBJECTIVE_MOVE)

        def show_pi_scanner_widget(self):
            # Preserve Qt's zero-argument slot contract before the variadic guard.
            if objective_widget_factory is not None:
                bridge = getattr(self, 'localization_bridge', None)
                if bridge is None:
                    raise OwnershipError('managed_objective_requires_initialized_bridge')
                try:
                    widget = getattr(self, 'pi_scanner_widget', None)
                    if widget is None:
                        self.pi_scanner_widget = objective_widget_factory(self)
                        widget = self.pi_scanner_widget
                    elif not bridge.managed_objective(widget):
                        raise OwnershipError('unmanaged_objective_widget_exists')
                    # Reopening only shows cached UI, including during localization.
                    widget.refresh_ownership()
                    widget.show()
                    widget.raise_()
                    return widget
                except Exception as error:
                    self.auto_relocation.failures_label.setText('Objective not opened: ' + str(error))
                    return False
            return objective_guard(self)

        AutoRelocationMainWindow.show_pi_scanner_widget = show_pi_scanner_widget

    return AutoRelocationMainWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--offline', action='store_true', help='Default: registration-only, no vendor imports')
    modes.add_argument('--hardware', action='store_true', help='Start the original hardware UI plus the offline registration tab')
    parser.add_argument('--supervised-translation-only', action='store_true',
        help='Explicit supervised H+V Locate Marker opt-in; no target motion')
    parser.add_argument('--developer-mode', action='store_true', help='Expose alternative orientation controls')
    args = parser.parse_args(argv)
    if args.supervised_translation_only and not args.hardware:
        parser.error('--supervised-translation-only requires --hardware')
    app = QApplication.instance() or QApplication([])
    window = operational_window_class(translation_launch_enabled=args.supervised_translation_only,developer_mode=args.developer_mode)() if args.hardware else OfflineAutoRelocationWindow(developer_mode=args.developer_mode)
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
