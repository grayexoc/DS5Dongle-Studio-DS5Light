import copy,unittest
from unittest.mock import patch
import test_studio_settings as fixture


class LightingTests(unittest.TestCase):
    setUp=fixture.NativeUITests.setUp
    tearDown=fixture.NativeUITests.tearDown
    editor=fixture.NativeUITests.editor

    def lighting(self):
        ui=self.editor();ui.doc.values.update(disable_pico_led=0,lightbar_off=0,lightbar_fixed=0,lightbar_rgb=0x123456)
        ui.doc.baseline=dict(ui.doc.values);ui.select_category(0);return ui

    def test_card_order_and_nested_controls(self):
        ui=self.lighting();titles=list(ui.search_targets)
        self.assertEqual(titles.index('조명'),titles.index('장치')+1)
        for key in ui.LIGHTING_FIELDS:self.assertIn(key,ui.field_views)
        self.assertEqual(ui.field_views['lightbar_off'][1][0].text,'끄기')
        self.assertFalse(ui.doc.changes)

    def test_pico_positive_toggle_preserves_wire_polarity(self):
        ui=self.lighting();control=ui.field_views['disable_pico_led'][1][0]
        self.assertEqual(control.text,'켜기');self.assertTrue(control.variable.get())
        with patch.object(ui,'with_client') as wire:
            control.invoke();self.assertEqual(ui.doc.values['disable_pico_led'],1)
            self.assertFalse(control.variable.get());self.assertEqual(control.text,'끄기')
            control.invoke();self.assertEqual(ui.doc.values['disable_pico_led'],0)
            wire.assert_not_called()
        self.assertFalse(ui.doc.changes)

    def test_default_off_and_color_are_exclusive_and_local(self):
        ui=self.lighting();before=dict(ui.doc.values)
        with patch.object(ui,'with_client') as wire:
            ui.field_views['lightbar_off'][1][0].invoke()
            self.assertEqual((ui.doc.values['lightbar_fixed'],ui.doc.values['lightbar_off']),(0,1))
            with patch('studio_lightbar.rgb_palette',return_value=None):ui.choose_lightbar_colour()
            self.assertEqual((ui.doc.values['lightbar_fixed'],ui.doc.values['lightbar_off']),(0,1))
            with patch('studio_lightbar.rgb_palette',return_value=0xabcdef):ui.choose_lightbar_colour()
            self.assertEqual((ui.doc.values['lightbar_fixed'],ui.doc.values['lightbar_off']),(1,0))
            self.assertEqual(ui.doc.values['lightbar_rgb'],0xabcdef)
            ui.field_views['lightbar_fixed'][1][0].invoke()
            self.assertEqual((ui.doc.values['lightbar_fixed'],ui.doc.values['lightbar_off']),(0,0))
            wire.assert_not_called()
        for key in set(before)-{'lightbar_fixed','lightbar_off','lightbar_rgb'}:
            self.assertEqual(ui.doc.values[key],before[key])

    def test_read_refresh_and_search_keep_values(self):
        ui=self.lighting();before=copy.deepcopy(ui.doc.values)
        ui.doc.values['disable_pico_led']=1;ui.doc.baseline['disable_pico_led']=1
        ui.refresh_read_values();self.assertEqual(ui.field_views['disable_pico_led'][1][0].text,'끄기')
        self.assertFalse(ui.doc.changes)
        ui.search.set('lightbar');ui.render_fields();self.assertIn('lightbar_rgb',ui.field_views)
        ui.search.set('');ui.render_fields();self.assertIn('조명',ui.search_targets)
        self.assertEqual(ui.doc.values,dict(before,disable_pico_led=1))

if __name__=='__main__':unittest.main()
