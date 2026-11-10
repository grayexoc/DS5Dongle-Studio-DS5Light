"""Idempotent stream ownership; close playback without draining stale PCM."""
class OwnedStream:
    def __init__(self, stream, output=False):
        self.stream = stream
        self.output = output
        self.closed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        # PortAudio close aborts pending playback. Do not drain it with StopStream.
        if not self.output:
            try:
                self.stream.stop_stream()
            except Exception:
                pass
        self.stream.close()

    def stop_stream(self):
        self.close()
