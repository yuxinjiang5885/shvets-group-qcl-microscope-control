"""Explicit supervised H-only action. Construction performs no device calls."""
from pathlib import Path
from dataclasses import asdict
import json
from PyQt6.QtCore import QObject,QThread,Qt,pyqtSlot,QTimer
from PyQt6.QtWidgets import QWidget,QFormLayout,QLineEdit,QCheckBox,QPushButton,QLabel,QVBoxLayout
from experiment.scan_1d import StageBounds
from ui.h_only_validation import HOnlySpec,OperatorConfirmation,InputHandoff,HOnlyServices
from ui.localization_daq import LocalizationDAQProvider
from ui.localization_orchestration import RunSettings,LocateMarkerWorker,CleanupOutcome,OwnershipError
from ui.localization_worker import LocateMarkerQtWorker


class HOnlyRunner(QObject):
    def __init__(self,window,*,backend=None,services_type=HOnlyServices):
        super().__init__(window)
        self.window,self.bridge=window,window.localization_bridge
        self.backend,self.services_type=backend,services_type
        self.thread=None;self.worker=None;self.services=None;self.starting=False

    @property
    def busy(self):return self.starting or self.thread is not None

    def start(self,spec,confirmation,output_dir):
        if self.busy:raise OwnershipError('H_run_already_active')
        self.starting=True
        controller=self.bridge.controller
        context=controller.registration.context
        generation=controller.registration.context_generation
        handle=None
        try:
            confirmation.validate(context,self.window.laser)
            spec.scan().positions()
            if spec.bounds.frame_id!=context.frame_id:raise ValueError('frame_mismatch')
            Path(output_dir).mkdir(parents=True,exist_ok=True)
            handoff=InputHandoff(self.bridge);handoff.prepare()
            handle=self.bridge.acquire(RunSettings(context,generation,repr(spec.rough_start_xy),purpose='h_only'))
            provider=LocalizationDAQProvider(self.bridge,handle,self.backend)
            self.services=self.services_type(self.bridge,handle,spec,output_dir,provider,
                confirmation=confirmation,handoff=handoff)
            self.thread=QThread(self)
            self.worker=LocateMarkerQtWorker(LocateMarkerWorker(controller,handle,self.services))
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            for name in ('started','progress','phase_changed','profile_completed','warning','failed','cancelled','finished'):
                getattr(self.worker,name).connect(self.window.auto_relocation.consume_localization_event)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.finished.connect(self.thread.quit,Qt.ConnectionType.DirectConnection)
            self.thread.finished.connect(self._finished)
            self.window.h_only_controls.set_busy(True)
            self.window.auto_relocation.refresh()
            self.thread.start()
            return handle
        except Exception:
            if self.thread is not None and self.thread.isRunning():
                controller.request_cancel(handle)
            elif handle is not None:
                controller.finish(handle,succeeded=False,cleanup=CleanupOutcome(False,False),reasons=('H_worker_start_failed',))
                if self.worker is not None:self.worker.deleteLater()
                if self.thread is not None:self.thread.deleteLater()
                self.worker=None;self.thread=None
                self.window.h_only_controls.set_busy(False)
            raise
        finally:self.starting=False

    @pyqtSlot()
    def _finished(self):
        thread=self.thread
        self.thread=None;self.worker=None
        if thread is not None:thread.deleteLater()
        report=dict(self.services.report)
        snapshot=self.bridge.controller.snapshot()
        report.update(final_state=snapshot['acquisition'],ownership=snapshot['ownership'],
            cleanup_status='PASS' if snapshot['ownership']=='AVAILABLE' else 'UNCONFIRMED',
            reasons=snapshot['reasons'],handoff=self.services.handoff.result,
            restore=self.services.handoff.restore_result,registration_published=False)
        try:
            if self.services.path.exists():
                (self.services.path/'h_only_result.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
        except Exception as error:
            report['report_write_error']=str(error)
        self.window.auto_relocation.run_display.update(h_only_result=report)
        self.window.h_only_controls.set_busy(False)
        self.window.auto_relocation.refresh()
        if self.bridge.close_pending:QTimer.singleShot(0,self.window.continue_localization_close)


class HOnlyControls(QWidget):
    def __init__(self,window):
        super().__init__(window.auto_relocation)
        self.window=window
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('SUPERVISED DEVELOPMENT: one H scan only; no registration publication.'))
        form=QFormLayout();self.fields={}
        for key,label,value in (('x','Confirmed rough X (um)',''),('y','Confirmed rough Y (um)',''),
            ('xmin','Clearance bounds X min',''),('xmax','Clearance bounds X max',''),
            ('ymin','Clearance bounds Y min',''),('ymax','Clearance bounds Y max',''),
            ('margin','Scan margin (um)','100'),('step','Step (um)','10'),
            ('wn','Operator-confirmed wavenumber (cm^-1)','1500'),('note','Operator / clearance note',''),
            ('output','Journal directory',str(Path.cwd()/'localization_runs'))):
            self.fields[key]=QLineEdit(value);form.addRow(label,self.fields[key])
        layout.addLayout(form)
        self.checks=[]
        for text in ('I confirm the current XY/frame and full approach/scan/return clearance.',
            'I confirm physical emission ON at the stated wavenumber.',
            'Python is the sole MIRcat owner; vendor GUI and other DAQ users are closed.',
            'SR865A: 20 mV, 300 us, Advanced 24 dB; wiring/settings verified.'):
            check=QCheckBox(text);layout.addWidget(check);self.checks.append(check)
        self.preview_button=QPushButton('Preview H Envelope')
        self.run_button=QPushButton('Run H-Only Validation')
        self.run_button.setEnabled(False)
        self.reviewed=None
        self.cancel_button=QPushButton('Cancel H-Only / Localization')
        self.result=QLabel();self.result.setWordWrap(True)
        for w in (self.preview_button,self.run_button,self.cancel_button,self.result):layout.addWidget(w)
        self.preview_button.clicked.connect(self.preview)
        self.run_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(lambda:window.localization_bridge.controller.request_cancel())
        for field in self.fields.values():field.textChanged.connect(self.invalidate_review)

    def invalidate_review(self,*_):
        self.reviewed=None
        self.run_button.setEnabled(False)
        for check in self.checks:check.setChecked(False)

    def set_busy(self,busy):
        for widget in (*self.fields.values(),*self.checks,self.preview_button):
            widget.setEnabled(not busy)
        self.invalidate_review()

    def build(self):
        state=self.window.auto_relocation.state
        assignments=self.window.auto_relocation.selection.assignments
        if assignments is None or assignments.marker is None:raise ValueError('manually_select_square_gold_marker')
        side=assignments.build_chip_layout().marker.width
        def num(k):return float(self.fields[k].text())
        spec=HOnlySpec((num('x'),num('y')),StageBounds(num('xmin'),num('xmax'),num('ymin'),num('ymax'),state.context.frame_id),
            side_um=side,scan_margin_um=num('margin'),step_um=num('step'))
        confirmation=OperatorConfirmation(*(c.isChecked() for c in self.checks),
            wavenumber_cm=num('wn'),note=self.fields['note'].text())
        return spec,confirmation

    def preview(self):
        try:
            spec,_=self.build();scan=spec.scan()
            self.invalidate_review()
            state=self.window.auto_relocation.state
            self.reviewed=(spec,state.context,state.context_generation)
            self.run_button.setEnabled(True)
            self.result.setText(f'H only: X {scan.start_um} to {scan.end_um}, Y {scan.fixed_um}; '
                f'{len(scan.positions())} points. Return {spec.rough_start_xy}. Bounds {spec.bounds}. '
                'A rough point far from center may not capture both edges; no automatic extension/retry.')
        except Exception as error:self.result.setText(str(error))

    def start(self):
        try:
            spec,confirmation=self.build()
            state=self.window.auto_relocation.state
            if self.reviewed!=(spec,state.context,state.context_generation):
                raise ValueError('preview_current_envelope_and_context_before_confirmation')
            handle=self.window.h_only_runner.start(spec,confirmation,self.fields['output'].text())
            self.result.setText('Running H only: '+handle.run_id)
            self.invalidate_review() # Fresh preview and confirmation every attempt.
        except Exception as error:self.result.setText('Not started: '+str(error))
