"""Human terminal progress on stderr; stdout remains the CLI JSON contract."""
from __future__ import annotations

import sys
import threading
import time


class TerminalProgress:
    def __init__(self, *, enabled=True, interval=15, stream=None):
        self.enabled = enabled
        self.interval = interval
        self.stream = stream if stream is not None else sys.stderr
        self.started = time.monotonic()
        self.stage = 'Iniciando'
        self.updated = self.started
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None

    def _write(self, message):
        elapsed = int(time.monotonic() - self.started)
        # One bounded line, including when editorial text contains newlines.
        message = ' '.join(str(message).split())[:300]
        print(f'[{elapsed//60:02d}:{elapsed%60:02d}] {message}', file=self.stream, flush=True)

    def __call__(self, message):
        if self.enabled:
            with self.lock:
                self.stage = message
                self.updated = time.monotonic()
                self._write(message)

    def _heartbeat(self):
        while not self.stop.wait(self.interval):
            with self.lock:
                if time.monotonic() - self.updated >= self.interval:
                    self._write(f'En curso: {self.stage}')

    def __enter__(self):
        if self.enabled:
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        if self.thread:
            self.thread.join()
