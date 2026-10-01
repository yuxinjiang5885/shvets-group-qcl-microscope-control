"""Read-only process provenance and low-volume in-memory phase evidence."""
import hashlib
import marshal
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

MODULES = ('ui.localization_pipeline', 'ui.h_only_validation', 'ui.hv_validation',
           'ui.multi_h_validation', 'ui.localization_orchestration',
           'experiment.stage_registration')
REPO = Path(__file__).resolve().parents[1]


def module_info(module):
    source = getattr(module, '__file__', None)
    path = Path(source).resolve() if source else None
    result = dict(file=source, resolved_path=str(path) if path else None,
                  module_id=id(module))
    try:
        result['source_file_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest() if path else None
    except OSError as error:
        result['source_read_error'] = str(error)
    return result


def runtime_provenance():
    from ui.localization_pipeline import LocalizationPipelineServices
    from ui.multi_h_validation import MultiHServices
    from ui.localization_orchestration import LocateMarkerWorker
    result = dict(executable=sys.executable, cwd=str(Path.cwd().resolve()),
                  repo_root=str(REPO), modules={}, code={}, sys_path=[], logical_modules={})
    try:
        completed = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=2,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        result['git_head'] = completed.stdout.strip() if completed.returncode == 0 else None
        result['git_error'] = completed.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        result['git_error'] = str(error)
    for name in MODULES:
        result['modules'][name] = module_info(sys.modules[name])
    for name, function in (
        ('LocalizationPipelineServices.prepare', LocalizationPipelineServices.prepare),
        ('LocalizationPipelineServices.validate_context', LocalizationPipelineServices.validate_context),
        ('MultiHServices.prepare', MultiHServices.prepare),
        ('MultiHServices.work', MultiHServices.work),
        ('LocateMarkerWorker.run', LocateMarkerWorker.run)):
        code = function.__code__
        result['code'][name] = dict(function_id=id(function), module=function.__module__,
            filename=code.co_filename, resolved_path=str(Path(code.co_filename).resolve()),
            first_line=code.co_firstlineno,
            runtime_code_sha256=hashlib.sha256(marshal.dumps(code)).hexdigest())
    for index, entry in enumerate(sys.path):
        root = Path(entry or os.getcwd()).resolve()
        candidates = [str(root.joinpath(*name.split('.')).with_suffix('.py'))
                      for name in MODULES if root.joinpath(*name.split('.')).with_suffix('.py').is_file()]
        result['sys_path'].append(dict(index=index, entry=entry, resolved_path=str(root),
                                       candidate_sources=candidates))
    result['alternate_repo_candidates'] = [entry for entry in result['sys_path']
        if entry['candidate_sources'] and Path(entry['resolved_path']) != REPO]
    for name, module in list(sys.modules.items()):
        source = getattr(module, '__file__', None)
        if not source:
            continue
        stem = Path(source).stem
        if stem in ('localization_pipeline', 'multi_h_validation', 'stage_registration'):
            result['logical_modules'].setdefault(stem, []).append(dict(name=name, **module_info(module)))
    result['duplicate_logical_modules'] = {k:v for k,v in result['logical_modules'].items() if len(v)>1}
    result['hash_note'] = ('File SHA256 describes disk bytes at collection; runtime code hash describes '
                          'the loaded code object (Python-version/path dependent), not disk freshness.')
    return result


class PhaseTrace:
    def __init__(self):
        self.run_id = None
        self.events = []

    def bind(self, run_id):
        self.run_id = run_id
        for event in self.events:
            event['run_id'] = run_id

    def record(self, phase):
        self.events.append(dict(run_id=self.run_id, sequence=len(self.events)+1,
            timestamp=time.time(), monotonic_ns=time.monotonic_ns(),
            thread_id=threading.get_ident(), thread_name=threading.current_thread().name,
            phase=phase))


def breadcrumb(services, phase):
    trace = getattr(services, 'phase_trace', None)
    if trace is not None:
        trace.record(phase)
