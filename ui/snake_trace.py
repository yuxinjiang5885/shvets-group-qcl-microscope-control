"""Best-effort Snake trace persistence; no GUI/native calls or caller-side I/O."""
import json
from pathlib import Path
from queue import Queue, Full
from threading import Thread


class SnakeTraceWriter:
    def __init__(self, path):
        self.path = Path(path)
        self.queue = Queue(maxsize=2048)
        self.dropped = 0
        self.error = None
        self.thread = Thread(target=self._write, name='Snake diagnostic writer', daemon=True)
        self.thread.start()

    def record(self, event):
        try:
            self.queue.put_nowait(event)
        except Full:
            self.dropped += 1

    def finish(self):
        """Nonblocking request; never join from GUI or make shutdown depend on logging."""
        self.record(None)

    def _write(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as stream:
                while True:
                    event = self.queue.get()
                    if event is None: return
                    stream.write(json.dumps(event, allow_nan=False) + '\n')
                    stream.flush()
        except Exception as error:
            self.error = str(error)  # No retry, hardware effect or GUI exception.
