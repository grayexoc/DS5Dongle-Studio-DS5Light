import tkinter as tk
from tkinter import ttk
import unittest
from ui_controls import install_combobox_selection_cleanup
from studio_option_groups import PLANS

class RevisionTests(unittest.TestCase):
    def test_volume_default_marker_and_updated_bilingual_help(self):
        from unittest.mock import patch
        from studio_help import REFERENCE,DEFAULTS,help_text,reference_point
        self.assertNotIn('speaker_volume',REFERENCE)
        self.assertNotIn('headset_volume',REFERENCE)
        self.assertEqual(reference_point('headset_volume'),(None,''))
        self.assertEqual(DEFAULTS['speaker_volume'],127)
        self.assertEqual(reference_point('speaker_volume')[0],127)
        with patch('localization.LANGUAGE','ko'):
            self.assertIn('127은 Windows 장치 볼륨 100%',help_text('speaker_volume'))
            self.assertNotIn('추천 시작값',help_text('speaker_volume'))
            self.assertIn('효과적',help_text('speaker_gain'))
            self.assertNotIn('게임의 음량',help_text('speaker_volume'))
            self.assertIn('스피커 음량을 기준',help_text('headset_volume'))
            self.assertNotIn('기본값 기준',help_text('headset_volume'))
            from studio_help import label
            self.assertNotIn('배터리 절약',label('disable_mic'))
        with patch('localization.LANGUAGE','en'):
            self.assertIn('Default: 127',help_text('speaker_volume'))
            self.assertIn('100% Windows device volume',help_text('speaker_volume'))
            self.assertNotIn('Recommended:',help_text('speaker_volume'))
    def test_mute_options_visible_and_audio_controls_order(self):
        groups=PLANS['General Haptics & Audio']
        order=[key for group in groups for key in group[2].split()]
        self.assertLess(order.index('disable_speaker'),order.index('disable_mic'))
        self.assertNotIn('auto_mute_mix',order)
        audio_order=[key for group in PLANS['Auto-Haptics & Speaker Effect Leak'] for key in group[2].split()]
        self.assertEqual(audio_order.index('auto_mute_mix'),audio_order.index('auto_haptics_gain')+1)
        self.assertEqual(audio_order.index('auto_mute_replace'),audio_order.index('auto_mute_mix')+1)
        for _,_,fields,collapsed,_ in groups:
            if 'auto_mute_mix' in fields:self.assertFalse(collapsed)
            if 'speaker_gain' in fields:
                self.assertFalse(collapsed)
                self.assertEqual(fields.split().index('speaker_gain')+1,fields.split().index('speaker_volume'))
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
