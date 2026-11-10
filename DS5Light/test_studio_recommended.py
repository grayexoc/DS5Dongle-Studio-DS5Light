"""Recommended preset transactions use mock clients only; no device writes."""
import copy,unittest,tkinter as tk
from unittest.mock import patch
import test_studio_settings as fixture
from studio_slots import Slot
from studio_recommended import PRESETS,AUDIO_HAPTIC_FIELDS,load_preset,save_and_activate


class Client:
    def __init__(self):
        self.values=dict(auto_haptics_enable=1,audio_buffer_length=48,macro_disable=0xfffffffa)
        self.stamp=dict(index=0,name='Existing',edited=False);self.slot=Slot(2,'empty','')
        self.calls=[];self.timeout=False;self.mask_changed=False
    def profile(self):return dict(self.stamp)
    def info(self,index):return self.slot
    def read_fields(self,fields):return {f[1]:self.values[f[1]] for f in fields},[]
    def write_fields(self,values,current):
        self.calls.append(('fields',dict(values)));self.values.update(values);self.stamp['edited']=bool(values)
        return dict(values)
    def read_one(self,field):return self.values[field[1]]^(1 if self.mask_changed else 0)
    def save_slot(self,index,name):
        self.calls.append(('slot',index));self.saved_values=dict(self.values);self.slot=Slot(index,'saved',name);self.stamp=dict(index=index,name=name,edited=False)
    def activate(self,index):
        self.calls.append(('activate',index))
        if self.timeout:raise TimeoutError('reply lost')
        return dict(reconnect=False,deferred=False)
    def save_flash(self):self.calls.append(('flash',None))
    def reconnect_usb(self):self.calls.append(('reset',None))
    def cancel(self):return False
    def write_macro(self,*args):raise AssertionError('Global macros must not be written')
    def commit_macros(self):raise AssertionError('Global macros must not be committed')


class RecommendedTests(unittest.TestCase):
    def run_transaction(self,client,stamp=None,slot=('empty','')):
        return save_and_activate(client,{'auto_haptics_enable':0},'DS Native',2,slot,stamp or dict(index=0,name='Existing',edited=False),
                                 dict(auto_haptics_enable=1,audio_buffer_length=48,macro_disable=0xfffffffa),lambda _:None)
    def test_normalized_files_and_roles(self):
        profiles={file:load_preset(file) for file,_,_ in PRESETS}
        self.assertEqual(profiles['DS_Native.json'][1]['auto_haptics_enable'],0)
        a=profiles['Audio_Haptic_01.json'];b=profiles['Audio_Haptic_02.json']
        self.assertEqual(a[0],'Audio Haptic 01');self.assertEqual(b[0],'Audio Haptic 02')
        self.assertGreater(a[1]['auto_haptics_gate'],b[1]['auto_haptics_gate'])
        self.assertEqual(b[1]['auto_haptics_smooth'],32)
        self.assertEqual(b[1]['auto_haptics_gate'],16)
        self.assertNotIn('lightbar_fixed',b[1])
        self.assertNotIn('audio_buffer_length',b[1])
        self.assertEqual((a[1]['ah_xover_hz'],b[1]['ah_xover_hz']),(50,60))
        for _,fields in profiles.values():self.assertEqual(set(fields),AUDIO_HAPTIC_FIELDS)
    def test_save_activate_once_and_preserve_mask(self):
        client=Client();mask=client.values['macro_disable'];result=self.run_transaction(client)
        self.assertEqual(client.values['macro_disable'],mask)
        kinds=[kind for kind,_ in client.calls]
        self.assertEqual(kinds,['fields','slot','activate','flash'])
        self.assertEqual(result['mask'],mask)
    def test_device_settings_cannot_enter_preset_transaction(self):
        client=Client();baseline=dict(client.values)
        with self.assertRaises(ValueError):
            save_and_activate(client,{'audio_buffer_length':64},'Audio Haptic 01',2,('empty',''),dict(client.stamp),baseline,lambda _:None)
        self.assertEqual(client.calls,[])
    def test_other_live_settings_survive_in_saved_slot(self):
        client=Client()
        client.values.update(audio_buffer_length=61,polling_rate_mode=2,gyro_mode=1,trigger_reduce=4,
                             haptics_gain=1.7,disable_speaker=0,disable_mic=0,lightbar_off=1)
        before=dict(client.values)
        save_and_activate(client,{'auto_haptics_enable':0},'DS Native',2,('empty',''),dict(client.stamp),before,lambda _:None)
        for key,value in before.items():
            if key!='auto_haptics_enable':self.assertEqual(client.saved_values[key],value)
        self.assertEqual(client.saved_values['auto_haptics_enable'],0)
    def test_changed_source_or_destination_stops_before_writes(self):
        client=Client();client.stamp['name']='Other'
        with self.assertRaises(RuntimeError):self.run_transaction(client)
        self.assertEqual(client.calls,[])
        client=Client();client.slot=Slot(2,'saved','Unexpected')
        with self.assertRaises(RuntimeError):self.run_transaction(client)
        self.assertEqual(client.calls,[])
    def test_ambiguous_activation_never_repeats_or_saves_dependently(self):
        client=Client();client.timeout=True;result=self.run_transaction(client)
        self.assertIn('notice',result)
        self.assertEqual([kind for kind,_ in client.calls],['fields','slot','activate'])
    def test_external_macro_mask_change_prevents_slot_save(self):
        client=Client();client.mask_changed=True
        with self.assertRaises(RuntimeError):self.run_transaction(client)
        self.assertEqual([kind for kind,_ in client.calls],['fields'])


class RecommendedUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def walk(self,widget):
        for child in widget.winfo_children():
            yield child
            yield from self.walk(child)

    def test_card_then_shared_slot_selection_and_rename_precedes_save(self):
        ui=self.editor();errors=[];self.root.report_callback_exception=lambda *args:errors.append(args)
        ui.profile_stamp=dict(index=0,name='Existing',edited=False)
        ui.slots=[Slot(0,'saved','Existing')]+[Slot(i,'empty','') for i in range(1,4)]
        ui.select_category(5);self.root.deiconify();self.root.update()
        self.assertEqual(len(ui.recommended_boxes),3)
        self.assertIn('disabled',ui.recommended_choice.state())
        self.assertIn('disabled',ui.recommended_use_button.state())
        card=ui.recommended_boxes['DS_Native.json']
        help_icon=next(w for w in card.winfo_children() if getattr(w,'_studio_help_icon',False))
        help_icon.event_generate('<Button-1>');self.root.update()
        self.assertIsNone(getattr(ui,'recommended_selection',None))
        ui.select_recommended('DS_Native.json');self.root.update()
        self.assertNotIn('disabled',ui.recommended_choice.state())
        self.assertIn('disabled',ui.recommended_use_button.state())
        ui.recommended_choice.current(1);ui.recommended_choice.event_generate('<<ComboboxSelected>>')
        self.assertEqual(ui.recommended_slots['DS_Native.json'],1)
        self.assertNotIn('disabled',ui.recommended_use_button.state())
        ui.select_recommended('Audio_Haptic_01.json');self.root.update()
        self.assertIn('disabled',ui.recommended_use_button.state())
        buttons=[w for w in self.walk(ui.body) if 'text' in w.keys()]
        self.assertEqual(sum(str(w.cget('text'))=='저장 후 사용' for w in buttons),1)
        rename=next(w for w in buttons if str(w.cget('text'))=='이름 변경')
        save=next(w for w in rename.master.winfo_children() if 'text' in w.keys() and str(w.cget('text'))=='현재 설정 저장')
        self.assertLess(int(rename.grid_info()['column']),int(save.grid_info()['column']))
        self.assertFalse(errors,errors)

    def test_native_completion_never_requests_audio_resume(self):
        ui=self.editor();ui.resume=True
        values=fixture.defaults();values.update(auto_haptics_enable=0,macro_disable=0xfffffffa)
        row=dict(path=b'ours',serial_number='ours',product_string='DualSense')
        profile=dict(index=2,name='DS Native',edited=False,auto_haptics_enable=0,device_row=row)
        fresh=dict(rows=[row],path=b'ours',values=values,profile=profile,cfg=19,version='v1.42.0',macros={})
        ui.slots=[Slot(2,'empty','')]
        with patch.object(self.ui.studio,'_observe_profile'),patch.object(self.ui.studio,'_sync_current_profile'):
            ui.finish_recommended(dict(reloaded=fresh,verified=True,index=2,name='DS Native',old_path=b'ours'))
        self.assertFalse(ui.resume);self.assertEqual(ui.doc.values['macro_disable'],0xfffffffa)
        self.assertEqual(ui.slots[0].name,'DS Native');self.assertTrue(ui.doc.save_requested)

    def test_unconfirmed_completion_blocks_writes_and_resume(self):
        ui=self.editor();ui.resume=True
        ui.finish_recommended(dict(verified=False,notice='확인 필요'))
        self.assertTrue(ui.uncertain);self.assertFalse(ui.write_ready);self.assertFalse(ui.resume)


if __name__=='__main__':unittest.main()
