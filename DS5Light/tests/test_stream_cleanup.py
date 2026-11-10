import unittest
from stream_cleanup import OwnedStream
class StreamCleanupTests(unittest.TestCase):
    def test_playback_discards_without_stop_and_closes_once(self):
        events=[]
        class Stream:
            def stop_stream(self): events.append('drain')
            def close(self): events.append('close')
        owned=OwnedStream(Stream(),True)
        owned.stop_stream();owned.close()
        self.assertEqual(events,['close'])
    def test_capture_close_survives_stop_failure(self):
        events=[]
        class Stream:
            def stop_stream(self): raise OSError('unplugged')
            def close(self): events.append('close')
        OwnedStream(Stream()).close()
        self.assertEqual(events,['close'])
