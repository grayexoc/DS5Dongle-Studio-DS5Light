"""Experimental Studio tests: local edits, strict wire parsing, native layouts."""
import copy,struct,time,unittest
from unittest.mock import patch
from studio_fields import FIELDS,SECTIONS
from studio_scope import EDITABLE,CONSTRUCTION,REMOVED,trigger_display,trigger_raw
from studio_reference import REFERENCE,DEFAULTS
from studio_help import LABELS,help_text,options
from studio_settings_protocol import SettingsClient,encode,decode,PartialApplyError
from studio_document import SettingsDocument
from studio_records import effect_states,macro_records,build_effect
from studio_backup import backup_all,validate_backup
from studio_slots import Slot
import test_modified_ui as fixtures

def defaults():
    out={}
    for key,f in FIELDS.items():
        kind=f[4]
        if kind=='number':out[key]=f[5][0]
        elif kind=='select':out[key]=options(f)[0][0]
        elif kind=='macros':out[key]=0xffffffff
        else:out[key]=0
    out['auto_haptics_lowpass_hz']=80;out['ah_xover_hz']=0;out['auto_haptics_enable']=1
    return out

class Device:
    def __init__(self):self.values=defaults();self.sent=[];self.reply=bytes(64);self.bad_length=False;self.partial=False
    def send_feature_report(self,p):
        self.sent.append(bytes(p));cmd=p[2];payload=p[3:];body=bytearray([0x66,cmd,0,0])
        if cmd==2:
            self.reply=(bytes([0x84,0x66,2,0,1])+payload[:4]).ljust(64,b'\0');return len(p)
        if cmd==12:
            n=payload[0];body[3]=n
            for fid in payload[1:n+1]:
                f=next(f for f in FIELDS.values() if f[0]==fid);data=encode(f,self.values[f[1]])
                body.extend([fid,len(data)+(1 if self.bad_length else 0)]);body.extend(data)
        elif cmd==4:
            fid=payload[0];f=next(f for f in FIELDS.values() if f[0]==fid);body=bytearray([0x66,4,fid])+encode(f,self.values[f[1]])
        elif cmd==11:
            n=payload[0];off=1;body[3]=n
            for _ in range(n):
                fid,size=payload[off:off+2];off+=2;f=next(f for f in FIELDS.values() if f[0]==fid);self.values[f[1]]=decode(f,payload[off:off+size]);off+=size
            if self.partial:body[2]=1;body[3]=0
        elif cmd==1:
            fid=payload[0];f=next(f for f in FIELDS.values() if f[0]==fid);self.values[f[1]]=decode(f,payload[1:1+struct.calcsize('<'+{'u8':'B','u16':'H','u32':'I','f32':'f'}[f[2]])])
        self.reply=(bytes([0x81])+body).ljust(64,b'\0');return len(p)
    def get_feature_report(self,r,n):return self.reply

