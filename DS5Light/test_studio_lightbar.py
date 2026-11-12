"""Fixed lightbar: mock wire and local Tk editing only; no hardware writes."""
import copy,unittest
from unittest.mock import patch
import test_studio_settings as fixture
from studio_settings_protocol import SettingsClient,encode,PartialApplyError
from studio_document import SettingsDocument
from studio_backup import validate_backup,restore_all,backup_all
from studio_slots import Slot
from studio_fields import FIELDS
from studio_scope import LIGHTBAR_FIELDS

class Device(fixture.Device):
    def __init__(self,mode='good'):
        super().__init__();self.mode=mode;self.values.update(lightbar_fixed=0,lightbar_rgb=0x3366cc)
    def send_feature_report(self,p):
        result=super().send_feature_report(p)
        if p[2]==12 and p[3:6]==b'\x02\xc1\xc2':
            raw=bytearray(self.reply)
            if self.mode=='status':raw[3]=1
            if self.mode=='count':raw[4]=1
            if self.mode=='id':raw[5]=0xc0
            if self.mode=='length':raw[9]=3
            if self.mode=='fixed':raw[7]=2
            if self.mode=='rgb':raw[13]=1
            if self.mode=='short':raw=raw[:10]
            self.reply=bytes(raw)
        return result

class ProtocolTests(unittest.TestCase):
    def client(self,mode='good'):
        d=Device(mode);return SettingsClient(d,sleep=lambda _:None),d
    def test_strict_bulk_probe_and_little_endian(self):
        c,d=self.client();self.assertEqual(c.read_lightbar(),dict(lightbar_fixed=0,lightbar_rgb=0x3366cc))
        self.assertEqual(d.sent[0][:6],b'\x80\x66\x0c\x02\xc1\xc2')
        self.assertEqual(encode(FIELDS['lightbar_rgb'],0x3366cc),b'\xcc\x66\x33\x00')
        self.assertEqual(encode(FIELDS['lightbar_rgb'],0),bytes(4))
    def test_invalid_probe_blocks_writes_without_single_fallback(self):
        for mode in ('status','count','id','length','fixed','rgb','short'):
            with self.subTest(mode=mode):
                c,d=self.client(mode);self.assertFalse(c.read_lightbar())
                with self.assertRaises(ValueError):c.write_fields({'lightbar_fixed':1},d.values)
                self.assertFalse(any(p[2] in (1,11) for p in d.sent))
                self.assertFalse(any(p[2]==4 and p[3] in (0xc1,0xc2) for p in d.sent))
    def test_enable_is_one_bulk_rgb_off_fixed_and_verified(self):
        c,d=self.client();baseline=dict(d.values)
        changes=dict(lightbar_fixed=1,lightbar_off=0,lightbar_rgb=0x3366cc)
        self.assertEqual(c.write_fields(changes,baseline),changes)
        writes=[p for p in d.sent if p[2]==11];self.assertEqual(len(writes),1)
        self.assertEqual(writes[0][3:17],b'\x03\xc2\x04\xcc\x66\x33\x00\x19\x01\x00\xc1\x01\x01\x00'[:14])
        self.assertFalse(any(p[2]==2 for p in d.sent))
    def test_ranges_and_partial_ack_no_retry(self):
        for key,value in (('lightbar_fixed',2),('lightbar_rgb',-1),('lightbar_rgb',0x1000000)):
            with self.assertRaises(ValueError):encode(FIELDS[key],value)
        c,d=self.client();d.partial=True
        with self.assertRaises(PartialApplyError):c.write_fields({'lightbar_fixed':1},d.values)
        self.assertEqual(sum(p[2]==11 for p in d.sent),1)
    def test_rgb_readback_requires_exact_integer_equality(self):
        class Corrupt(Device):
            def send_feature_report(self,p):
                result=super().send_feature_report(p)
                if p[2]==12 and p[3:6]==b'\x02\xc1\xc2' and any(packet[2]==11 for packet in self.sent):
                    raw=bytearray(self.reply);raw[10]^=1;self.reply=bytes(raw)
                return result
        d=Corrupt();c=SettingsClient(d,sleep=lambda _:None)
        with self.assertRaises(PartialApplyError):c.write_fields({'lightbar_rgb':0x3366cc},d.values)
        self.assertEqual(sum(p[2]==11 for p in d.sent),1)

