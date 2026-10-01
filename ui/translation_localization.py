"""Production MVP: exactly the live-validated H/V acquisition, then translation."""
from hashlib import sha256
from time import monotonic
from ui.production_marker_selection import select_marker_candidate

from ui.hv_validation import HVServices
from ui.translation_registration import TranslationEvidence, build_translation_registration


class TranslationServices(HVServices):
    def prepare(self, settings):
        self.localization_started=monotonic()
        scan = self.spec.scan()
        mode, requested, step = self.spec.production_geometry or ('reference', (scan.end_um-scan.start_um)/2, scan.step_um)
        self.report.update(marker_side_um=self.spec.side_um,
            geometry_mode=mode,requested_production_half_span_um=requested,requested_step_um=step,
            actual_half_span_um=(scan.end_um-scan.start_um)/2,
            actual_span_um=scan.end_um-scan.start_um, step_um=scan.step_um,
            points_per_axis=len(scan.positions()),total_scan_points=2*len(scan.positions()),
            sampling_interpretation='Production speed/coverage sampling; physical center accuracy not calibrated')
        super().prepare(settings)

    def _scan(self, name, *args, **kwargs):
        if name not in ('initial_H', 'initial_V'):
            raise ValueError('translation_only_forbids_extra_profiles')
        started=monotonic()
        result = super()._scan(name, *args, require_valid_edges=False, **kwargs)
        scan, generic = result
        axis=0 if name=='initial_H' else 1
        edge,diagnostics=select_marker_candidate(generic,self.spec.side_um,
            self.spec.width_tolerance_um,self.spec.rough_start_xy[axis],scan=scan)
        self.report.setdefault('production_candidates',{})[name]=diagnostics
        self.report.setdefault('scan_duration_s',{})[name]=monotonic()-started
        if not edge.valid:
            raise ValueError('edge_failed:'+name+':'+repr(edge.reasons))
        result=scan,edge
        if name == 'initial_H':
            self.horizontal_result = result
        elif name == 'initial_V':
            self.vertical_result = result
        return result

    def work(self, settings, checkpoint, progress):
        if settings.purpose != 'translation_only':
            raise ValueError('translation_run_purpose_required')
        self.acquire_initial_center(checkpoint, progress)
        checkpoint()
        h, he = self.horizontal_result
        v, ve = self.vertical_result
        evidence = TranslationEvidence(settings.context, self.handle.run_id, h, v, he, ve,
            tuple((str(p), sha256(p.read_bytes()).hexdigest()) for p in self.journals),
            self.report.get('warnings', ()))
        registration = build_translation_registration(evidence)
        self.report.update(registration_mode=registration.registration_mode,
            marker_center_stage_um=(he.midpoint_um,ve.midpoint_um),
            rotation_calibrated=False, assumed_theta_deg=0.0, warnings=registration.warnings,
            registration_published=False, source_hashes=evidence.source_hashes)
        progress(dict(warnings=registration.warnings, translation_candidate=self.report.copy()))
        self._phase('success_only_return', checkpoint, progress)
        self.report['return_status'] = 'FAILED_OR_INCOMPLETE'
        self._return(checkpoint)
        self.report['return_status'] = 'PASS'
        checkpoint()
        return evidence

    def release_daq(self):
        try:
            return super().release_daq()
        finally:
            if hasattr(self,'localization_started'):
                self.report['localization_duration_through_daq_cleanup_s']=monotonic()-self.localization_started