class SchemaTests(unittest.TestCase):
    def test_edge_serial_requires_explicit_firmware_support(self):
        from studio_settings_protocol import needs_reconnect
        client=SettingsClient(None)
        with patch.object(client,'command',return_value=b'\x66\x0c\x01\x00') as command:
            self.assertEqual(client.read_fields([FIELDS['disable_usb_sn']]),({},['disable_usb_sn']))
            command.assert_called_once()
            self.assertEqual(command.call_args.args,(12,b'\x01\xc7'))
        with patch.object(client,'command',return_value=b'\x66\x0c\x00\x01\xc7\x01\x00'):
            self.assertEqual(client.read_fields([FIELDS['disable_usb_sn']]),({'disable_usb_sn':0},[]))
        self.assertTrue(needs_reconnect({'disable_usb_sn':0},{'disable_usb_sn':1}))
        self.assertFalse(needs_reconnect({}, {'disable_usb_sn':1}))

    def test_slot_restore_uses_serial_storage_even_when_live_edge_is_unavailable(self):
        from studio_backup import restore_all
        class Client:
            cancel=staticmethod(lambda:False)
            def __init__(self):self.stored=1;self.saved=[]
            def read_fields(self):return {},['disable_usb_sn']
            def read_one(self,field):
                self.assert_storage(field)
                return self.stored
            def assert_storage(self,field):
                if field[0]!=0xc8:raise AssertionError(field)
            def read_macros(self):return {}
            def command(self,*args):return bytes((0x66,26,0))
            def write_fields(self,values,baseline,*,profile_snapshot):
                if not profile_snapshot:raise AssertionError('expected profile snapshot')
                self.stored=values['disable_usb_sn']
            def save_slot(self,index,name):self.saved.append((index,self.stored))
        client=Client()
        rows=[dict(index=0,name='Edge',fields={'disable_usb_sn':1},effects={}),
              dict(index=1,name='Legacy',fields={},effects={})]
        self.assertEqual(restore_all(client,rows,{}),[0,1])
        self.assertEqual(client.saved,[(0,1),(1,0)])
        self.assertEqual(client.stored,1)

    def test_full_stable_registry_and_descriptions(self):
        self.assertEqual(len(FIELDS),143);self.assertEqual(len({f[0] for f in FIELDS.values()}),143)
        self.assertEqual(set(FIELDS),set(LABELS));self.assertFalse(any('experimental' in s['title'].lower() for s in SECTIONS))
        for key,f in FIELDS.items():
            text=help_text(key);self.assertIn(f[3],text);self.assertNotIn('('+key+')',text)
            if key in REFERENCE:self.assertIn('추천 시작값',text)
            else:self.assertNotIn('추천 시작값',text)
            self.assertEqual(decode(f,encode(f,defaults()[key])),defaults()[key])
    def test_bad_values_and_cross_field_rules(self):
        for value in (float('nan'),float('inf'),True,'100',-1,201):
            with self.assertRaises(ValueError):encode(FIELDS['auto_haptics_gain'],value)
        d=SettingsDocument();d.load(defaults())
        with self.assertRaises(ValueError):d.import_json({'fields':{'ah_xover_hz':90,'auto_haptics_lowpass_hz':80}})
    def test_edit_revert_never_contacts_hid(self):
        d=SettingsDocument();d.load(defaults())
        with patch('studio_slots.devices') as call:
            d.values['auto_haptics_gain']=100;self.assertTrue(d.dirty);d.revert();self.assertFalse(d.dirty);d.import_json({'settings':{'auto_haptics_gain':120}})
        call.assert_not_called();self.assertEqual(d.changes,{'auto_haptics_gain':120})
    def test_import_is_atomic_and_excludes_unknown_and_macro_mask(self):
        d=SettingsDocument();d.load(defaults());before=copy.deepcopy(d.values)
        with self.assertRaises(ValueError):d.import_json({'fields':{'auto_haptics_gain':100},'macros':{'0':[0]}})
        self.assertEqual(d.values,before)
        d.import_json({'fields':{'auto_haptics_gain':100,'macro_disable':0,'bt_flush_timeout':4}})
        self.assertEqual(d.values['macro_disable'],0xffffffff);self.assertNotIn('bt_flush_timeout',d.values)
    def test_effect_builder_and_macro_wire_bits(self):
        b=build_effect('vibration',2,8,50,35);self.assertEqual(b[0],0x26);self.assertEqual(b[9],35)
        self.assertEqual(b[1]|b[2]<<8,sum(1<<i for i in range(2,9)))
        r=macro_records([dict(index=2,chord=1<<24,gesture=128,keys=[224,4],label='Test')])['2']
        self.assertEqual(int.from_bytes(bytes(r[:4]),'little'),1<<24);self.assertEqual(r[4],128);self.assertEqual(r[7:9],[224,4]);self.assertEqual(len(r),35)
    def test_legacy_slot_raw_fields_survive_full_backup_and_restore_validation(self):
        class Client(SettingsClient):
            def read_lightbar(self,refresh=False):return {'lightbar_fixed':0,'lightbar_rgb':0}
            def read_rumble(self,refresh=False):return {'rumble_gain':100,'rumble_release':0}
            def slots(self):return [Slot(0,'saved','Legacy'),Slot(1,'saved','Custom')]
            def read_macros(self):return {}
            def command(self,command,payload,report=0x81,echo=b'',echo_offset=3,**kwargs):
                if command==12 and payload==b'\x01\xc8':return b'\x66\x0c\x00\x01\xc8\x01\x00'
                if command==12 and payload==b'\x01\xc5':return b'\x66\x0c\x00\x01\xc5\x01\x00'
                if command==12 and payload==b'\x01\xc6':return b'\x66\x0c\x00\x01\xc6\x01\x00'
                assert command==13 and report==0x84 and echo==payload
                slot,fid=payload
                field=FIELDS['disable_usb_sn'] if fid==0xc8 else next(f for f in EDITABLE.values() if f[0]==fid)
                key=field[1]
                if slot==0:
                    size=struct.calcsize('<'+{'u8':'B','u16':'H','u32':'I','f32':'f'}[field[2]])
                    value=b'\xff'*size if key!='lightbar_rgb' else b'\xff\xff\xff\0'
                else:
                    value=encode(field,custom[key])
                return b'\x66\x0d\0'+payload+value
        custom={key:defaults()[key] for key in EDITABLE}
        custom.update(rumble_gain=175,rumble_release=2,rumble_mode=2,lightbar_rgb=0x3366cc,usb_gamepad_mode=1,disable_usb_sn=1,
                      auto_haptics_lowpass_hz=20,ah_xover_hz=200,
                      gyro_natural_x10=254,gyro_natural_y_x10=230,gyro_scale_trim_x100=1)
        rows,_=validate_backup(backup_all(Client(None)))
        self.assertEqual(set(rows[0]['fields']),{k for k in EDITABLE if not k.startswith('ce_')})
        for key,value in dict(rumble_gain=100,rumble_release=0,rumble_mode=0,haptics_gain=1.0,
                              ah_xover_hz=0,haptics_aa=1,stick_mouse_curve=18,
                              macro_disable=0xffffffff).items():
            self.assertEqual(rows[0]['fields'][key],value,key)
        self.assertEqual(rows[1]['fields'],{k:v for k,v in custom.items() if not k.startswith('ce_')})

    def test_backup_rejects_duplicates_and_unknown_active_actions(self):
        row=dict(index=0,valid=True,name='A',fields={'auto_haptics_gain':100})
        self.assertEqual(len(validate_backup(dict(slots=[row]))[0]),1)
        with self.assertRaises(ValueError):validate_backup(dict(slots=[row,row]))
        row['fields']['macro_disable']=0
        with self.assertRaises(ValueError):validate_backup(dict(slots=[row]))

