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


class StoredFieldsDevice(Fake):
    def __init__(self, fault=None):
        super().__init__([])
        self.fault = fault

    def send_feature_report(self, packet):
        from studio_settings_protocol import encode
        from studio_scope import EDITABLE

        super().send_feature_report(packet)
        command = packet[2]
        if command == 0x0a:
            reply = bytearray(info())
            reply[23:31] = b'SLT1SBR1'
            reply[31:35] = bytes((8, 0, 0, 0))
        elif command == 0x29:
            slot, count = packet[3:5]
            reply = bytearray((132, 102, command, 0, slot, count, 8, 0, 0, 0))
            for fid in packet[5:5 + count]:
                field = next(f for f in EDITABLE.values() if f[0] == fid)
                value = encode(field, 60 if field[1] == 'auto_haptics_lowpass_hz' else 0)
                reply.extend((fid, len(value)))
                reply.extend(value)
            reply = reply.ljust(60, b'\0') + packet[60:64]
            if self.fault == 'revision':reply[6] = 9
            if self.fault == 'status':reply[3] = 1
            if self.fault == 'count':reply[5] -= 1
            if self.fault == 'length':reply[11] += 1
            if self.fault == 'tag':reply[61] ^= 0x01
            if self.fault == 'interference':
                reply[2] = 0x27
                self.fault = None
        else:
            raise AssertionError(f'unexpected command {command:02x}')
        self.replies.append(reply)
        return len(packet)


class Tests(unittest.TestCase):

    def test_stored_fields_use_tagged_bulk_after_positive_slot_info(self):
        from studio_settings_protocol import SettingsClient
        from studio_scope import EDITABLE

        keys = ('auto_haptics_lowpass_hz', 'auto_haptics_enable', 'auto_haptics_gain',
                'auto_haptics_smooth', 'auto_haptics_gate', 'mix_native_level',
                'mix_native_filter', 'ah_dsp_source', 'ah_high_gain')
        device = StoredFieldsDevice()
        client = SettingsClient(device, sleep=lambda _: None)
        slot = client.info(0)
        self.assertTrue(client.bulk_stored_slot)
        self.assertEqual(slot.catalog_revision, 8)
        values = client.read_stored_slot(slot, (EDITABLE[key] for key in keys))
        self.assertEqual(values, dict.fromkeys(keys, 0) | {'auto_haptics_lowpass_hz': 60})
        self.assertEqual([packet[2] for packet in device.sent], [0x0a, 0x29, 0x29])

    def test_stored_fields_reject_bad_replies_without_legacy_reads(self):
        from unittest.mock import Mock
        from studio_backup import backup_all
        from studio_settings_protocol import SettingsClient

        for fault in ('revision', 'status', 'count', 'length', 'tag'):
            with self.subTest(fault=fault):
                device = StoredFieldsDevice(fault)
                client = SettingsClient(device, sleep=lambda _: None)
                client.read_lightbar = Mock(return_value={})
                client.read_rumble = Mock(return_value={})
                client.read_one = Mock(return_value=0)
                with self.assertRaises(TimeoutError if fault == 'tag' else ValueError):
                    backup_all(client, indices=[0])
                expected = [0x0a, 0x29, 0x29] if fault == 'tag' else [0x0a, 0x29]
                self.assertEqual([packet[2] for packet in device.sent], expected)
                self.assertTrue(all(len(call.args) == 1 for call in client.read_one.call_args_list))

    def test_stored_fields_retry_read_after_another_reply_overwrites_it(self):
        from studio_settings_protocol import SettingsClient
        from studio_scope import EDITABLE

        device = StoredFieldsDevice('interference')
        client = SettingsClient(device, sleep=lambda _: None)
        slot = client.info(0)
        values = client.read_stored_slot(slot, [EDITABLE['auto_haptics_enable']])
        self.assertEqual(values, {'auto_haptics_enable': 0})
        self.assertEqual([packet[2] for packet in device.sent], [0x0a, 0x29, 0x29])

    def test_delete_checks_capability_and_slot_then_verifies_empty(self):
        from unittest.mock import Mock
        from studio_settings_protocol import SettingsClient

        client = SettingsClient(Fake([]))
        client.require_write_tags = Mock()
        client.catalog_page = Mock(return_value=(9, [Slot(2, 'saved', 'Changed')]))
        client._tagged_write = Mock(return_value=bytes((0x66, 0x28, 0, 2)))
        client.info = Mock(return_value=Slot(2, 'empty'))
        slot = Slot(2, 'saved', 'Original', catalog_revision=9)
        client.slot_delete_supported = False
        with self.assertRaises(RuntimeError):
            client.delete_slot(slot)
        client.catalog_page.assert_not_called()
        client.slot_delete_supported = True
        with self.assertRaises(RuntimeError):
            client.delete_slot(slot)
        client.catalog_page.return_value = (10, [Slot(2, 'saved', 'Original')])
        with self.assertRaises(RuntimeError):
            client.delete_slot(slot)
        client._tagged_write.assert_not_called()
        client.catalog_page.return_value = (9, [slot])
        client.delete_slot(slot)
        self.assertEqual(client._tagged_write.call_args.args, (0x28, b'\x02\x09\0\0\0'))
        client.info.assert_called_once_with(2)

    def client(self, replies):
        d = Fake(replies)
        return (StudioClient(d, sleep=lambda _: None), d)

    def test_names_and_empty(self):
        c, d = self.client([info(name='테스트'), info(1, 0)])
        self.assertEqual(c.info(0).name, '테스트')
        self.assertEqual(c.info(1).label(), '02 · Empty')
        self.assertFalse(c.bulk_stored_slot)
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

    def test_single_unavailable_legacy_slot_does_not_hide_following_slots(self):
        c,d=self.client([info(i,status=int(i==9)) for i in range(32)])
        rows=c.slots()
        self.assertEqual(len(rows),32)
        self.assertEqual(rows[9].state,'unavailable')
        self.assertEqual(rows[10].state,'saved')

    def test_bulk_slot_catalog_restarts_if_a_slot_changes_between_pages(self):
        c,d=self.client([info()[:23]+b'SLT1'+bytes(37)])
        original=d.get_feature_report
        pages=[]
        def reply(report,length):
            request=d.sent[-1]
            if request[2]==10:return original(report,length)
            start=request[3]
            pages.append(start)
            count=min(3,32-start)
            revision=1 if len(pages)==1 else 2
            rows=(b'\x01'+b'Profile'.ljust(16,b'\0'))*count
            return (bytes([132,102,0x27,0,start,count])+revision.to_bytes(4,'little')+rows).ljust(61,b'\0')+request[4:7]
        d.get_feature_report=reply
        rows=c.slots()
        self.assertEqual(rows,[Slot(i,'saved','Profile') for i in range(32)])
        self.assertEqual({slot.catalog_revision for slot in rows},{2})
        self.assertEqual(pages,[0,3]+list(range(0,32,3)))

    def test_rejection(self):
        c, d = self.client([info(), activate(1)])
        with self.assertRaises(RuntimeError):
            c.activate(0)

