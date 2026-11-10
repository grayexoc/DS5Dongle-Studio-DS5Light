import unittest
from unittest.mock import patch

from studio_settings_protocol import SettingsClient


class SaveDevice:
    def __init__(self, modes):
        self.modes = list(modes)
        self.sent = []

    def send_feature_report(self, packet):
        self.sent.append(bytes(packet))
        return len(packet)

    def get_feature_report(self, report, size):
        mode = self.modes.pop(0) if len(self.modes) > 1 else self.modes[0]
        command, status, version = 2, 0, 1
        tag = self.sent[-1][3:7]
        if mode == 'processing':status = 0xfe
        if mode == 'failure':status = 2
        if mode == 'wrong_tag':tag = bytes(4)
        if mode == 'wrong_command':command = 8
        if mode == 'wrong_version':version = 2
        if mode == 'legacy':return bytes(size)
        return (bytes([report, 102, command, status, version]) + tag).ljust(size, b'\0')


class ConfigSaveAckTests(unittest.TestCase):
    def test_processing_and_unrelated_reply_then_matching_ack(self):
        device = SaveDevice(['processing', 'wrong_tag', 'wrong_command', 'success'])
        client = SettingsClient(device, sleep=lambda _: None)
        with patch('studio_settings_protocol.secrets.randbelow', side_effect=[10, 11]):
            self.assertTrue(client.save_flash())
            self.assertTrue(client.save_flash())
        self.assertEqual(len(device.sent), 2)
        self.assertEqual(device.sent[0][:7], bytes([128, 102, 2, 11, 0, 0, 0]))
        self.assertNotEqual(device.sent[0][3:7], device.sent[1][3:7])
        self.assertTrue(all(len(packet) == 64 for packet in device.sent))

    def test_verified_failure_is_not_timeout_or_success(self):
        device = SaveDevice(['failure'])
        with self.assertRaisesRegex(RuntimeError, '저장 실패'):
            SettingsClient(device, sleep=lambda _: None).save_flash()
        self.assertEqual(len(device.sent), 1)

    def test_legacy_wrong_tag_version_and_processing_remain_uncertain(self):
        for mode in ('legacy', 'wrong_tag', 'wrong_command', 'wrong_version', 'processing'):
            with self.subTest(mode=mode):
                device = SaveDevice([mode])
                waits = []
                with self.assertRaisesRegex(TimeoutError, '미확인'):
                    SettingsClient(device, sleep=waits.append).save_flash()
                self.assertEqual(len(device.sent), 1)
                self.assertGreaterEqual(sum(waits), 2)


if __name__ == '__main__':
    unittest.main()