class ProtocolTests(unittest.TestCase):
    def test_bulk_roundtrip_and_only_changed_fields(self):
        dev=Device();c=SettingsClient(dev,sleep=lambda _:None);values,missing=c.read_fields();self.assertFalse(missing);self.assertEqual(len(values),len(EDITABLE))
        c.write_fields({'auto_haptics_gain':100},values)
        self.assertEqual(dev.values['auto_haptics_gain'],100)
        writes=[p for p in dev.sent if p[2]==11];self.assertEqual(len(writes),1);self.assertEqual(writes[0][3],1)
        self.assertTrue(all(len(p)==64 for p in dev.sent))
    def test_partial_write_is_not_retried(self):
        dev=Device();c=SettingsClient(dev,sleep=lambda _:None);c.bulk=True;dev.partial=True
        with self.assertRaises(PartialApplyError):c.write_fields({'auto_haptics_gain':100},dev.values)
        self.assertEqual(sum(p[2]==11 for p in dev.sent),1)
    def test_malformed_bulk_falls_back_to_verified_individual_reads(self):
        dev=Device();dev.bad_length=True;c=SettingsClient(dev,sleep=lambda _:None);out,missing=c.read_fields([FIELDS['auto_haptics_gain']]);self.assertFalse(missing);self.assertEqual(out['auto_haptics_gain'],0)
    def test_cancel_prevents_any_packet(self):
        dev=Device();c=SettingsClient(dev,sleep=lambda _:None,cancel=lambda:True)
        with self.assertRaises(RuntimeError):c.read_fields([FIELDS['auto_haptics_gain']])
        self.assertFalse(dev.sent)
    def test_flash_save_sent_once(self):
        dev=Device();c=SettingsClient(dev,sleep=lambda _:None);c.save_flash();self.assertEqual([p[2] for p in dev.sent],[2])

