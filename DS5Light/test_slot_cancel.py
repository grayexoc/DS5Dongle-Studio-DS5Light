"""Inherited Studio reads and slot activation must obey SettingsClient policy."""
import threading
import unittest
from unittest.mock import patch

from studio_settings_protocol import SettingsClient
from test_studio_slots import Fake, info


class CancellationTests(unittest.TestCase):
    def test_cancelled_or_expired_activation_sends_nothing(self):
        for expired in (False, True):
            with self.subTest(expired=expired):
                device = Fake([info(2)])
                client = SettingsClient(device, sleep=lambda _:None, cancel=lambda:not expired)
                if expired:client.deadline = 0
                with self.assertRaises(RuntimeError):client.activate(2)
                self.assertFalse(device.sent)

    def test_cancellation_during_info_never_sends_activation(self):
        cancel = threading.Event()
        device = Fake([info(2)])
        read = device.get_feature_report
        def cancelled_read(*args):
            reply = read(*args);cancel.set();return reply
        device.get_feature_report = cancelled_read
        client = SettingsClient(device, sleep=lambda _:None, cancel=cancel.is_set)
        with self.assertRaises(RuntimeError):client.activate(2)
        self.assertEqual([p[2] for p in device.sent], [10])

    def test_slot_listing_stops_during_wait(self):
        cancel = threading.Event();device = Fake([info(i) for i in range(32)])
        client = SettingsClient(device, sleep=lambda _:cancel.set(), cancel=cancel.is_set)
        with self.assertRaises(RuntimeError):client.slots()
        self.assertEqual([(p[2],p[3]) for p in device.sent], [(10,0)])
        self.assertEqual(len(device.replies), 32)

    def test_metadata_cancellation_during_wait_prevents_read(self):
        cancel = threading.Event();device = Fake([bytes(64)])
        client = SettingsClient(device, sleep=lambda _:cancel.set(), cancel=cancel.is_set)
        with self.assertRaises(RuntimeError):client.profile()
        self.assertEqual(len(device.replies), 1)

    def test_deadline_is_checked_again_after_sleep(self):
        now = [1.0];device = Fake([info(2)])
        def sleep(_):now[0] = 3
        client = SettingsClient(device, sleep=sleep);client.deadline = 2
        with patch('studio_settings_protocol.time.monotonic', side_effect=lambda:now[0]):
            with self.assertRaises(RuntimeError):client.activate(2)
        self.assertEqual([p[2] for p in device.sent], [10])
        self.assertEqual(len(device.replies), 1)


if __name__ == '__main__':unittest.main()
