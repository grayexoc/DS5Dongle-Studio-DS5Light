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
        basic=ui.field_views['lightbar_fixed'][1][0]
        self.assertEqual(basic.master.grid_info()['sticky'],'e')
        color=ui.field_views['lightbar_rgb'][1][0]
        off=ui.field_views['lightbar_off'][1][0]
        self.assertEqual(basic.master.pack_slaves(),[color.master.master,basic,off.master.master])
        self.assertEqual(color.master.winfo_children()[0].cget('text'),'색상 고정')
        self.assertEqual(ui.field_views['disable_pico_led'][0].winfo_children()[0].cget('text'),'Pico LED')
        self.assertFalse(ui.doc.changes)

    def test_pico_positive_toggle_preserves_wire_polarity(self):
        ui=self.lighting();on,off=ui.field_views['disable_pico_led'][1]
        self.assertEqual((on.text,off.text),('켜기','끄기'))
        self.assertEqual((on.variable.get(),off.variable.get()),(True,False))
        with patch.object(ui,'with_client') as wire:
            off.invoke();self.assertEqual(ui.doc.values['disable_pico_led'],1)
            off.invoke();self.assertEqual((on.variable.get(),off.variable.get()),(False,True))
            on.invoke();self.assertEqual(ui.doc.values['disable_pico_led'],0)
            self.assertEqual((on.variable.get(),off.variable.get()),(True,False))
            wire.assert_not_called()
        self.assertFalse(ui.doc.changes)

    def test_default_off_and_color_are_exclusive_and_local(self):
        ui=self.lighting();before=dict(ui.doc.values)
        color=ui.field_views['lightbar_rgb'][1][0]
        caption=color.master.winfo_children()[0]
        self.assertEqual((color.cget('text'),str(color.cget('state'))),('고정 꺼짐','normal'))
        self.assertEqual(int(color.cget('pady')),1)
        with patch.object(ui,'with_client') as wire:
            ui.field_views['lightbar_off'][1][0].invoke()
            self.assertEqual((ui.doc.values['lightbar_fixed'],ui.doc.values['lightbar_off']),(0,1))
            self.assertEqual((color.cget('text'),str(color.cget('state'))),('고정 꺼짐','normal'))
            with patch('studio_lightbar.rgb_palette',return_value=None) as palette:color.invoke()
            palette.assert_called_once()
            self.assertEqual((ui.doc.values['lightbar_fixed'],ui.doc.values['lightbar_off']),(0,1))
            with patch('studio_lightbar.rgb_palette',return_value=0xabcdef):caption.invoke()
            self.assertEqual((ui.doc.values['lightbar_fixed'],ui.doc.values['lightbar_off']),(1,0))
            self.assertEqual(ui.doc.values['lightbar_rgb'],0xabcdef)
            self.assertEqual((color.cget('text'),str(color.cget('state')),caption.cget('fg')),('#ABCDEF','normal','#d6ad52'))
            ui.field_views['lightbar_fixed'][1][0].invoke()
            self.assertEqual((ui.doc.values['lightbar_fixed'],ui.doc.values['lightbar_off']),(0,0))
            self.assertEqual((color.cget('text'),str(color.cget('state'))),('고정 꺼짐','normal'))
            wire.assert_not_called()
        for key in set(before)-{'lightbar_fixed','lightbar_off','lightbar_rgb'}:
            self.assertEqual(ui.doc.values[key],before[key])

    def test_read_refresh_and_search_keep_values(self):
        ui=self.lighting();before=copy.deepcopy(ui.doc.values)
        ui.doc.values['disable_pico_led']=1;ui.doc.baseline['disable_pico_led']=1
        ui.refresh_read_values()
        self.assertEqual([c.variable.get() for c in ui.field_views['disable_pico_led'][1]],[False,True])
        self.assertFalse(ui.doc.changes)
        ui.search.set('lightbar');ui.render_fields();self.assertIn('lightbar_rgb',ui.field_views)
        ui.search.set('');ui.render_fields();self.assertIn('조명',ui.search_targets)
        self.assertEqual(ui.doc.values,dict(before,disable_pico_led=1))

if __name__=='__main__':unittest.main()