class ProfileTests(unittest.TestCase):

    def test_profile_state_reads_native_mix_level_only_in_mix(self):
        mode=lambda value:bytes((129,102,4,0x12,value))
        level=bytes((129,102,4,0x55,60))
        source=bytes((129,102,4,0x64,0))
        for current in (0,1,2):
            fields = {0: [], 1: [level, source], 2: [source]}[current]
            replies = [self.reply(), mode(current), *fields, self.reply()]
            device=Fake(replies)
            state=StudioClient(device,sleep=lambda _:None).profile_state()
            self.assertEqual(state.get('mix_native_level'),60 if current==1 else None)
            self.assertEqual(state.get('ah_dsp_source'), 0 if current in (1, 2) else None)
            self.assertEqual(len(device.sent), 3 + len(fields))

    def test_extended_snapshot_is_one_request_and_default_profile_stays_legacy(self):
        extended=self.reply()[:22]+b'\x02SLP2'+bytes((1,75,1))+bytes(34)
        device=Fake([extended,extended])
        c=StudioClient(device,sleep=lambda _:None)
        self.assertEqual(c.profile_state(),dict(index=3,edited=True,name='Audio Haptics',
            mute_macro=True,auto_haptics_enable=1,mix_native_level=75,ah_dsp_source=1))
        self.assertEqual(len(device.sent),1)
        self.assertEqual(c.profile(),dict(index=3,edited=True,name='Audio Haptics'))

    def test_speaker_automute_extension_preserves_profile_framing(self):
        packet = self.reply()[:22]+b'\x02SLP2'+bytes((1,75,0))+bytes(16)+bytes((0xA1,))+bytes(17)
        device = Fake([packet])
        state = StudioClient(device, sleep=lambda _:None).profile_state()
        self.assertIs(state['auto_mute_mix'], True)
        self.assertIs(state['auto_mute_replace'], False)
        self.assertEqual(len(device.sent), 1)

    def test_revision_extension_accepts_only_the_matching_tag_and_keeps_legacy_reply(self):
        from unittest.mock import patch
        packet=self.reply()[:30]+b'REV1'+bytes.fromhex('01000000aabbccdd')
        d=Fake([packet+bytes(4),packet+b'OLD!',packet+b'NEW!',self.reply()])
        c=StudioClient(d,sleep=lambda _:None)
        with patch('studio_slots.secrets.randbelow',return_value=int.from_bytes(b'NEW!','little')-1):
            self.assertEqual(c.profile(include_revision=True)['config_token'],'01000000aabbccdd')
            self.assertNotIn('config_token',c.profile(include_revision=True))
        self.assertEqual(d.sent[0][:9],b'\x80\x66\x67R1NEW!')

    def test_legacy_profile_state_reuses_supplied_header(self):
        device=Fake([bytes((129,102,4,0x12,0)),self.reply()])
        c=StudioClient(device,sleep=lambda _:None)
        header=dict(index=3,edited=True,name='Audio Haptics')
        self.assertEqual(c.profile_state(header),dict(header,auto_haptics_enable=0))
        self.assertEqual([packet[2] for packet in device.sent],[4,103])

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
