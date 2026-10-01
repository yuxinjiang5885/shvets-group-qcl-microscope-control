"""Shared supervised H-only/H+V controls. Construction performs no device calls."""
from pathlib import Path
from dataclasses import asdict
import json
from math import isfinite
from PyQt6.QtCore import QObject,QThread,Qt,pyqtSlot,QTimer
from PyQt6.QtWidgets import QWidget,QFormLayout,QLineEdit,QCheckBox,QPushButton,QLabel,QVBoxLayout,QGroupBox
from experiment.scan_1d import StageBounds
from ui.h_only_validation import HOnlySpec,OperatorConfirmation,InputHandoff,HOnlyServices
from ui.hv_validation import HVSpec, HVConfirmation, HVServices
from ui.multi_h_validation import MultiHSpec, MultiHConfirmation, MultiHServices, clearance_rectangle
from ui.localization_daq import LocalizationDAQProvider
from ui.localization_orchestration import RunSettings,LocateMarkerWorker,CleanupOutcome,OwnershipError
from ui.localization_worker import LocateMarkerQtWorker
from ui.translation_localization import TranslationServices
from ui.translation_geometry import production_geometry, production_spec, requested_geometry, SEARCH_HALF_SPAN_MARKER_FACTOR
from ui.multi_h_preflight import multi_h_preflight, run_settings
from ui.runtime_provenance import PhaseTrace, runtime_provenance


