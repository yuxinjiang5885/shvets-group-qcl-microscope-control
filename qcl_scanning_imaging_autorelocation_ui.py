"""Experimental UI entry point. Default is hardware-independent registration only.

--hardware explicitly opts into ALL existing mainWindow startup side effects:
MIRcat/Prior/PI connections and stage speed/acceleration/joystick configuration.
The old module is never imported by the default/offline path. The hardware window
offers an explicitly confirmed, isolated H-only development scan. Full live
Locate Marker and target motion remain disabled.
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


class OfflineAutoRelocationWindow(QMainWindow):
    """Safe standalone panel host; does not simulate operational instrument controls."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Auto Relocation — OFFLINE ONLY')
        self.resize(1400, 1000)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.auto_relocation = AutoRelocationWidget()
        self.auto_location_scroll=auto_location_scroll(self.auto_relocation)
        self.tabs.addTab(self.auto_location_scroll, 'Auto Relocation')


def operational_window_class(base_class=None, *, owner_factory=None):
    """Lazy subclass, with an injectable inert base for offline contract tests.

    Do not call without a fake base during offline validation: importing the
    legacy module loads vendor libraries, and its constructor starts hardware.
    Experimental overrides guard callbacks and defer close while leased.
    The real experimental path injects one persistent-owner proxy before inherited
    startup. H-only owns a separately configured DAQ task; Locate Marker stays disabled.
    """
    use_owner = base_class is None or owner_factory is not None
    if base_class is None:
        from qcl_scanning_imaging_ui import mainWindow
        base_class = mainWindow

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
            self.prior_owner = owner
            self.auto_relocation = AutoRelocationWidget()
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
            self.h_only_runner = None
            if owner is not None:
                from ui.h_only_controls import HOnlyRunner, HOnlyControls
                self.h_only_runner = HOnlyRunner(self)
                self.h_only_controls = HOnlyControls(self)
                self.auto_relocation.layout().addWidget(self.h_only_controls)
            self.localization_display_timer = QTimer(self)
            self.localization_display_timer.setInterval(200)
            self.localization_display_timer.timeout.connect(self.auto_relocation.refresh)
            self.localization_display_timer.start()  # Cached Python state only; no instrument polling.

        def closeEvent(self, event):
            bridge = getattr(self, 'localization_bridge', None)
            runner = getattr(self, 'h_only_runner', None)
            if runner is not None and runner.busy:
                bridge.request_close()
                event.ignore()
                return
            if bridge is not None and not bridge.request_close():
                event.ignore()
                self.auto_relocation.refresh()
                return
            if bridge is not None:
                active = [r for r in bridge.blockers() if r.startswith(('legacy_activity:',
                          'legacy_thread_state_unknown:', 'legacy_callback_active'))]
                if active:
                    event.ignore()
                    return
            try:
                super().closeEvent(event)  # Stops gamepad; proxy disconnect owns cleanup.
                if self.prior_owner is not None and event.isAccepted():
                    if not self.prior_owner.shutdown():
                        event.ignore()
                if bridge is not None and event.isAccepted() and not bridge.dispatcher.shutdown():
                    event.ignore()
            except Exception as error:
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
                        # Legacy cleanup has no checked release attestation.
                        # Completion alone cannot prove that its DAQ task is gone.
                        bridge.legacy_daq_cleanup_unverified = True
                    return callback(*args,**kwargs)
                return bridge.dispatch(command, authorized_callback)
            except OwnershipError as error:
                self.auto_relocation.failures_label.setText('Command blocked: ' + str(error))
                return False
        return guarded

    for name, command in MAIN_COMMANDS.items():
        if hasattr(base_class, name):
            setattr(AutoRelocationMainWindow, name, wrap(name, command))

    return AutoRelocationMainWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--offline', action='store_true', help='Default: registration-only, no vendor imports')
    modes.add_argument('--hardware', action='store_true', help='Start the original hardware UI plus the offline registration tab')
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    window = operational_window_class()() if args.hardware else OfflineAutoRelocationWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
