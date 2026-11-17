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


class TaggedWriteDevice:
    def __init__(self, replies):
        self.replies=iter(replies)
        self.sent=[]

    def send_feature_report(self,packet):
        self.sent.append(bytes(packet))
        return len(packet)

    def get_feature_report(self,report,size):
        command=self.sent[-1][2]
        tag=self.sent[-1][-4:]
        kind=next(self.replies,'stale')
        status={'pending':0xfe,'failure':2,'previous':1}.get(kind,0)
        extra={8:[self.sent[-1][3]],0x19:[],0x22:[1]}.get(command,[1,1])
        if kind=='stale':tag=b'\0'*4
        if kind=='previous':tag=self.sent[-2][-4:]
        return bytes([report,0x66,command,status,*extra]).ljust(60,b'\0')+tag


class TaggedWriteTests(unittest.TestCase):
    def test_correlates_each_write_after_legacy_success_and_pending(self):
        device=TaggedWriteDevice(['match']+['stale','pending','match']*5)
        client=SettingsClient(device,sleep=lambda _:None)
        with patch('studio_settings_protocol.secrets.randbelow',side_effect=range(6)):
            client.save_slot(4,'0123456789ABCDEF')
            client.commit_macros()
            self.assertEqual(client.standby_mode(1),1)
            self.assertEqual(client.dock_disconnect(1),1)
            self.assertEqual(client.usb_serial_hidden(1),1)
        self.assertEqual([p[2] for p in device.sent],[0x22,8,25,0x1c,0x1d,0x21])
        self.assertEqual(device.sent[1][3:20],b'\x04' + b'0123456789ABCDEF')
        self.assertEqual([p[60:] for p in device.sent], [i.to_bytes(4,'little') for i in range(1,7)])

    def test_unsupported_firmware_prevents_restore_and_write_commands(self):
        from studio_backup import restore_all
        device=TaggedWriteDevice([])
        client=SettingsClient(device,sleep=lambda _:None)
        with self.assertRaises(RuntimeError):
            restore_all(client,[dict(index=0,name='Test',fields={},effects={})],{},recovery_path=None)
        with self.assertRaises(RuntimeError):client.save_slot(0,'Test')
        self.assertEqual([p[2] for p in device.sent],[0x22,0x22])

    def test_unconfirmed_write_is_never_retried(self):
        device=TaggedWriteDevice(['match'])
        client=SettingsClient(device,sleep=lambda _:None)
        with self.assertRaises(TimeoutError):client.commit_macros()
        self.assertEqual([p[2] for p in device.sent],[0x22,25])

    def test_same_slot_cannot_accept_previous_tagged_failure(self):
        device=TaggedWriteDevice(['match','match','previous','match'])
        client=SettingsClient(device,sleep=lambda _:None)
        with patch('studio_settings_protocol.secrets.randbelow',side_effect=(4,5,6)):
            client.save_slot(4,'Same')
            client.save_slot(4,'Same')
        self.assertEqual([p[2] for p in device.sent],[0x22,8,8])

    def test_policy_failure_with_matching_tag_preserves_reported_value(self):
        from studio_settings_protocol import PolicySaveError
        device=TaggedWriteDevice(['match','failure'])
        with self.assertRaises(PolicySaveError) as error:
            SettingsClient(device,sleep=lambda _:None).standby_mode(0)
        self.assertEqual(error.exception.current,1)


class MacroPauseTests(unittest.TestCase):
    class Device:
        def __init__(self):
            self.sent=[];self.previous=False;self.reject=False;self.lost=False;self.reads=0
        def send_feature_report(self,packet):
            self.sent.append(bytes(packet));return len(packet)
        def get_feature_report(self,report,size):
            packet=self.sent[-1];self.reads+=1
            if self.lost:return bytes(size)
            payload=packet[3:13]
            if self.previous:
                self.previous=False
                payload=payload[:6]+self.sent[0][9:13]
            return (bytes([report,0x66,packet[2],int(self.reject)])+payload).ljust(size,b'\0')

    def test_renews_in_same_handle_before_next_command_and_rejects_previous_tag(self):
        device=self.Device();client=SettingsClient(device,sleep=lambda _:None)
        with patch('studio_settings_protocol.time.monotonic',return_value=10) as clock, \
             patch('studio_settings_protocol.secrets.token_bytes',side_effect=[b'1111',b'2222',b'3333']):
            client.start_macro_pause();clock.return_value=14
            client.command(4,b'\x01')
            self.assertEqual(len(device.sent),2)
            clock.return_value=15;device.previous=True
            client.command(4,b'\x01');client.end_macro_pause()
        self.assertEqual([(p[2],p[4]) for p in device.sent if p[2]==0x23],[(0x23,1),(0x23,2),(0x23,3)])
        self.assertEqual([p[2] for p in device.sent],[0x23,4,0x23,4,0x23])
        self.assertEqual(device.reads,6)

    def test_rejected_renewal_blocks_next_write_and_still_releases(self):
        device=self.Device();client=SettingsClient(device,sleep=lambda _:None)
        with patch('studio_settings_protocol.time.monotonic',return_value=10) as clock:
            client.start_macro_pause();clock.return_value=45;device.reject=True
            with self.assertRaises(RuntimeError):client.command(11,b'write')
            device.reject=False;client.end_macro_pause()
        self.assertEqual([p[2] for p in device.sent],[0x23]*3)
        self.assertEqual([p[4] for p in device.sent],[1,2,3])
        self.assertIsNone(client._macro_pause_owner)

    def test_lost_acquire_ack_can_release_same_owner_without_legacy_pause(self):
        device=self.Device();client=SettingsClient(device,sleep=lambda _:None)
        device.lost=True
        with self.assertRaises(RuntimeError):client.start_macro_pause()
        device.lost=False;client.end_macro_pause()
        self.assertEqual([(p[2],p[4]) for p in device.sent],[(0x23,1),(0x23,3)])
        self.assertEqual(device.sent[0][5:9],device.sent[1][5:9])

    def test_cancel_during_renewal_blocks_following_write(self):
        device=self.Device();cancelled=False
        client=SettingsClient(device,sleep=lambda _:None,cancel=lambda:cancelled)
        read=device.get_feature_report
        def receive(report,size):
            nonlocal cancelled
            cancelled=True
            return read(report,size)
        with patch('studio_settings_protocol.time.monotonic',return_value=10) as clock:
            client.start_macro_pause();clock.return_value=15
            with patch.object(device,'get_feature_report',side_effect=receive):
                with self.assertRaises(RuntimeError):client.command(11,b'write')
        self.assertEqual([(p[2],p[4]) for p in device.sent],[(0x23,1),(0x23,2)])


if __name__ == '__main__':
    unittest.main()