class NativeUITests(unittest.TestCase):
    setUp=fixtures.ModifiedUITests.setUp
    tearDown=fixtures.ModifiedUITests.tearDown
    def editor(self):
        e=self.ui.studio_settings
        with patch.object(e,'read'):self.ui.select_tab(2)
        e.doc.load(defaults());e.loaded=True;e.write_ready=True;e.pico_recognized=True;e.select_category(1);return e
    def test_lazy_creation_and_right_aligned_tab(self):
        self.assertFalse(self.ui.studio_settings.built);self.root.deiconify();self.root.update();tabs=self.ui.tabs
        self.assertEqual(tabs._left(2)+tabs.tab_width,tabs.winfo_width());e=self.editor();self.assertTrue(e.built)
    def test_staging_notice_and_no_hid_during_edit(self):
        e=self.editor()
        with patch.object(e,'with_client') as call:
            e.vars['auto_haptics_gain'].set('100');self.assertIn('변경',e.notice.get());self.assertEqual(e.doc.changes['auto_haptics_gain'],100);e.revert()
        call.assert_not_called();self.assertFalse(e.doc.dirty)
    def test_all_categories_and_search_keep_ui_inside_viewport(self):
        e=self.editor();self.root.deiconify();self.root.update()
        for i in range(6):
            e.select_category(i);self.root.update_idletasks()
            self.assertLessEqual(e.body.winfo_reqwidth(),e.canvas.winfo_width()+1)
        e.search.set('세기');e.render_fields();self.assertTrue(e.vars)
    def test_busy_and_readonly_disable_apply(self):
        e=self.editor();e.changed('auto_haptics_gain',100);e.write_ready=False;e.update_state();self.assertIn('disabled',e.apply_button.state());e.write_ready=True;e.busy=True;e.render_fields();self.assertIn('disabled',e.apply_button.state())
    def test_help_contains_recommendation_and_reason(self):
        e=self.editor();self.assertTrue(e.tips);self.assertIn('추천 시작값',help_text('auto_haptics_gain'));self.assertIn('추천 시작값: 체크',help_text('disable_mic'))



class RestoreSafetyTests(unittest.TestCase):
    def test_restore_keeps_live_config_and_resumes_macros_after_failure(self):
        from studio_backup import restore_all
        class Client:
            def __init__(self):self.values={'auto_haptics_gain':100};self.saves=[];self.suspended=False;self.cancel=lambda:False
            def read_fields(self):return dict(self.values),[]
            def read_one(self,field):
                from studio_settings_protocol import EdgeSerialUnsupported
                raise EdgeSerialUnsupported('Unsupported')
            def read_effects(self):return {'0':[],'1':[]}
            def read_macros(self):return {}
            def command(self,cmd,payload,report):self.suspended=bool(payload[0]);return bytes([102,cmd,0,0])
            def write_fields(self,values,current,**kwargs):self.values=dict(values)
            def save_slot(self,index,name):
                if index==1:raise RuntimeError('save failed')
                self.saves.append(index)
        c=Client();rows=[dict(index=0,name='A',fields={'auto_haptics_gain':50},effects={}),dict(index=1,name='B',fields={'auto_haptics_gain':80},effects={})]
        with self.assertRaises(RuntimeError):restore_all(c,rows,{})
        self.assertEqual(c.values,{'auto_haptics_gain':100});self.assertFalse(c.suspended);self.assertEqual(c.saves,[0])
    def test_cancel_blocks_flash_and_reconnect(self):
        d=Device();c=SettingsClient(d,sleep=lambda _:None,cancel=lambda:True)
        with self.assertRaises(RuntimeError):c.save_flash()
        with self.assertRaises(RuntimeError):c.reconnect_usb()
        self.assertFalse(d.sent)
    def test_unknown_motion_macro_stays_unmodified(self):
        raw=[0]*35;raw[4]=144
        self.assertEqual(macro_records({'0':raw}),{})
    def test_every_option_has_korean_function_description(self):
        from studio_help import DESCRIPTIONS
        self.assertEqual(set(DESCRIPTIONS),set(FIELDS))


