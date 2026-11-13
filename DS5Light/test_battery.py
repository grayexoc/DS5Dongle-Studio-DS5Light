import unittest
from pathlib import Path
from unittest.mock import patch
import battery_status as battery
from studio_slots import StudioClient
from test_studio_slots import Fake,info
import test_modified_ui as fixture

class ImmediateThread:
    def __init__(self,target,**kwargs):self.target=target
    def start(self):self.target()

class BatteryTests(unittest.TestCase):
    def test_read_percent_and_charge_state(self):
        for value in (4,10,0x14,0x20,0xf4):
            device=Fake([info(),bytes([0x81,0x66,4,0x68,value])+bytes(59)])
            result=StudioClient(device,sleep=lambda _:None).battery()
            self.assertEqual(result,dict(percent=(value&15)*10,state=value>>4))
            self.assertEqual([p[2] for p in device.sent],[10,4])
    def test_empty_and_bad_reports(self):
        for value in (0,11):
            device=Fake([info(),bytes([0x81,0x66,4,0x68,value])+bytes(59)])
            client=StudioClient(device,sleep=lambda _:None)
            if value:
                with self.assertRaises(RuntimeError):client.battery()
            else:self.assertIsNone(client.battery())
    def test_retry_then_normal_and_low_frequency(self):
        clock=[100.];answer=[None];calls=[]
        def read(*args,**kw):calls.append(clock[0]);return answer[0]
        with patch.object(battery.time,'monotonic',lambda:clock[0]),patch.object(battery.threading,'Thread',ImmediateThread),patch.object(battery,'devices',return_value=[{'path':b'one'}]),patch.object(battery,'run_device',side_effect=read):
            m=battery.BatteryMonitor();m.tick();m.tick()
            self.assertEqual((m.state,m.next_check),('no_data',115.))
            clock[0]=114;m.tick();self.assertEqual(len(calls),1)
            answer[0]=dict(percent=40,state=0);clock[0]=115;m.tick();m.tick()
            self.assertEqual((m.state,m.interval,m.next_check),('ready',300,415.))
            answer[0]=dict(percent=20,state=0);clock[0]=415;m.tick();m.tick()
            self.assertEqual(m.interval,60)
            m.close();clock[0]=1000;m.tick();self.assertEqual(len(calls),3)
    def test_paused_and_multiple_devices_do_not_read(self):
        with patch.object(battery.threading,'Thread',ImmediateThread),patch.object(battery,'devices',return_value=[{'path':b'one'},{'path':b'two'}]),patch.object(battery,'run_device') as read:
            m=battery.BatteryMonitor();m.tick(paused=True);self.assertFalse(m.busy)
            m.tick();m.tick(paused=True);self.assertEqual(m.state,'multiple');read.assert_not_called()
    def test_preferred_change_discards_old_result(self):
        m=battery.BatteryMonitor();m.preferred=b'old';m.busy=True
        m.results.put((0,'ready',dict(percent=100,state=2)))
        m.tick(paused=True,preferred=b'new')
        self.assertEqual(m.state,'waiting');self.assertIsNone(m.value);self.assertFalse(m.busy)

