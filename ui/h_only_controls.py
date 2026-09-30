"""Shared supervised H-only/H+V controls. Construction performs no device calls."""
from pathlib import Path
from dataclasses import asdict
import json
from math import isfinite
from PyQt6.QtCore import QObject,QThread,Qt,pyqtSlot,QTimer
from PyQt6.QtWidgets import QWidget,QFormLayout,QLineEdit,QCheckBox,QPushButton,QLabel,QVBoxLayout
from experiment.scan_1d import StageBounds
from ui.h_only_validation import HOnlySpec,OperatorConfirmation,InputHandoff,HOnlyServices
from ui.hv_validation import HVSpec, HVConfirmation, HVServices
from ui.multi_h_validation import MultiHSpec, MultiHConfirmation, MultiHServices, clearance_rectangle
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
            if isinstance(spec,MultiHSpec) and not isinstance(confirmation,MultiHConfirmation):
                raise ValueError('multi_H_requires_separate_confirmation')
            if isinstance(spec,HVSpec) and not isinstance(confirmation,HVConfirmation):
                raise ValueError('H_plus_V_requires_separate_confirmation')
            confirmation.validate(context,self.window.laser)
            spec.scan().positions()
            if spec.bounds.frame_id!=context.frame_id:raise ValueError('frame_mismatch')
            Path(output_dir).mkdir(parents=True,exist_ok=True)
            handoff=InputHandoff(self.bridge);handoff.prepare()
            purpose='multi_h' if isinstance(spec,MultiHSpec) else ('hv' if isinstance(spec,HVSpec) else 'h_only')
            handle=self.bridge.acquire(RunSettings(context,generation,repr(spec.rough_start_xy),purpose=purpose))
            provider=LocalizationDAQProvider(self.bridge,handle,self.backend)
            services_type = self.services_type
            if services_type is HOnlyServices:
                services_type = {'h_only':HOnlyServices,'hv':HVServices,'multi_h':MultiHServices}[purpose]
            self.services=services_type(self.bridge,handle,spec,output_dir,provider,
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
        report[self.services.handle.settings.purpose+'_complete'] = snapshot['acquisition']=='COMPLETE' and snapshot['ownership']=='AVAILABLE'
        try:
            if self.services.path.exists():
                (self.services.path/(self.services.handle.settings.purpose+'_result.json')).write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
        except Exception as error:
            report['report_write_error']=str(error)
        self.window.auto_relocation.run_display.update({self.services.handle.settings.purpose+'_result':report})
        self.window.h_only_controls.set_busy(False)
        self.window.auto_relocation.refresh()
        if self.bridge.close_pending:QTimer.singleShot(0,self.window.continue_localization_close)


class HOnlyControls(QWidget):
    def __init__(self,window):
        super().__init__(window.auto_relocation)
        self.window=window
        self.preview_xy=None
        self.mode='h_only'
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('SUPERVISED DEVELOPMENT: H-only / H+V / Multi-H; no registration publication.'))
        form=QFormLayout();self.fields={}
        for key,label,value in (('x','Fresh preview X (um)',''),('y','Fresh preview Y (um)',''),
            ('xmin','Clearance bounds X min',''),('xmax','Clearance bounds X max',''),
            ('ymin','Clearance bounds Y min',''),('ymax','Clearance bounds Y max',''),
            ('margin','Scan margin (um)','100'),('step','Step (um)','10'),
            ('wn','Operator-confirmed wavenumber (cm^-1)','1500'),('note','Operator / clearance note',''),
            ('output','Journal directory',str(Path.cwd()/'localization_runs'))):
            self.fields[key]=QLineEdit(value);form.addRow(label,self.fields[key])
        layout.addLayout(form)
        for key in ('x','y'):
            self.fields[key].setReadOnly(True)
            self.fields[key].setPlaceholderText('Read from stage on Preview')
        self.automatic_bounds=QCheckBox('Propose bounds from H envelope (clearance still requires operator confirmation)')
        self.automatic_bounds.setChecked(True)
        layout.addWidget(self.automatic_bounds)
        self.automatic_bounds.toggled.connect(self.bounds_mode_changed)
        self.bounds_mode_changed(True)
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
        self.hv_preview_button=QPushButton('Preview H+V Envelope')
        self.hv_run_button=QPushButton('Run H+V Validation')
        self.hv_run_button.setEnabled(False)
        self.hv_clearance=QCheckBox('H+V: I confirm movement in BOTH X and Y.\nFull 2D rectangle, approach and return clearance checked.')
        self.multi_preview_button=QPushButton('Preview Multi-H Envelope')
        self.multi_run_button=QPushButton('Run Multi-H Validation')
        self.multi_run_button.setEnabled(False)
        self.multi_clearance=QCheckBox('Multi-H: I confirm full H+V+profiles clearance.\nFull approach, scan rectangle and return checked.')
        self.cancel_button=QPushButton('Cancel supervised validation / Localization')
        self.result=QLabel();self.result.setWordWrap(True)
        for w in (self.preview_button,self.run_button,self.hv_preview_button,self.hv_clearance,self.hv_run_button,self.multi_preview_button,self.multi_clearance,self.multi_run_button,self.cancel_button,self.result):layout.addWidget(w)
        self.preview_button.clicked.connect(lambda:self.preview('h_only'))
        self.hv_preview_button.clicked.connect(lambda:self.preview('hv'))
        self.hv_run_button.clicked.connect(self.start)
        self.multi_preview_button.clicked.connect(lambda:self.preview('multi_h'))
        self.multi_run_button.clicked.connect(self.start)
        self.run_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(lambda:window.localization_bridge.controller.request_cancel())
        for field in self.fields.values():field.textChanged.connect(self.invalidate_review)

    def invalidate_review(self,*_):
        self.reviewed=None
        self.run_button.setEnabled(False)
        self.hv_run_button.setEnabled(False)
        self.hv_clearance.setChecked(False)
        self.multi_run_button.setEnabled(False)
        self.multi_clearance.setChecked(False)
        for check in self.checks:check.setChecked(False)

    def set_busy(self,busy):
        for widget in (*self.fields.values(),*self.checks,self.preview_button,self.hv_preview_button,self.hv_clearance,self.multi_preview_button,self.multi_clearance,self.automatic_bounds):
            widget.setEnabled(not busy)
        self.invalidate_review()

    def bounds_mode_changed(self,automatic):
        for key in ('xmin','xmax','ymin','ymax'):
            self.fields[key].setReadOnly(automatic)
            self.fields[key].setPlaceholderText('Proposed on Preview' if automatic else 'Operator-reviewed current-frame limit')
        if hasattr(self,'run_button'):self.invalidate_review()

    def number(self,key,label):
        text=self.fields[key].text().strip()
        if not text:raise ValueError(f'H-only {label} is missing')
        try:value=float(text)
        except ValueError:raise ValueError(f'H-only {label} must be a number') from None
        if not isfinite(value):raise ValueError(f'H-only {label} must be finite')
        return value

    def marker_side(self):
        assignments=self.window.auto_relocation.selection.assignments
        if assignments is None or assignments.marker is None:
            raise ValueError('H-only reference square marker must be manually selected')
        marker=assignments.marker
        if not marker.width_um or marker.width_um!=marker.height_um:
            raise ValueError('H-only selected marker must have square geometry')
        return marker.width_um

    def build(self):
        state=self.window.auto_relocation.state
        if self.preview_xy is None:raise ValueError('H-only fresh stage position is unavailable; preview first')
        side=self.marker_side()
        spec_type={'h_only':HOnlySpec,'hv':HVSpec,'multi_h':MultiHSpec}[self.mode]
        spec=spec_type(self.preview_xy,StageBounds(
            self.number('xmin','clearance X minimum'),self.number('xmax','clearance X maximum'),
            self.number('ymin','clearance Y minimum'),self.number('ymax','clearance Y maximum'),state.context.frame_id),
            side_um=side,scan_margin_um=self.number('margin','scan margin'),step_um=self.number('step','scan step'))
        confirmation_type={'h_only':OperatorConfirmation,'hv':HVConfirmation,'multi_h':MultiHConfirmation}[self.mode]
        extra={'both_axes_clearance':self.hv_clearance.isChecked()} if self.mode=='hv' else {}
        if self.mode=='multi_h':
            extra=dict(both_axes_clearance=self.multi_clearance.isChecked(),multi_profile_clearance=self.multi_clearance.isChecked())
        confirmation=confirmation_type(*(c.isChecked() for c in self.checks),
            wavenumber_cm=self.number('wn','wavenumber'),note=self.fields['note'].text(),**extra)
        return spec,confirmation

    def preview(self,mode='h_only'):
        self.mode=mode
        self.invalidate_review()
        self.preview_xy=None
        try:
            if self.window.h_only_runner.busy:raise ValueError('H-only preview unavailable during acquisition')
            side=self.marker_side()
            margin=self.number('margin','scan margin')
            self.number('step','scan step')
            state=self.window.auto_relocation.state
            if not state.context.frame_id.strip():raise ValueError('H-only coordinate frame identity is missing')
            try:
                # Existing shared proxy serializes this read; no handoff, move,
                # task creation or change to joystick/laser state is performed.
                stage=self.window.stage
                with stage.execution_timeout(2.):
                    xy=stage.get_position()
                if (not isinstance(xy,(tuple,list)) or len(xy)!=2 or
                    any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in xy)):
                    raise ValueError('invalid XY readback')
            except Exception as error:
                raise ValueError(f'H-only fresh stage position unavailable: {error}') from error
            self.preview_xy=tuple(xy)
            for key,value in zip(('x','y'),xy):self.fields[key].setText(f'{value:g}')
            if self.automatic_bounds.isChecked():
                half=side/2+margin
                # Proposed clearance envelope, NOT controller travel limits or
                # proof of physical clearance. Run still requires confirmation.
                padding=HOnlySpec.position_tolerance_um
                yhalf=half if self.mode in ('hv','multi_h') else 0
                limits=(xy[0]-half-padding,xy[0]+half+padding,xy[1]-yhalf-padding,xy[1]+yhalf+padding)
                if self.mode=='multi_h':limits=clearance_rectangle(xy,side,margin)
                for key,value in zip(('xmin','xmax','ymin','ymax'),limits):self.fields[key].setText(f'{value:g}')
            spec,_=self.build();scan=spec.scan()
            self.invalidate_review()
            state=self.window.auto_relocation.state
            self.reviewed=(spec,state.context,state.context_generation)
            {'h_only':self.run_button,'hv':self.hv_run_button,'multi_h':self.multi_run_button}[self.mode].setEnabled(True)
            self.result.setText(f'Rough start: {spec.rough_start_xy} um\n'
                f'X start: {scan.start_um}; X end: {scan.end_um}; fixed Y: {scan.fixed_um} um\n'
                f'Step: {scan.step_um} um; points: {len(scan.positions())}\n'
                f'Marker: {side} x {side} um; expected width: {side} +/- {spec.width_tolerance_um} um\n'
                f'Return target: {spec.rough_start_xy}; position tolerance: {spec.position_tolerance_um} um\n'
                f'Clearance bounds (operator must verify): {spec.bounds}\n'
                'A rough point far from center may not capture both edges; no automatic extension/retry.')
            if self.mode in ('hv','multi_h'):
                v=spec.vertical(spec.rough_start_xy[0])
                self.result.setText(self.result.text()+f'\nH+V: V X is DYNAMIC: nearest integer H midpoint (ties-to-even), unknown until valid H.\nV Y: {v.start_um} to {v.end_um}; step {v.step_um}; {len(v.positions())} points.\nConfirm the full 2D clearance rectangle, not just the H line. Initial center only.')
            if self.mode=='multi_h':
                ys,scans=spec.plan(spec.rough_start_xy)
                self.result.setText(self.result.text()+f'\nMULTI-H preview only: {spec.profile_count} profiles; approximate Y {ys}; span {max(ys)-min(ys)} um.\nPreview X: {scans[0].start_um} to {scans[0].end_um}. Final X/Y derive from measured H/V center, revalidated before profiles.\nPlanner: +/-{spec.supported_rotation_deg} deg, center allowance {spec.center_uncertainty_um} um, inward guard {spec.boundary_guard_um} um; minimum {spec.minimum_profiles} CENTRAL and {spec.required_y_span_um} um accepted span.\nRounded central Y region at preview center: [{min(ys)}, {max(ys)}]. No rotation fit or registration publication.')
        except Exception as error:self.result.setText(str(error))

    def start(self):
        try:
            spec,confirmation=self.build()
            state=self.window.auto_relocation.state
            if self.reviewed!=(spec,state.context,state.context_generation):
                raise ValueError('preview_current_envelope_and_context_before_confirmation')
            handle=self.window.h_only_runner.start(spec,confirmation,self.fields['output'].text())
            self.result.setText({'h_only':'Running H only: ','hv':'Running H+V: ','multi_h':'Running Multi-H: '}[self.mode]+handle.run_id)
            self.invalidate_review() # Fresh preview and confirmation every attempt.
        except Exception as error:self.result.setText('Not started: '+str(error))
