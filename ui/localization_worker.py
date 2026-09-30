"""Thin optional Qt event adapter. No QThread or hardware is started on import.

The owner may move this QObject to a QThread and connect started to run. Keep
both alive until finished. Cancellation calls the core Event/controller directly,
not a queued worker slot. Window-close/ownership policy remains in the core.
"""
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class LocateMarkerQtWorker(QObject):
    started = pyqtSignal(object)
    progress = pyqtSignal(object)
    phase_changed = pyqtSignal(object)
    warning = pyqtSignal(object)
    failed = pyqtSignal(object)
    cancelled = pyqtSignal(object)
    registration_completed = pyqtSignal(object)
    finished = pyqtSignal(object)

    def __init__(self, core_worker):
        super().__init__()
        self.core_worker = core_worker

    @pyqtSlot()
    def run(self):
        self.core_worker.run(lambda event: getattr(self, event.name).emit(event))