class HOnlyRunner(QObject):
    def __init__(self,window,*,backend=None,services_type=HOnlyServices):
        super().__init__(window)
        self.window,self.bridge=window,window.localization_bridge
        self.backend,self.services_type=backend,services_type
        self.thread=None;self.worker=None;self.services=None;self.starting=False

    @property
    def busy(self):return self.starting or self.thread is not None

    def start(self,spec,confirmation,output_dir,*,production=False):
        if self.busy:raise OwnershipError('H_run_already_active')
        if production and not getattr(self.window,'translation_launch_enabled',False):
            raise OwnershipError('translation_live_launch_requires_supervised_opt_in')
        if production and (type(spec) is not HVSpec or type(confirmation) is not HVConfirmation):
            raise ValueError('translation_requires_HV_spec_confirmation')
        self.starting=True
        self.phase_trace=PhaseTrace()
        self.phase_trace.record('runner_start')
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
            provenance=runtime_provenance()
            self.phase_trace.record('handoff_begin')
            handoff=InputHandoff(self.bridge);handoff.prepare()
            purpose='multi_h' if isinstance(spec,MultiHSpec) else ('hv' if isinstance(spec,HVSpec) else 'h_only')
            if production:purpose='translation_only'
            settings=run_settings(context,generation,spec.rough_start_xy,purpose)
            self.phase_trace.record('settings_created')
            handle=self.bridge.acquire(settings)
            self.phase_trace.bind(handle.run_id)
            self.phase_trace.record('ownership_acquired')
            provider=LocalizationDAQProvider(self.bridge,handle,self.backend)
            services_type = self.services_type
            if services_type is HOnlyServices:
                services_type = {'h_only':HOnlyServices,'hv':HVServices,'multi_h':MultiHServices,'translation_only':TranslationServices}[purpose]
            self.services=services_type(self.bridge,handle,spec,output_dir,provider,
                confirmation=confirmation,handoff=handoff)
            self.services.phase_trace=self.phase_trace
            self.services.report.update(provenance=provenance, breadcrumbs=self.phase_trace.events)
            self.thread=QThread(self)
            self.worker=LocateMarkerQtWorker(LocateMarkerWorker(controller,handle,self.services))
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            for name in ('started','progress','phase_changed','profile_completed','warning','failed','cancelled','registration_completed','finished'):
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
            restore=self.services.handoff.restore_result,registration_published=(
                self.services.handle.settings.purpose=='translation_only' and snapshot['acquisition']=='COMPLETE'))
        report[self.services.handle.settings.purpose+'_complete'] = snapshot['acquisition']=='COMPLETE' and snapshot['ownership']=='AVAILABLE'
        try:
            if self.services.path.exists():
                (self.services.path/(self.services.handle.settings.purpose+'_result.json')).write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
            elif 'orientation_gate' in report:
                # prepare can fail before the scan directory is created. Retain
                # identity evidence without creating a misleading scan journal.
                path=self.services.path.parent/(self.services.handle.run_id+'_prepare_diagnostics.json')
                with path.open('x',encoding='utf-8') as stream:
                    json.dump(report,stream,indent=2,default=str)
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
        layout.addWidget(QLabel('Locate Marker: H → V → translation-only registration. Preview and confirm full 2D clearance.'))
        form=QFormLayout();self.fields={}
        for key,label,value in (('x','Fresh preview X (um)',''),('y','Fresh preview Y (um)',''),
            ('xmin','Clearance bounds X min',''),('xmax','Clearance bounds X max',''),
            ('ymin','Clearance bounds Y min',''),('ymax','Clearance bounds Y max',''),
            ('margin','Development/reference scan margin (um)','100'),('step','Development/reference step (um)','10'),
            ('wn','Operator-confirmed wavenumber (cm^-1)','1500'),('note','Operator / clearance note',''),
            ('output','Journal directory',str(Path.cwd()/'localization_runs'))):
            self.fields[key]=QLineEdit(value);form.addRow(label,self.fields[key])
        layout.addLayout(form)
        self.production_group=QGroupBox('Production Scan Settings')
        pf=QFormLayout(self.production_group)
        self.production_override=QCheckBox('Override automatic scan geometry')
        self.production_half=QLineEdit();self.production_step=QLineEdit()
        self.production_summary=QLabel();self.production_summary.setWordWrap(True)
        self.production_reset=QPushButton('Reset to Automatic Defaults')
        pf.addRow(self.production_override)
        pf.addRow('Requested search half-span (um)',self.production_half)
        pf.addRow('Requested step (integer um)',self.production_step)
        pf.addRow(self.production_summary);pf.addRow(self.production_reset)
        layout.addWidget(self.production_group)
        for key in ('x','y'):
            self.fields[key].setReadOnly(True)
            self.fields[key].setPlaceholderText('Read from stage on Preview')
        self.automatic_bounds=QCheckBox('Propose bounds for this scan sequence (operator must verify clearance)')
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
        self.translation_preview_button=QPushButton('Preview Locate Marker Envelope (H+V)')
        self.translation_clearance=QCheckBox('Locate Marker: I confirm full H+V approach/scan/return clearance in BOTH axes.')
        layout.addWidget(self.translation_preview_button)
        layout.addWidget(self.translation_clearance)
        self.translation_preview_button.clicked.connect(lambda:self.preview('translation_only'))
        window.auto_relocation.locate_button.clicked.connect(self.start_translation)
        window.auto_relocation.locate_button.setToolTip(
            'Preview and confirm H+V clearance. A live test requires --supervised-translation-only.')
        self.preview_button=QPushButton('Preview H Envelope')
        self.run_button=QPushButton('Run H-Only Validation')
        self.run_button.setEnabled(False)
        self.reviewed=None
        self.hv_preview_button=QPushButton('Preview H+V Envelope')
        self.hv_run_button=QPushButton('Run H+V Validation')
        self.hv_run_button.setEnabled(False)
        self.hv_clearance=QCheckBox('H+V: I confirm movement in BOTH X and Y.\nFull 2D rectangle, approach and return clearance checked.')
        self.multi_preflight_button=QPushButton('Run Multi-H Preflight (no hardware calls)')
        self.multi_preflight_button.clicked.connect(self.preflight)
        self.multi_preview_button=QPushButton('Preview Multi-H Envelope')
        self.multi_run_button=QPushButton('Run Multi-H Validation')
        self.multi_run_button.setEnabled(False)
        self.multi_clearance=QCheckBox('Multi-H: I confirm full H+V+profiles clearance.\nFull approach, scan rectangle and return checked.')
        self.cancel_button=QPushButton('Cancel supervised validation / Localization')
        self.result=QLabel();self.result.setWordWrap(True)
        self.development_actions=QWidget()
        dev=QVBoxLayout(self.development_actions)
        for w in (self.preview_button,self.run_button,self.hv_preview_button,self.hv_clearance,self.hv_run_button,self.multi_preflight_button,self.multi_preview_button,self.multi_clearance,self.multi_run_button):dev.addWidget(w)
        window.auto_relocation.development_body.layout().addWidget(self.development_actions)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.result)
        self.preview_button.clicked.connect(lambda:self.preview('h_only'))
        self.hv_preview_button.clicked.connect(lambda:self.preview('hv'))
        self.hv_run_button.clicked.connect(self.start)
        self.multi_preview_button.clicked.connect(lambda:self.preview('multi_h'))
        self.multi_run_button.clicked.connect(self.start)
        self.run_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(lambda:window.localization_bridge.controller.request_cancel())
        for field in self.fields.values():field.textChanged.connect(self.invalidate_review)
        self.production_override.toggled.connect(self.production_settings_changed)
        self.production_half.textChanged.connect(self.production_settings_changed)
        self.production_step.textChanged.connect(self.production_settings_changed)
        self.production_reset.clicked.connect(self.reset_production_defaults)
        window.auto_relocation.selection.chip_layout_changed.connect(self.production_settings_changed)
        self.production_settings_changed()

    def production_values(self):
        side=self.marker_side()
        if not self.production_override.isChecked():return requested_geometry(side)
        try:
            half=float(self.production_half.text());step=float(self.production_step.text())
        except ValueError:raise ValueError('Production half-span and step must be finite numbers') from None
        return requested_geometry(side,half,step)

    def production_settings_changed(self,*_):
        self.invalidate_review()
        override=self.production_override.isChecked()
        self.production_half.setReadOnly(not override);self.production_step.setReadOnly(not override)
        try:
            side=self.marker_side()
            if not override:
                _,step=production_geometry(side)
                for field,value in ((self.production_half,SEARCH_HALF_SPAN_MARKER_FACTOR*side),(self.production_step,step)):
                    field.blockSignals(True);field.setText(f'{value:g}');field.blockSignals(False)
            mode,requested,step,half=self.production_values()
            points=int(2*half/step+1)
            self.production_summary.setText(f'Marker: {side:g} x {side:g} um; mode: {mode}\nRequested half-span: {requested:g} um; requested/actual step: {step:g} um\nActual half-span: {half:g} um; actual span: {2*half:g} um\nPoints / axis: {points}; total H+V points: {2*points}')
        except ValueError as error:self.production_summary.setText(str(error))

    def reset_production_defaults(self):
        self.production_override.setChecked(False)
        self.production_settings_changed()

    def preflight(self):
        try:
            if self.window.h_only_runner.busy:
                raise ValueError('preflight_unavailable_during_acquisition')
            state=self.window.auto_relocation.state
            with state.lock:
                context,generation=state.context,state.context_generation
            frame=self.reviewed[0].bounds.frame_id if self.reviewed else context.frame_id
            report=multi_h_preflight(context,generation,rough_start_xy=self.preview_xy,frame_id=frame)
            report['legacy_daq_session']=self.window.localization_bridge.legacy_daq_evidence.snapshot()
            self.preflight_report=report
            self.result.setText(json.dumps(report,indent=2,default=str))
            self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        except Exception as error:
            self.result.setText('Preflight could not complete: '+str(error))

    def start_translation(self):
        if self.mode != 'translation_only':
            self.result.setText('Preview Locate Marker Envelope before starting.')
            return
        self.start()

    def invalidate_review(self,*_):
        self.window.auto_relocation.locate_button.setEnabled(False)
        self.translation_clearance.setChecked(False)
        self.reviewed=None
        self.run_button.setEnabled(False)
        self.hv_run_button.setEnabled(False)
        self.hv_clearance.setChecked(False)
        self.multi_run_button.setEnabled(False)
        self.multi_clearance.setChecked(False)
        for check in self.checks:check.setChecked(False)

    def set_busy(self,busy):
        self.production_group.setEnabled(not busy)
        for widget in (*self.fields.values(),*self.checks,self.translation_preview_button,self.translation_clearance,self.preview_button,self.hv_preview_button,self.hv_clearance,self.multi_preflight_button,self.multi_preview_button,self.multi_clearance,self.automatic_bounds):
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
        spec_type={'h_only':HOnlySpec,'hv':HVSpec,'multi_h':MultiHSpec,'translation_only':HVSpec}[self.mode]
        bounds=StageBounds(
            self.number('xmin','clearance X minimum'),self.number('xmax','clearance X maximum'),
            self.number('ymin','clearance Y minimum'),self.number('ymax','clearance Y maximum'),state.context.frame_id)
        options={}
        if self.mode=='translation_only':
            mode,requested,step,_=self.production_values()
            if mode=='override':options=dict(half_span=requested,step_um=step)
        spec=production_spec(self.preview_xy,bounds,side,**options) if self.mode=='translation_only' else spec_type(self.preview_xy,bounds,
            side_um=side,scan_margin_um=self.number('margin','scan margin'),step_um=self.number('step','scan step'))
        confirmation_type={'h_only':OperatorConfirmation,'hv':HVConfirmation,'multi_h':MultiHConfirmation,'translation_only':HVConfirmation}[self.mode]
        extra={'both_axes_clearance':self.hv_clearance.isChecked()} if self.mode=='hv' else {}
        if self.mode=='translation_only':extra={'both_axes_clearance':self.translation_clearance.isChecked()}
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
            if self.mode=='translation_only':
                production_mode,production_requested,production_step,production_half=self.production_values()
                margin=production_half-side/2
            else:
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
                yhalf=half if self.mode in ('hv','multi_h','translation_only') else 0
                limits=(xy[0]-half-padding,xy[0]+half+padding,xy[1]-yhalf-padding,xy[1]+yhalf+padding)
                if self.mode=='multi_h':limits=clearance_rectangle(xy,side,margin)
                for key,value in zip(('xmin','xmax','ymin','ymax'),limits):self.fields[key].setText(f'{value:g}')
            spec,_=self.build();scan=spec.scan()
            self.invalidate_review()
            state=self.window.auto_relocation.state
            self.reviewed=(spec,state.context,state.context_generation)
            {'h_only':self.run_button,'hv':self.hv_run_button,'multi_h':self.multi_run_button,'translation_only':self.window.auto_relocation.locate_button}[self.mode].setEnabled(
                self.mode!='translation_only' or getattr(self.window,'translation_launch_enabled',False))
            self.result.setText(f'Rough start: {spec.rough_start_xy} um\n'
                f'X start: {scan.start_um}; X end: {scan.end_um}; fixed Y: {scan.fixed_um} um\n'
                f'Step: {scan.step_um} um; points: {len(scan.positions())}\n'
                f'Marker: {side} x {side} um; expected width: {side} +/- {spec.width_tolerance_um} um\n'
                f'Return target: {spec.rough_start_xy}; position tolerance: {spec.position_tolerance_um} um\n'
                f'Clearance bounds (operator must verify): {spec.bounds}\n'
                'A rough point far from center may not capture both edges; no automatic extension/retry.')
            if self.mode in ('hv','multi_h','translation_only'):
                v=spec.vertical(spec.rough_start_xy[0])
                self.result.setText(self.result.text()+f'\nH+V: V X is DYNAMIC: nearest integer H midpoint (ties-to-even), unknown until valid H.\nV Y: {v.start_um} to {v.end_um}; step {v.step_um}; {len(v.positions())} points.\nConfirm the full 2D clearance rectangle, not just the H line. Initial center only.')
            if self.mode=='translation_only':
                self.result.setText(self.result.text()+f'\nProduction mode: {production_mode}; requested half-span: {production_requested:g} um; requested step: {production_step:g} um; actual half-span: {production_half:g} um; total span: {2*production_half:g} um; total H+V points: {2*len(scan.positions())}.\nDevelopment/reference fields do not apply. Move to a point clearly on the selected marker; exact centering is not required.\nSpeed/coverage default; center accuracy is not calibrated. 10 um remains reference sampling.')
                self.result.setText(self.result.text()+'\nProduction uses this H/V center as the registration anchor; theta=0 is assumed, not measured. Publication follows return and cleanup.')
                if not getattr(self.window,'translation_launch_enabled',False):
                    self.result.setText(self.result.text()+'\nLive launch disabled: separately supervised --supervised-translation-only opt-in required.')
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
            handle=self.window.h_only_runner.start(spec,confirmation,self.fields['output'].text(),production=self.mode=='translation_only')
            self.result.setText({'h_only':'Running H only: ','hv':'Running H+V: ','multi_h':'Running Multi-H: ','translation_only':'Locating marker (translation only): '}[self.mode]+handle.run_id)
            self.invalidate_review() # Fresh preview and confirmation every attempt.
        except Exception as error:self.result.setText('Not started: '+str(error))
