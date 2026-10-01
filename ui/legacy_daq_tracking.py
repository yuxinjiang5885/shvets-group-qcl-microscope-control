"""Experimental legacy-DAQ evidence, not an NI task provider or reset control."""
from pathlib import Path
from types import FunctionType, CodeType
from hashlib import sha256
import time
from uuid import uuid4

from ui.localization_orchestration import OwnershipError


class LegacyDaqEvidence:
    def __init__(self):
        self.session_id = uuid4().hex
        self.records = {}
        self.ever_acquired = False

    def acquired_or_uncertain(self, source, *, owner=None, verifier=None):
        token = uuid4().hex
        if owner is None or not hasattr(owner,'ever_acquired'):
            self.ever_acquired=True  # Uninstrumented legacy source: conservative evidence.
        self.records[token] = dict(source=source, timestamp=time.time(), released=False,
                                   owner=owner, verifier=verifier)
        return token

    @property
    def uncertain(self):
        return any(not row['released'] for row in self.records.values())

    def confirm_release(self, token):
        row = self.records.get(token)
        if row is None or row['released']:
            raise OwnershipError('unknown_or_stale_legacy_DAQ_release')
        # Only an instrumented owner may supply a positive cleanup verifier.
        # Legacy callbacks currently supply none; thread completion is not proof.
        if row['owner'] is None or not callable(row['verifier']):
            raise OwnershipError('legacy_DAQ_has_no_release_verifier')
        if row['verifier'](row['owner']) is not True:
            raise OwnershipError('legacy_DAQ_release_unconfirmed')
        row['released'] = True
        row['released_at'] = time.time()
        # Retain all unresolved ownership, but only the most recent 32 completed sources.
        completed=[token for token,row in self.records.items() if row['released']]
        for old in completed[:-32]:del self.records[old]

    def snapshot(self):
        return dict(session_id=self.session_id,
            ever_acquired=self.ever_acquired,
            state='release_uncertain' if self.uncertain else ('released' if self.records else 'never_acquired'),
            transitions=[dict(token=token, source=row['source'], timestamp=row['timestamp'],
                              released=row['released'],
                              released_at=row.get('released_at'),
                              lifecycle=row['owner'].snapshot() if hasattr(row['owner'],'snapshot') else None)
                         for token,row in self.records.items()])


def invoke_acquisition(callback, mark_uncertain, *args, snake_bridge=None, **kwargs):
    """Mark at the reviewed worker-creation boundary, not an early-return callback.

    All six stable acquisition callbacks assign a QThread before creating any
    acquisition worker. A private globals copy intercepts that factory. No global
    patch, NI import or stable-file change. Unknown/modified code remains blocked
    conservatively at entry rather than assuming it follows the audited order.
    """
    function = getattr(callback, '__func__', None)
    path = Path(__file__).resolve().parents[1]/'qcl_scanning_imaging_ui.py'
    reviewed = False
    audited_names = ('run_experiment', 'repeat_experiment', 'multiple',
                     'run_snake_scan', 'repeat_snake_scan', 'run_scanning_imaging')
    if (function is not None and function.__name__ in audited_names
            and Path(function.__code__.co_filename).resolve() == path):
        try:
            source = path.read_bytes()
            if sha256(source).hexdigest() != 'fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab':
                raise ValueError('unaudited_stable_source')
            # Compile, never execute: preserve class/nested-function code identity
            # without importing the operational hardware module.
            compiled = compile(source, function.__code__.co_filename, 'exec', dont_inherit=True)
            cls = next(c for c in compiled.co_consts
                       if isinstance(c, CodeType) and c.co_name == 'mainWindow')
            expected = next(c for c in cls.co_consts
                            if isinstance(c, CodeType) and c.co_name == function.__name__)
            reviewed = (function.__code__ == expected
                        and 'QThread' in function.__code__.co_names)
        except (OSError,ValueError,StopIteration,SyntaxError):
            pass
    if not reviewed:
        mark_uncertain('unreviewed_callback:'+getattr(callback,'__name__',repr(callback)))
        return callback(*args,**kwargs)
    namespace = dict(function.__globals__)
    original = namespace['QThread']
    snake = snake_bridge is not None and function.__name__ in ('run_snake_scan','repeat_snake_scan')
    created_threads=[]
    def thread_factory(*a,**k):
        if not snake:mark_uncertain('worker_creation:'+function.__name__)
        thread=original(*a,**k);created_threads.append(thread)
        return thread
    namespace['QThread'] = thread_factory
    if snake:
        from ui.snake_daq_lifecycle import snake_worker_factory
        name='snakeScan' if function.__name__=='run_snake_scan' else 'repeatSnakeScan'
        base=namespace[name]
        namespace[name]=lambda:snake_worker_factory(base,snake_bridge,created_threads[-1],function.__name__)
    private = FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    private.__kwdefaults__ = function.__kwdefaults__
    return private(callback.__self__,*args,**kwargs)