class BatteryLogoTests(unittest.TestCase):
    setUp=fixture.ModifiedUITests.setUp
    tearDown=fixture.ModifiedUITests.tearDown
    def test_native_combobox_popup_focus_does_not_break_sweep(self):
        from tkinter import ttk
        errors=[]
        self.root.report_callback_exception=lambda *error:errors.append(error)
        self.root.deiconify();self.root.focus_force();self.root.update()
        logo=self.ui.brand_wordmark
        logo.show_status('ready',dict(percent=40,state=0))
        choice=ttk.Combobox(self.root,values=['a','b'],state='readonly')
        choice.pack();self.root.update()
        try:
            self.root.tk.call('ttk::combobox::Post',str(choice))
            popup=str(self.root.tk.call('ttk::combobox::PopdownWindow',str(choice)))
            self.root.tk.call('focus','-force',popup+'.f.l')
            self.root.update()
            with self.assertRaises(KeyError):self.root.nametowidget(popup+'.f.l')
            self.assertFalse(logo._foreground())
            logo._check_focus();logo._begin_sweep();logo._sweep_frame()
            self.assertIsNone(logo._sweep_job)
        finally:
            self.root.tk.call('ttk::combobox::Unpost',str(choice))
            choice.destroy()
        self.root.focus_force();self.root.update()
        self.assertTrue(logo._foreground())
        self.assertIsNotNone(logo._sweep_job)
        self.assertFalse(errors)
        logo.show_status('no_data',None)
    def test_render_levels_have_different_pulse_and_identical_type(self):
        logo=self.ui.brand_wordmark;images=[]
        for percent in (0,20,40,100):
            logo.show_status('ready',dict(percent=percent,state=0));images.append(logo._display.copy())
            self.assertIn(str(percent)+'%',logo.hint.text)
        y=round((130-70)*logo._scale);start=round((410-62)*logo._scale)
        samples=[tuple(image.get(x,y) for x in range(start,image.width())) for image in images]
        self.assertEqual(len(set(samples)),4)
        for image in images[1:]:
            for x in range(start-5):self.assertEqual(image.get(x,y),images[0].get(x,y))
        out=Path('reports/battery-review');out.mkdir(parents=True,exist_ok=True)
        for percent,image in zip((0,20,40,100),images):image.write(str(out/f'pulse-{percent}.png'),format='png')
        # Verify visible brightness on the actual app background, not just RGB
        # of transparent pixels (the fade is stored in their alpha channel).
        import tkinter as tk
        composite=[]
        for percent,image in zip((0,20,40,100),images):
            target=tk.PhotoImage(master=logo,width=image.width(),height=image.height())
            target.put('#0b0b0b',to=(0,0,image.width(),image.height()))
            logo.tk.call(target,'copy',image,'-compositingrule','overlay')
            target.write(str(out/f'pulse-background-{percent}.png'),format='png');composite.append(target)
        x=round((600-62)*logo._scale)
        self.assertLess(sum(composite[2].get(x,y)),sum(composite[3].get(x,y))*.5)
    def test_unknown_is_not_full_and_unchanged_status_is_cached(self):
        logo=self.ui.brand_wordmark;logo.show_status('ready',dict(percent=100,state=2));full=logo._display
        logo.show_status('no_data',None);self.assertIs(logo._display,logo.unknown);self.assertIsNot(logo._display,full)
        ids=logo.find_all();logo.show_status('no_data',None);self.assertEqual(logo.find_all(),ids)

    def test_sweep_clips_to_remaining_pulse_and_stops_when_unmapped(self):
        import tkinter as tk
        self.root.deiconify();self.root.focus_force();self.root.update()
        logo=self.ui.brand_wordmark
        logo.show_status('ready',dict(percent=65,state=0))
        logo._stop_sweep()
        with patch('battery_logo.time.monotonic',side_effect=(0,.7)):
            logo._begin_sweep()
        cached=logo._sweep_sources
        strip=logo._sweep_strip
        def composite(image):
            target=tk.PhotoImage(master=logo,width=logo.full.width(),height=logo.full.height())
            target.put(logo._background,to=(0,0,target.width(),target.height()))
            logo.tk.call(target,'copy',logo._display,'-compositingrule','overlay')
            if image is not None:
                x=int(logo.coords(logo._sweep_item)[0])
                logo.tk.call(target,'copy',image,'-to',x,0,'-compositingrule','overlay')
            return target
        before,after=composite(None),composite(strip)
        changed=[(x,y) for y in range(after.height()) for x in range(after.width())
                 if before.get(x,y)!=after.get(x,y)]
        self.assertTrue(changed)
        self.assertTrue(all(int(logo.PULSE_LEFT*logo._scale)<=x<logo._sweep_cutoff and
                            before.get(x,y)!=before.get(0,0) for x,y in changed))
        other=tk.Toplevel(self.root);other.update();other.focus_force();self.root.update()
        self.assertTrue(logo.winfo_viewable())
        self.assertIsNone(logo._sweep_job)
        self.assertEqual(logo.itemcget(logo._sweep_item,'state'),'hidden')
        other.destroy();self.root.focus_force();self.root.update()
        self.assertIsNotNone(logo._sweep_job)
        self.root.withdraw();self.root.update()
        self.assertIsNone(logo._sweep_job)
        self.root.deiconify();self.root.focus_force();self.root.update()
        self.assertIsNotNone(logo._sweep_job)
        self.assertIs(logo._sweep_sources,cached)
        logo.show_status('no_data',None)
        self.assertIsNone(logo._sweep_job)

if __name__=='__main__':unittest.main()
