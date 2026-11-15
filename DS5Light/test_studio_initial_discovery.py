import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from preferences import PreferenceStore,default_preferences,validate
from studio_startup import StartupDiscovery,initial_profile
from studio_slots import Slot
from device_binding import DeviceBinding
import test_studio_settings as fixture


class InitialDiscoveryTests(unittest.TestCase):
    def panel(self):
        p=StartupDiscovery();p.initial_connected=False;p.initial_deadline=None;p.closed=False;p.busy=False
        p._cancel=threading.Event();p.binding=DeviceBinding();p.task=Mock();p.device_serials={b'old':'PICO-A'}
        p.app=NS(_closing=False,_close_requested=False,root=Mock(),studio_settings=NS(busy=False),
                 preference_store=NS(data=default_preferences()),schedule_preferences_save=Mock())
        return p

    def test_optional_history_preserves_legacy_settings_and_discards_bad_history_only(self):
        data=default_preferences();data.pop('studio_slots');data['auto_start']=True
        old=dict(version=1,preferences=data)
        self.assertEqual(validate(old)['studio_slots'],[])
        for bad in (None,{},[{'serial':'A','slots':[{'index':32,'state':'saved'}]}],
                    [{'serial':'A','slots':[{'index':0,'state':'saved','name':5}]}]):
            data['studio_slots']=bad
            clean=validate(old)
            self.assertTrue(clean['auto_start']);self.assertEqual(clean['studio_slots'],[])

    def test_persistence_reuses_serial_with_new_path_but_not_another_or_unknown_device(self):
        p=self.panel();p.remember_slots({'serial_number':'PICO-A'},[Slot(0,'saved','Audio'),Slot(3,'empty')])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'preferences.json';store=PreferenceStore(path)
            store.save(p.app.preference_store.data)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['version'],1)
            p.app.preference_store=PreferenceStore(path);p.app.preference_store.load()
        self.assertEqual(p.cached_slots({'path':b'new','serial_number':'PICO-A'}),[Slot(0,'saved','Audio'),Slot(3,'empty')])
        self.assertEqual(p.cached_slots({'serial_number':'PICO-B'}),[])
        self.assertEqual(p.cached_slots({'path':b'new'}),[])
        p.forget_slot_history(b'old')
        self.assertEqual(p.cached_slots({'serial_number':'PICO-A'}),[])

    def test_initial_budget_and_verified_connection_stop_fast_retry(self):
        p=self.panel()
        with patch('studio_startup.time.monotonic',return_value=100):p.initial_read()
        self.assertEqual(p.initial_deadline,110);p.task.assert_called_once()
        with patch('studio_startup.time.monotonic',return_value=101):p.finish_initial_read(None)
        self.assertEqual(p.app.root.after.call_args.args[0],600)
        p.task.reset_mock();p.app.root.after.reset_mock()
        with patch('studio_startup.time.monotonic',return_value=110):
            p.finish_initial_read(None);p.initial_read()
        p.app.root.after.assert_not_called();p.task.assert_not_called()
        p.initial_connected=True
        with patch('studio_startup.time.monotonic',return_value=102):p.initial_read()
        p.task.assert_not_called()

    def test_settings_work_defers_initial_query(self):
        p=self.panel();p.app.studio_settings.busy=True
        p.initial_read();p.task.assert_not_called()
        self.assertEqual(p.app.root.after.call_args.args[0],200)

    def test_live_profile_is_read_before_using_saved_slot_list(self):
        row={'path':b'new','serial_number':'PICO-A'};binding=DeviceBinding()
        device=Mock();client=Mock();client.profile_state.return_value={'index':0,'name':'Live','auto_haptics_enable':0}
        lock=Mock();lock.acquire.return_value=True
        with patch('studio_startup.devices',return_value=[row]),patch('hid.device',return_value=device),\
             patch('studio_settings_protocol.SettingsClient',return_value=client),patch('studio_startup._DEVICE_LOCK',lock):
            result=initial_profile(binding,lambda:False,10**15)
        self.assertEqual(result,(row,client.profile_state.return_value,True))
        client.profile_state.assert_called_once();client.slots.assert_not_called()
        device.close.assert_called_once();lock.release.assert_called_once()

    def test_unknown_or_ambiguous_device_does_not_open_hid(self):
        rows=[{'path':b'A','serial_number':'A'},{'path':b'B','serial_number':'B'}]
        with patch('studio_startup.devices',return_value=rows),patch('hid.device') as device:
            self.assertIsNone(initial_profile(DeviceBinding(),lambda:False,10**15))
        device.assert_not_called()

    def test_failed_query_releases_handle_and_shared_lock(self):
        row={'path':b'A','serial_number':'A'};device=Mock();client=Mock()
        client.profile_state.side_effect=TimeoutError('not ready');lock=Mock();lock.acquire.return_value=True
        with patch('studio_startup.devices',return_value=[row]),patch('hid.device',return_value=device),\
             patch('studio_settings_protocol.SettingsClient',return_value=client),patch('studio_startup._DEVICE_LOCK',lock):
            with self.assertRaises(TimeoutError):initial_profile(DeviceBinding(),lambda:False,10**15)
        device.close.assert_called_once();lock.release.assert_called_once()

    def test_cancelled_or_expired_probe_does_not_enumerate(self):
        with patch('studio_startup.devices') as enumerate_devices:
            self.assertIsNone(initial_profile(DeviceBinding(),lambda:True,10**15))
            self.assertIsNone(initial_profile(DeviceBinding(),lambda:False,0))
        enumerate_devices.assert_not_called()


class SharedDiscoveryUITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def test_cached_catalog_never_overrides_live_profile_or_audio_mode(self):
        panel=self.ui.studio
        row={'path':b'A','serial_number':'PICO-A'}
        panel.remember_slots(row,[Slot(0,'saved','Previous')])
        profile=dict(index=0,name='Live',edited=False,auto_haptics_enable=0)
        panel.results.put(('startup',(row,profile,True),None));panel.poll()
        self.assertEqual(panel.auto_haptics_mode,0)
        self.assertEqual(panel.current_profile_name,'Live')
        self.assertTrue(panel.initial_connected)
        self.assertEqual(panel.binding.snapshot().hid_path,b'A')

    def test_settings_slot_entry_reuses_same_catalog_without_full_slot_query(self):
        ui=self.editor();row={'path':b'A','serial_number':'PICO-A'}
        self.ui.studio.remember_slots(row,[Slot(0,'saved','Audio'),Slot(2,'empty')])
        ui.category=5;ui.path=b'A';ui.device_rows=[row];ui.slots=[];ui.slots_cache_path=None
        ui.entry_attempts={'fields'}
        with patch.object(ui,'task') as query,patch.object(ui,'render_fields'):
            ui.entry_step(ui.entry_generation)
        query.assert_not_called()
        self.assertEqual(ui.slots,[Slot(0,'saved','Audio'),Slot(2,'empty')])


if __name__=='__main__':unittest.main()
