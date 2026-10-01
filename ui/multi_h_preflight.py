"""Pure diagnostic gate; never constructs services or accesses instruments."""
from dataclasses import asdict
from uuid import uuid4

from ui.localization_orchestration import RunSettings
from ui.localization_pipeline import LocalizationPipelineServices
from ui.orientation_diagnostics import orientation_diagnostics
from ui.runtime_provenance import runtime_provenance


def run_settings(context, generation, rough_start_xy, purpose):
    """Shared with the actual supervised runner; no context reconstruction."""
    return RunSettings(context, generation, repr(rough_start_xy), purpose=purpose)


def multi_h_preflight(context, generation, *, rough_start_xy=None, frame_id=None):
    settings = run_settings(context, generation, rough_start_xy, 'multi_h')
    # Inspect the class referenced by the actual gate, even if a running process
    # has imported an alternate module/class. Do not normalize either side.
    expected = LocalizationPipelineServices.validate_context.__globals__['Orientation'].FLIP_X
    diagnostic = orientation_diagnostics(settings.context.orientation, expected,
        run_id='preflight-'+uuid4().hex, phase='preflight.context_orientation_gate')
    report = dict(kind='NO-MOTION MULTI-H PREFLIGHT', settings=asdict(settings),
        orientation_gate=diagnostic, provenance=runtime_provenance(),
        rough_start_source='cached preview only; no readback' if rough_start_xy is not None else 'not supplied',
        scope='Context/orientation gate only; NOT scan readiness or hardware validation.',
        registration_published=False, valid=False, reasons=())
    try:
        LocalizationPipelineServices.validate_context(settings,
            context.frame_id if frame_id is None else frame_id, diagnostic)
        report['valid'] = True
    except ValueError as error:
        report['reasons'] = (str(error),)
    return report
