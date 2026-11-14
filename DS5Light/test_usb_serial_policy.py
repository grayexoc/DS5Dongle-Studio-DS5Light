"""Device policy UI/protocol tests; never access a physical device."""
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
from studio_settings_protocol import SettingsClient,PolicySaveError
from studio_help import help_text
import test_studio_settings as fixture


class ProtocolTests(unittest.TestCase):
    def test_policy_save_verifies_reply_and_failure_keeps_actual_value(self):
        client=SettingsClient(None)
        with patch.object(client,'command',return_value=bytes((0x66,0x21,0,1,1))) as command:
            self.assertEqual(client.usb_serial_hidden(1),1)
            self.assertEqual(command.call_args.args,(0x21,b'\x01\x01',0x84))
        for reply in (bytes((0x66,0x21,0,2,1)),bytes((0x66,0x21,0,1,0))):
            with patch.object(client,'command',return_value=reply):
                with self.assertRaises(ValueError):client.usb_serial_hidden(1)
        with patch.object(client,'command',return_value=bytes((0x66,0x21,2,1,0))):
            with self.assertRaises(PolicySaveError) as error:client.usb_serial_hidden(1)
            self.assertEqual(error.exception.current,0)

    def test_legacy_profile_write_never_sends_common_policy(self):
        client=SettingsClient(None);client.bulk=True
        with patch.object(client,'command') as command:
            client.write_fields({'disable_usb_sn':0},{},profile_snapshot=True)
            command.assert_not_called()


class UITests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def configured_editor(self,mode=0):
        ui=self.editor();ui.path=b'policy-device';ui.app.studio.controller_connected=True
        ui.external_stale=False;ui.reconnect_wait=False
        ui.usb_serial_policy=(ui.path,mode);ui.dock_policy=(ui.path,0)
        ui.standby_policy=(ui.path,0);ui.device_rows=[dict(path=ui.path)]
        ui.select_category(0)
        return ui

    def test_common_toggle_is_below_dock_and_outside_profile_fields(self):
        ui=self.configured_editor()
        def descendants(w):
            for child in w.winfo_children():
                yield child
                yield from descendants(child)
        controls={}
        for w in descendants(ui.body):
            if hasattr(w,'text'):controls[w.text]=w
            try:controls[str(w.cget('text'))]=w
            except tk.TclError:pass
        self.assertIn('Pico 설정',controls)
        self.assertIn('USB 시리얼 숨기기',controls)
        dock=controls['충전독 장착 시 연결 해제']
        serial=controls['USB 시리얼 숨기기']
        self.assertEqual(serial.master.master,dock.master)
        self.assertGreater(int(serial.master.grid_info()['row']),int(dock.grid_info()['row']))
        self.assertNotIn('disable_usb_sn',ui.field_views)
        self.assertIn('윈도 소리 제어판',help_text('disable_usb_sn'))

    def test_common_save_uses_its_own_command_and_verifies_native_reconnect(self):
        ui=self.configured_editor();ui.doc.values['usb_gamepad_mode']=0
        before=dict(ui.doc.values)
        client=Mock();client.usb_serial_hidden.return_value=1
        with patch.object(ui,'stopped_task') as task:
            ui.change_usb_serial_policy(1)
        kind,operation=task.call_args.args
        self.assertEqual(kind,'usb_serial_policy')
        with patch.object(ui,'with_client',side_effect=lambda op:op(client)), \
                patch('studio_reconnect.wait_for_macros',return_value={'verified':True}) as wait:
            result=operation()
        client.usb_serial_hidden.assert_called_once_with(1)
        client.reconnect_usb.assert_called_once()
        client.save_flash.assert_not_called()
        wait.assert_called_once()
        self.assertEqual(result['value'],1)
        self.assertEqual(ui.doc.values,before)

    def test_english_name_and_explanation(self):
        with patch('studio_settings_ui.ui_text',side_effect=lambda ko,en:en),patch('localization.LANGUAGE','en'):
            ui=self.configured_editor()
            text=help_text('disable_usb_sn')
            self.assertIn('wired DualSense',text)
            self.assertIn('Windows Sound control panel',text)
            self.assertEqual(ui.standby_value('usb_serial_policy'),0)

    def test_failed_save_restores_reported_actual_policy(self):
        ui=self.configured_editor()
        ui.results.put(('usb_serial_policy',0,'save rejected'))
        ui.poll()
        self.assertEqual(ui.usb_serial_policy,(ui.path,0))
        self.assertEqual(ui.standby_value('usb_serial_policy'),0)

    def test_xinput_stores_policy_without_native_reenumeration(self):
        ui=self.configured_editor();ui.doc.values['usb_gamepad_mode']=1
        client=Mock();client.usb_serial_hidden.return_value=1
        with patch.object(ui,'stopped_task') as task:ui.change_usb_serial_policy(1)
        with patch.object(ui,'with_client',side_effect=lambda op:op(client)):
            self.assertEqual(task.call_args.args[1](),{'value':1})
        client.reconnect_usb.assert_not_called()

    def test_old_firmware_keeps_toggle_unavailable(self):
        ui=self.configured_editor(mode=None)
        self.assertIsNone(ui.standby_value('usb_serial_policy'))
        with patch.object(ui,'stopped_task') as task:
            ui.change_standby_policy(tk.BooleanVar(master=self.root,value=True),'usb_serial_policy')
            task.assert_not_called()

    def test_edge_recommendation_is_gold_and_only_shown_for_known_off_policy(self):
        ui=self.configured_editor();warning='DualSense Edge의 네이티브 햅틱·스피커 호환성을 위해 USB 시리얼 숨기기를 켜는 것을 권장합니다.'
        def labels(widget):
            for child in widget.winfo_children():
                if isinstance(child,tk.Label):yield child
                yield from labels(child)
        for pid,mode,expected in ((0x0df2,0,True),(0x0df2,1,False),(0x0ce6,0,False),(0x0df2,None,False)):
            ui.device_rows=[dict(path=ui.path,product_id=pid)]
            ui.usb_serial_policy=(ui.path,mode);ui.render_fields()
            found=[label for label in labels(ui.body) if label.cget('text')==warning]
            self.assertEqual(bool(found),expected,(pid,mode))
            if found:
                self.assertEqual(found[0].cget('fg'),'#d6ad52')
                self.assertEqual(int(found[0].grid_info()['row']),8)
