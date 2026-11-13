import unittest
from unittest.mock import patch
from studio_macro_design import MacroDraft
from studio_macro_tools import normalize_macro
from studio_settings_protocol import SettingsClient
from test_studio_macro_flow import record


class SwipeClickTests(unittest.TestCase):
    def test_click_flag_roundtrip_and_other_flags(self):
        original=record(gesture=128,keys=[9])
        draft=MacroDraft(original)
        changed=draft.build(dict(draft.initial,hide=True),strict=True)
        self.assertEqual(changed[5]&31,4)
        self.assertEqual(normalize_macro(list(changed)),changed)
        self.assertTrue(MacroDraft(changed).initial['hide'])
        draft=MacroDraft(changed)
        self.assertEqual(draft.build(dict(draft.initial,hide=False))[5]&4,0)

    def test_old_firmware_rejects_click_block_without_writing(self):
        data=record(gesture=128,keys=[9],flags=4)
        for bits in (7,15):
            client=SettingsClient(object())
            reply=bytearray(63);reply[:4]=bytes([0x66,0x20,0,1]);reply[9]=bits
            with patch.object(client,'command',return_value=bytes(reply)) as command:
                if bits==7:
                    with self.assertRaisesRegex(RuntimeError,'업데이트'):
                        client.write_macro(0,data)
                    self.assertEqual(command.call_count,1)
                else:
                    client.require_macro_features([data])
                    self.assertEqual(command.call_count,1)



import test_studio_macro_flow as macro_fixture
class SwipeClickUITests(unittest.TestCase):
    setUp=macro_fixture.MacroFlowUITests.setUp
    tearDown=macro_fixture.MacroFlowUITests.tearDown
    editor=macro_fixture.MacroFlowUITests.editor
    macro=macro_fixture.MacroFlowUITests.macro

    def test_swipe_replaces_press_mode_with_click_option(self):
        ui,e=self.macro(record(gesture=128,keys=[9]))
        self.assertTrue(all(not w.winfo_manager() for w in e.mode_widgets))
        self.assertEqual(e.swipe_click_row.winfo_manager(),'grid')
        e.hide.set(True);e.refresh()
        self.assertEqual(e.draft.build(e.state(),strict=True)[5]&31,4)
        self.assertIn('클릭 차단',ui.macro_summary(e.draft.build(e.state())))
        e.kind.set('버튼 입력');e.refresh()
        self.assertTrue(all(w.winfo_manager()=='grid' for w in e.mode_widgets))
        self.assertFalse(e.swipe_click_row.winfo_manager())
        e.close()

    def test_click_picker_reorders_labels_without_changing_wire_bits(self):
        from studio_button_names import NAMES
        ui,e=self.macro(record(gesture=0,keys=[9]))
        values=e.button_dropdown.values
        self.assertEqual(values[-3:],tuple(NAMES[i] for i in (17,23,24)))
        e.clear_buttons()
        for bit in (17,23,24):
            e.button_dropdown.choose(values.index(NAMES[bit]))
            self.assertEqual(e.state()['chord'],1<<bit)
            e.clear_buttons()
        e.close()

if __name__=='__main__':unittest.main()
