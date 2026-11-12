"""Pending UI regressions; execution deferred at the user's request."""
import unittest
import test_studio_settings as fixture
from studio_range import RangeSlider


class ScaleTests(unittest.TestCase):
    def test_rumble_display_keeps_percent_wire_values(self):
        slider=object.__new__(RangeSlider)
        slider.trigger=False;slider.display_scale=100;slider.low=100;slider.high=200
        self.assertEqual(slider.limits(),(1,2))
        self.assertEqual(slider.display(150),1.5)
        self.assertEqual(slider.raw(1.5),150)


class LayoutTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def test_rumble_moves_to_haptics_without_changing_values(self):
        ui=self.editor();ui.doc.values['rumble_gain']=150
        before=dict(ui.doc.values);ui.select_category(0)
        self.assertNotIn('rumble_gain',ui.field_views)
        ui.select_category(1)
        keys=list(ui.field_views)
        self.assertLess(keys.index('haptics_gain'),keys.index('rumble_gain'))
        self.assertLess(keys.index('rumble_gain'),keys.index('rumble_mode'))
        self.assertEqual(keys.index('rumble_mode')+1,keys.index('rumble_release'))
        entry=ui.range_controls['rumble_gain'][0]
        self.assertEqual(ui.parent.getvar(str(entry.cget('textvariable'))),'1.5')
        self.assertEqual(ui.doc.values,before)

    def test_wake_policy_and_unsupported_field(self):
        ui=self.editor();ui.path=b'layout-test';ui.app.studio.controller_connected=True
        ui.external_stale=False;ui.reconnect_wait=False
        ui.standby_policy=(ui.path,0)
        self.assertTrue(ui.enabled_for('enable_wake'))
        ui.standby_policy=(ui.path,1)
        self.assertFalse(ui.enabled_for('enable_wake'))
        ui.doc.values.pop('enable_wake',None);ui.select_category(0)
        self.assertNotIn('enable_wake',ui.field_views)

if __name__=='__main__':unittest.main()
