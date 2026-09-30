"""Run-owned finite NI task. Native module import is deferred to explicit creation."""
from ui.localization_pipeline import DaqSettings


def checked(status, operation):
    if status is not None and status != 0:
        raise RuntimeError(f'{operation}: DAQmx status {status}')


class OwnedDAQ:
    def __init__(self, backend, settings, run_id):
        if settings != DaqSettings():
            raise ValueError('unvalidated_DAQ_settings')
        self.backend, self.settings, self.run_id = backend, settings, run_id
        self.device = backend.MultiChannelAnalogInput(
            [c.encode() for c in settings.channels], limit=settings.voltage_range, reset=False)
        self.clear_attempted = False
        self.clear_ok = False

    def configure(self):
        b, d, s = self.backend, self.device, self.settings
        checked(b.DAQmxCreateTask('', b.byref(d.taskHandle)), 'CreateTask')
        if not d.taskHandle.value:
            raise RuntimeError('DAQ task handle missing')
        for channel in s.channels:
            checked(b.DAQmxCreateAIVoltageChan(d.taskHandle, channel.encode(), '',
                b.DAQmx_Val_Cfg_Default, *s.voltage_range, b.DAQmx_Val_Volts, None), 'CreateChannel')
        checked(b.DAQmxCfgSampClkTiming(d.taskHandle, '', s.rate_hz,
            b.DAQmx_Val_Rising, b.DAQmx_Val_FiniteSamps, s.samples), 'Timing')

    def acquire_bounded(self, count, *, timeout_s):
        if self.clear_attempted or count != self.settings.samples:
            raise ValueError('invalid_owned_DAQ_read')
        return self.device.acquire_bounded(count, timeout_s=timeout_s)

    def clear(self):
        if self.clear_attempted:
            if not self.clear_ok:
                raise RuntimeError('DAQ_clear_previously_failed_no_retry')
            return
        self.clear_attempted = True
        if self.device.taskHandle.value:
            checked(self.backend.DAQmxClearTask(self.device.taskHandle), 'ClearTask')
        self.clear_ok = True


class LocalizationDAQProvider:
    def __init__(self, bridge, handle, backend=None):
        self.bridge, self.handle, self.backend = bridge, handle, backend

    def __call__(self, settings):
        self.bridge.controller.checkpoint(self.handle)
        if self.bridge.daq.run_id is not None or self.bridge.daq.uncertain:
            raise RuntimeError('DAQ_owner_conflict')
        backend = self.backend
        if backend is None:
            from instruments import ni_daq as backend
        task = OwnedDAQ(backend, settings, self.handle.run_id)
        self.bridge.claim_daq(self.handle, task, reset=False)
        try:
            task.configure()
        except BaseException:
            try:
                task.clear()
            except BaseException:
                self.bridge.release_daq(self.handle, False)
                self.bridge._quarantine_stage(self.handle, 'DAQ_partial_setup_cleanup_uncertain')
                raise
            self.bridge.release_daq(self.handle, True)
            raise
        return task
