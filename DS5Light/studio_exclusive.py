"""Bounded native WASAPI renderer for the opt-in Studio rehearsal."""
import base64
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Queue
import subprocess
import time
from threading import Thread

from thread_start import start_thread


@contextmanager
def prepare_exclusive_renderer(endpoint_id, *, live=False, cancel=lambda: False):
    script = Path(__file__).with_name('native') / 'StudioExclusiveRender.ps1'
    with subprocess.Popen(
        ['pwsh', '-NoProfile', '-File', str(script), endpoint_id, *(['live'] if live else [])],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    ) as child:
        messages = Queue()

        def receive():
            for line in child.stdout:
                messages.put(line.strip())
            messages.put(None)

        reader = Thread(target=receive, daemon=True)
        start_thread(reader)

        def expect(marker, timeout):
            expires = time.monotonic() + timeout
            while True:
                if cancel():
                    raise RuntimeError('Studio renderer cancelled.')
                remaining = expires - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f'Studio renderer timed out waiting for {marker}.')
                try:
                    response = messages.get(timeout=min(.05, remaining))
                    break
                except Empty:
                    continue
            if response != marker:
                raise RuntimeError(f'Studio renderer failed while waiting for {marker}: {response}')

        def send(line):
            child.stdin.write(line + '\n')
            child.stdin.flush()

        def stop():
            if child.poll() is not None:
                return
            try:
                send('STOP')
                child.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                child.kill()
                child.wait(timeout=2)

        class Renderer:
            def write(self, pcm):
                send(base64.b64encode(pcm).decode('ascii'))
                expect('WROTE', .4)

            def drain(self):
                send('DRAIN')
                expect('DRAINED', .4)

        @contextmanager
        def open_exclusive():
            try:
                send('GO')
                expect('EXCLUSIVE_STARTED', 1.5)
                yield Renderer()
            finally:
                stop()

        try:
            expect('READY', 10)
            yield open_exclusive
        finally:
            stop()
            reader.join(timeout=1)