class RevisionTests(unittest.TestCase):
    def test_scoped_protocol_never_targets_excluded_fields(self):
        d=Device();c=SettingsClient(d,sleep=lambda _:None);c.read_fields()
        ids={f[0] for f in EDITABLE.values()}
        for packet in d.sent:
            if packet[2]==12:self.assertTrue(set(packet[4:4+packet[3]])<=ids)
        for key in CONSTRUCTION|REMOVED:
            count=len(d.sent)
            with self.assertRaises(ValueError):c.write_fields({key:0},{})
            with self.assertRaises(ValueError):c.read_fields([FIELDS[key]])
            with self.assertRaises(ValueError):c.read_one(FIELDS[key])
            self.assertEqual(len(d.sent),count)
    def test_import_cannot_revive_construction_effects(self):
        d=SettingsDocument();d.load(defaults());d.import_json({'fields':{'at_mode':2,'effect_leak_volume':50,'auto_haptics_gain':120},'effects':{'r2':[{'bytes':[0]*11}]}})
        self.assertEqual(d.changes,{'auto_haptics_gain':120,'at_mode':2});self.assertFalse(d.effects);self.assertFalse(d.export_json()['effects'])
        self.assertFalse(set(d.export_json()['fields'])&(CONSTRUCTION|REMOVED))
    def test_trigger_scale_is_lossless_for_all_firmware_steps(self):
        for raw in range(11):self.assertEqual(trigger_raw(trigger_display(raw)),raw)
        self.assertEqual(trigger_display(0),10);self.assertEqual(trigger_display(10),1)
    def test_construction_record_apis_do_not_send(self):
        d=Device();c=SettingsClient(d,sleep=lambda _:None)
        with self.assertRaises(RuntimeError):c.read_effects()
        with self.assertRaises(RuntimeError):c.write_effect(0,0,dict(bytes=[0]*11))
        with self.assertRaises(RuntimeError):c.history()
        self.assertFalse(d.sent)
    def test_profile_import_cannot_replace_existing_motion(self):
        d=SettingsDocument();d.load(defaults());old=[0]*35;old[4]=144
        d.macros={'0':old[:]};d.macro_baseline={'0':old[:]}
        d.import_json(dict(macros=[dict(index=0,chord=1,keys=[4])]))
        self.assertEqual(d.macros['0'],old);self.assertFalse(d.macro_changes)
    def test_reference_and_default_markers(self):
        from studio_help import reference_point
        self.assertEqual(reference_point('auto_haptics_gain'),(80,'추천'))
        self.assertEqual(reference_point('trigger_reduce'),(0,'기본'))
        for key,f in EDITABLE.items():
            if f[4]=='number':self.assertIsNotNone(reference_point(key)[0],key)
    def test_macro_roundtrip_and_dependencies(self):
        from studio_macro_tools import normalize_macro,structured_macros
        r=macro_records([dict(index=3,chord=1,keys=[224,4],label='Map',rel_order=27)])
        self.assertEqual(macro_records(structured_macros(r)),r)
        a=[0]*35;a[4]=160;a[5]=16;a[17]=3;normalize_macro(a)
        self.assertEqual(a[5]&2,2);self.assertEqual(a[5]&16,0);self.assertEqual(a[17],0)
        a[4]=128;a[5]=31;normalize_macro(a);self.assertEqual(a[5],4)
    def test_macro_stick_threshold_120(self):
        r=macro_records([dict(index=0,gesture=160,stick_thresh=120)])
        self.assertEqual(r['0'][18],120)
    def test_passive_report_parser(self):
        from studio_macro_tools import input_snapshot
        d=[0]*64;d[0]=1;d[8]=8;d[10]=4|16
        s=input_snapshot(d);self.assertEqual(s['mask'],(1<<18)|(1<<19))
        self.assertIsNone(input_snapshot([0]*64))
    def test_html_scope_and_explicit_apply(self):
        from studio_html_export import profile_html
        d=SettingsDocument();d.load(defaults());s=profile_html(d.export_json())
        self.assertNotIn('"effect_leak_volume"',s);self.assertIn('"at_mode"',s);self.assertNotIn('"macro_disable"',s)
        self.assertIn('confirm(',s);self.assertIn('cfg[3]!==19',s)

