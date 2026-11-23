import unittest,tkinter as tk
from pathlib import Path
import test_studio_settings as base
import test_studio_macro_flow as flow
from studio_range import RangeSlider
from ui_controls import SectionTitle
import app

def walk(w):
    for c in w.winfo_children():yield c;yield from walk(c)
def text(w):
    try:return str(w.cget('text'))
    except tk.TclError:return ''

class LabelRevisionTests(unittest.TestCase):
    setUp=base.NativeUITests.setUp
    tearDown=base.NativeUITests.tearDown
    editor=base.NativeUITests.editor
    def macro(self,data):return flow.MacroFlowUITests.macro(self,data)
    def test_reference_caption_shares_tick_row_without_overlap(self):
        self.root._ui_scale = 1.25
        for marker, label, texts in (
            (2, 'Recommended', {'0', 'Recommended2', '100'}),
            (98, '추천', {'0', '추천98', '100'}),
            (100, '기본', {'0', '기본100'}),
        ):
            with self.subTest(marker=marker):
                variable = tk.StringVar(self.root, '50')
                slider = RangeSlider(self.root, variable, 0, 100, marker=marker, marker_label=label)
                slider.place(x=0, y=0)
                self.root.update_idletasks()
                slider.draw()
                items = [item for item in slider.find_all() if slider.type(item) == 'text']
                self.assertEqual({slider.itemcget(item, 'text') for item in items}, texts)
                self.assertEqual(len({slider.coords(item)[1] for item in items}), 1)
                bounds = sorted(slider.bbox(item) for item in items)
                self.assertTrue(all(a[2] < b[0] for a, b in zip(bounds, bounds[1:])))
                dot, = slider.find_withtag('reference_dot')
                self.assertEqual(slider.type(dot), 'oval')
                self.assertLessEqual(slider.bbox(dot)[3], min(bound[1] for bound in bounds))
                slider.destroy()

    def test_effective_stick_default_is_48_but_stored_default_stays_zero(self):
        ui,m=self.macro(flow.record(gesture=160,keys=[26,7,22,4],flags=2,stick_thresh=0))
        self.assertEqual(m.threshold.get(),'48');self.assertEqual(m.state()['threshold'],0)
        slider=next(w for w in walk(m.threshold_row) if isinstance(w,RangeSlider))
        self.assertEqual(slider.limits(),(10,120));self.assertEqual((slider.marker,slider.marker_label),(48,'기본'))
        self.assertEqual(m.draft.build(m.state())[18],0)
        m.threshold.set('60');self.assertEqual(m.draft.build(m.state())[18],60)
        m.threshold.set('48');self.assertEqual(m.draft.build(m.state())[18],0);m.close()
    def test_explicit_48_is_preserved_and_release_order_is_immediately_available(self):
        ui,m=self.macro(flow.record(chord=1,keys=[224,4],stick_thresh=48))
        self.assertEqual(m.state()['threshold'],48);m.go_step(1)
        self.assertTrue(m.release_details.winfo_manager());self.assertTrue(m.release_row.winfo_manager())
        self.assertFalse(any(text(w)=='키 해제 세부 설정' for w in walk(m.dialog)))
        self.assertFalse(hasattr(m,'output_icon'));self.assertFalse(hasattr(m,'advanced_button'))
        self.assertIn('키보드·마우스용',m.rules.get());m.close()
    def test_slot_note_and_names(self):
        ui=self.editor();ui.select_category(5)
        self.assertFalse(any('(공사 중 트리거 제외)' in text(w) for w in walk(ui.body)))
        ui,m=self.macro(flow.record(chord=1,keys=[4]))
        texts=[text(w) for w in walk(m.dialog)]
        self.assertIn('조건 버튼 전달',texts);self.assertEqual(m.hide_control.text,'조건 버튼 숨기기');m.close()
    def test_all_requested_title_glyphs_are_gold(self):
        titles=[w for page in (self.ui.game_page,self.ui.device_page)
                for w in walk(page) if isinstance(w,SectionTitle)]
        self.assertEqual([t.number for t in titles],['camera','channels','sliders','filter','input','output'])
        for t in titles:
            first=t.find_all()[0]
            color=t.itemcget(first,'fill') or t.itemcget(first,'outline')
            self.assertEqual(color,app.ACCENT)
        self.ui.tabs.draw()
        for i in range(len(self.ui.tabs.labels)):
            ids=self.ui.tabs.find_withtag(f'icon-{i}');self.assertTrue(ids)
            for item in ids:
                color=self.ui.tabs.itemcget(item,'fill') or self.ui.tabs.itemcget(item,'outline')
                self.assertEqual(color,app.ACCENT)
        self.assertFalse(Path('studio_button_icons.py').exists())

if __name__=='__main__':unittest.main()