class DocumentTests(unittest.TestCase):
    def test_legacy_import_disables_fixed_preserves_rgb_and_other_values(self):
        d=SettingsDocument();d.load(dict(lightbar_fixed=1,lightbar_rgb=0x123456,lightbar_off=0,audio_buffer_length=48))
        d.import_json({'cfgVersion':19,'fields':{'audio_buffer_length':48}})
        self.assertEqual(d.values,dict(lightbar_fixed=0,lightbar_rgb=0x123456,lightbar_off=0,audio_buffer_length=48))
        self.assertEqual(d.export_json()['cfgVersion'],20)
    def test_unsupported_import_rejected_atomically(self):
        d=SettingsDocument();d.load({'lightbar_off':0});before=dict(d.values)
        with self.assertRaises(ValueError):d.import_json({'fields':{'lightbar_fixed':1,'lightbar_rgb':0}})
        self.assertEqual(d.values,before)
    def test_legacy_backup_default_and_extension_backup_roundtrip(self):
        data=dict(slots=[dict(index=0,valid=True,name='A',fields={'lightbar_off':0})])
        rows,_=validate_backup(data);self.assertEqual(rows[0]['fields']['lightbar_fixed'],0)
        self.assertNotIn('lightbar_rgb',rows[0]['fields'])
        data['slots'][0]['fields'].update(lightbar_fixed=1,lightbar_rgb=0x3366cc)
        self.assertEqual(validate_backup(data)[0][0]['fields']['lightbar_rgb'],0x3366cc)
    def test_old_backup_restore_preserves_rgb_and_restores_live_configuration(self):
        class Client:
            cancel=staticmethod(lambda:False)
            def __init__(self):
                self.values=dict(lightbar_fixed=1,lightbar_rgb=0x123456,lightbar_off=0,auto_haptics_gain=80,audio_buffer_length=48)
                self.saved={}
            def read_fields(self):return dict(self.values),[]
            def read_one(self,field):
                from studio_settings_protocol import EdgeSerialUnsupported
                raise EdgeSerialUnsupported('Unsupported')
            def read_macros(self):return {}
            def command(self,*args):return b'\x66\x1a\x00'
            def write_fields(self,values,current,**kwargs):self.values.update(values)
            def save_slot(self,index,name):self.saved[index]=dict(self.values)
        c=Client();before=dict(c.values)
        rows,macros=validate_backup(dict(slots=[dict(index=0,valid=True,name='Legacy',fields={'auto_haptics_gain':100})]))
        restore_all(c,rows,macros)
        self.assertEqual(c.saved[0]['lightbar_fixed'],0);self.assertEqual(c.saved[0]['lightbar_rgb'],0x123456)
        self.assertEqual(c.saved[0]['audio_buffer_length'],48);self.assertEqual(c.values,before)
    def test_slot_backup_includes_verified_fields(self):
        class Client:
            def read_lightbar(self):return dict(lightbar_fixed=1,lightbar_rgb=0x3366cc)
            def slots(self):return [Slot(0,'saved','RGB')]
            def read_one(self,field,slot=None):
                if field[1]=='usb_gamepad_mode':
                    from studio_settings_protocol import USBModeUnsupported
                    raise USBModeUnsupported('Unsupported')
                return {'lightbar_fixed':1,'lightbar_rgb':0x3366cc}.get(field[1],fixture.defaults()[field[1]])
            def read_macros(self):return {}
        saved=backup_all(Client())['slots'][0]
        self.assertEqual(saved['cfgVersion'],20);self.assertEqual(saved['fields']['lightbar_rgb'],0x3366cc)

class UITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor
    def test_toggle_clears_off_locally_and_picker_stages_only(self):
        ui=self.editor();ui.doc.values['lightbar_off']=1;ui.doc.baseline['lightbar_off']=1
        ui.select_category(0)
        with patch.object(ui,'with_client') as wire:
            ui.vars['lightbar_fixed'].set(True)
            self.assertEqual(ui.doc.changes['lightbar_off'],0)
            self.assertEqual(ui.doc.changes['lightbar_fixed'],1)
            with patch('studio_lightbar.rgb_palette',return_value=0x3366cc):ui.choose_lightbar_colour()
            wire.assert_not_called()
        self.assertEqual(ui.doc.changes['lightbar_rgb'],0x3366cc)
        self.assertIn('#3366CC',ui.field_views['lightbar_rgb'][1][0].cget('text'))
    def test_unsupported_controls_disabled_and_read_sync_does_not_edit(self):
        ui=self.editor()
        for k in LIGHTBAR_FIELDS:ui.doc.values.pop(k);ui.doc.baseline.pop(k)
        ui.select_category(0)
        self.assertFalse(ui.field_views['lightbar_fixed'][1][0].enabled)
        self.assertEqual(str(ui.field_views['lightbar_rgb'][1][0].cget('state')),'disabled')
        ui.doc.values.update(lightbar_fixed=1,lightbar_rgb=0xabcdef)
        ui.doc.baseline.update(lightbar_fixed=1,lightbar_rgb=0xabcdef)
        ui.refresh_read_values();self.assertFalse(ui.doc.changes)
        self.assertIn('#ABCDEF',ui.field_views['lightbar_rgb'][1][0].cget('text'))
    def test_palette_cancel_does_not_stage(self):
        ui=self.editor();ui.select_category(0);before=dict(ui.doc.values)
        with patch('studio_lightbar.rgb_palette',return_value=None):ui.choose_lightbar_colour()
        self.assertEqual(ui.doc.values,before)
    def test_lost_support_disables_cached_controls(self):
        ui=self.editor();ui.select_category(0);before=dict(ui.doc.values)
        ui.lightbar_supported=False;ui.refresh_read_values()
        self.assertFalse(ui.field_views['lightbar_fixed'][1][0].enabled)
        self.assertEqual(str(ui.field_views['lightbar_rgb'][1][0].cget('state')),'disabled')
        self.assertEqual('—',ui.field_views['lightbar_rgb'][1][0].cget('text'))
        self.assertEqual(ui.doc.values,before)
    def test_actual_rgb_palette_confirm_is_local(self):
        from studio_lightbar import rgb_palette
        from tkinter import ttk
        def walk(parent):
            for child in parent.winfo_children():
                yield child;yield from walk(child)
        def choose(dialog,owner,accept):
            entries=[w for w in walk(dialog) if isinstance(w,ttk.Entry) and str(w.cget('width'))=='4']
            self.assertEqual(len(entries),3)
            for entry,value in zip(entries,(51,102,204)):
                dialog.setvar(str(entry.cget('textvariable')),str(value))
            accept.invoke()
        with patch('studio_lightbar._show',side_effect=choose):
            self.assertEqual(rgb_palette(self.root,0),0x3366cc)

if __name__=='__main__':unittest.main()
