import tkinter as tk
from tkinter import ttk
import unittest
from ui_controls import install_combobox_selection_cleanup
from studio_option_groups import PLANS

class RevisionTests(unittest.TestCase):
    def test_mute_options_visible_and_gain_below_volume(self):
        groups=PLANS['General Haptics & Audio']
        for _,_,fields,collapsed,_ in groups:
            if 'auto_mute_mix' in fields:self.assertFalse(collapsed)
            if 'speaker_gain' in fields:
                self.assertFalse(collapsed)
                self.assertEqual(fields.split().index('speaker_gain'),fields.split().index('speaker_volume')+1)
    def test_wheel_requires_click(self):
        root=tk.Tk()
        try:
            install_combobox_selection_cleanup(root,'white','black','gray','black')
            combo=ttk.Combobox(root,values=['a','b'],state='readonly');combo.pack();combo.current(0)
            root.update()
            combo.event_generate('<MouseWheel>',delta=-120);root.update()
            self.assertEqual(combo.current(),0)
            combo._wheel_selected=True
            combo.event_generate('<MouseWheel>',delta=-120);root.update()
            self.assertEqual(combo.current(),1)
            combo.event_generate('<FocusOut>');root.update()
            combo.event_generate('<MouseWheel>',delta=120);root.update()
            self.assertEqual(combo.current(),1)
        finally:root.destroy()