class RevisionUITests(NativeUITests):
    def test_option_groups_preserve_profile_and_do_not_send(self):
        e=self.editor();before=copy.deepcopy(e.doc.values)
        with patch.object(e,'with_client') as send:
            for category in (1,3,2,0):
                e.select_category(category)
                for group,rows,button,conditional,note in e._option_groups:
                    if button:
                        e.toggle_option_group(group);e.toggle_option_group(group)
                e.refresh_read_values()
            self.assertEqual(e.doc.values,before)
            self.assertFalse(e.doc.dirty)
        send.assert_not_called()
    def test_mix_and_gyro_groups_follow_values_without_losing_fields(self):
        e=self.editor()
        e.doc.values['auto_haptics_enable']=0;e.refresh_read_values()
        mix=next(g for g in e._option_groups if g[0][1]=='Mix 혼합')
        self.assertTrue(all(not row.winfo_manager() for key,row in mix[1]))
        e.doc.values['auto_haptics_enable']=1;e.refresh_read_values()
        self.assertTrue(all(row.winfo_manager() for key,row in mix[1][:2]))
        e.select_category(3)
        e.doc.values.update(gyro_mode=0,gyro_output=0);e.refresh_read_values()
        sensitivity=next(g for g in e._option_groups if g[0][1]=='감도')
        self.assertTrue(all(not row.winfo_manager() for key,row in sensitivity[1]))
        e.doc.values.update(gyro_mode=1,gyro_output=1,gyro_sens_mode=1);e.refresh_read_values()
        visible={key for key,row in sensitivity[1] if row.winfo_manager()}
        self.assertIn('gyro_natural_x10',visible);self.assertNotIn('gyro_sens',visible)
        e.search.set('gyro_sens');e.render_fields();self.assertIn('gyro_sens',e.vars)
    def test_every_gyro_and_stick_option_stays_visible_when_off(self):
        e=self.editor();e.select_category(3)
        keys={f[1] for section in SECTIONS if section['title'] in ('Gyro Aiming','Right Stick','Stick to Mouse') for f in section['fields']}
        self.assertEqual(set(e.vars),keys)
    def test_removed_fields_not_searchable(self):
        e=self.editor()
        for term in ('effect_leak','touch_mouse','batt_stage','t2_mode'):
            e.search.set(term);e.render_fields();self.assertFalse(e.vars)
    def test_sliders_and_header_use_requested_layout(self):
        from studio_range import RangeSlider
        e=self.editor();self.root.deiconify();self.root.update()
        sliders=[]
        def walk(w):
            if isinstance(w,RangeSlider):sliders.append(w)
            for c in w.winfo_children():walk(c)
        walk(e.body);self.assertTrue(sliders)
        for slider in sliders:
            if slider.winfo_ismapped():self.assertGreaterEqual(slider.winfo_width(),300)
        self.assertEqual(int(e.device_choice.grid_info()['row']),0);self.assertEqual(int(e.read_button.grid_info()['column']),2);self.assertFalse(hasattr(e.progress,'grid_info'));self.assertEqual(int(e.notice_label.cget('height')),1)
    def test_slot_collapse_is_initially_eight(self):
        from studio_slots import Slot
        e=self.editor();e.slots=[Slot(i,'saved',str(i)) for i in range(32)];e.select_category(5)
        def strings(w):
            out=[]
            if hasattr(w,'cget'):
                try:out.append(w.cget('text'))
                except Exception:pass
            for c in w.winfo_children():out.extend(strings(c))
            return out
        self.assertNotIn('32 · 31',strings(e.body));e.toggle_slots();self.assertIn('32 · 31',strings(e.body))

if __name__=='__main__':unittest.main()

