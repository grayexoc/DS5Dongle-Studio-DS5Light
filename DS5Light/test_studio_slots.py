import unittest
from studio_slots import StudioClient, Slot

class Fake:

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def send_feature_report(self, p):
        self.sent.append(p)
        return len(p)

    def get_feature_report(self, r, n):
        assert r in (129, 132)
        return self.replies.pop(0) if self.replies else bytes(64)

def info(i=0, valid=1, name='Audio Haptics', status=0):
    return bytes([132, 102, 10, status, i, valid, 19]) + name.encode()[:16].ljust(16, b'\x00') + bytes(41)

def activate(status=0, reconnect=0):
    return bytes([132, 102, 9, status, 0, reconnect, 0]) + bytes(57)

class Tests(unittest.TestCase):

    def client(self, replies):
        d = Fake(replies)
        return (StudioClient(d, sleep=lambda _: None), d)

    def test_names_and_empty(self):
        c, d = self.client([info(name='테스트'), info(1, 0)])
        self.assertEqual(c.info(0).name, '테스트')
        self.assertEqual(c.info(1).label(), '02 · Empty')
        self.assertTrue(all((x[2] == 10 for x in d.sent)))

    def test_unavailable_not_empty(self):
        c, d = self.client([info(status=1)])
        self.assertEqual(c.info(0).state, 'unavailable')

    def test_stale_and_pending(self):
        c, d = self.client([info(1), info(status=254), info()])
        self.assertEqual(c.info(0).name, 'Audio Haptics')

    def test_timeout_not_empty(self):
        c, d = self.client([])
        with self.assertRaises(TimeoutError):
            c.info(0)

    def test_empty_cannot_activate(self):
        c, d = self.client([info(valid=0)])
        with self.assertRaises(ValueError):
            c.activate(0)
        self.assertEqual([p[2] for p in d.sent], [10])

    def test_deferred_and_reconnect(self):
        c, d = self.client([info(), activate(2, 1)])
        r = c.activate(0)
        self.assertTrue(r['deferred'])
        self.assertTrue(r['reconnect'])
        self.assertEqual([p[2] for p in d.sent], [10, 9])

    def test_activation_not_retried(self):
        c, d = self.client([info()])
        with self.assertRaises(TimeoutError):
            c.activate(0)
        self.assertEqual([p[2] for p in d.sent], [10, 9])

    def test_bounds_and_write_whitelist(self):
        c, d = self.client([])
        for cmd, idx in [(8, 0), (3, 0), (9, 32), (10, -1)]:
            with self.assertRaises(ValueError):
                c.request(cmd, idx)
        self.assertFalse(d.sent)

    def test_32_slots(self):
        c, d = self.client([info(i, valid=i % 2) for i in range(32)])
        self.assertEqual(len(c.slots()), 32)
        self.assertEqual([p[3] for p in d.sent], list(range(32)))

    def test_rejection(self):
        c, d = self.client([info(), activate(1)])
        with self.assertRaises(RuntimeError):
            c.activate(0)

class ProfileTests(unittest.TestCase):

    def reply(self, index=3, edited=1, status=0):
        return bytes([129, 102, 103, status, index, edited]) + b'Audio Haptics'.ljust(16, b'\x00') + bytes(42)

    def test_current_slot_read_only(self):
        d = Fake([self.reply()])
        r = StudioClient(d, sleep=lambda _: None).profile()
        self.assertEqual(r, dict(index=3, edited=True, name='Audio Haptics'))
        self.assertEqual(d.sent, [bytes([128, 102, 103]) + bytes(61)])

    def test_unknown_not_first_slot(self):
        d = Fake([self.reply(255)])
        self.assertIsNone(StudioClient(d, sleep=lambda _: None).profile()['index'])

    def test_stale_reply_ignored(self):
        d = Fake([info(), self.reply()])
        self.assertEqual(StudioClient(d, sleep=lambda _: None).profile()['index'], 3)

    def test_bad_response(self):
        d = Fake([self.reply(edited=2)])
        with self.assertRaises(RuntimeError):
            StudioClient(d, sleep=lambda _: None).profile()

    def test_unsupported(self):
        d = Fake([])
        with self.assertRaises(TimeoutError):
            StudioClient(d, sleep=lambda _: None).profile()
