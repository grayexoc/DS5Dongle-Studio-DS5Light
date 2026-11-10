"""DPI arithmetic checks; no GUI, device, audio or application launch."""
import unittest
import re
import weakref
from unittest.mock import patch
from ui_dpi import DpiTracker,fit_window,px,ui_scale


class FakeWindow:
    _ui_scale=1.5
    def _root(self):return self
    def winfo_toplevel(self):return self
    def minsize(self,*values):self.minimum=values
    def geometry(self,value):self.geometry_value=value


class TrackedWindow(FakeWindow):
    def __init__(self,root=None):
        self.root=root or self;self.dpi=96;self._ui_scale=1
        self.width=860;self.height=1000;self.minimum=(860,860)
        self.area=(0,0,1920,1080);self.exists=True;self.jobs={};self.bindings={}
    def _root(self):return self.root
    def winfo_exists(self):return self.exists
    def winfo_width(self):return self.width
    def winfo_height(self):return self.height
    def winfo_x(self):return 0
    def winfo_y(self):return 0
    def minsize(self,*values):
        if values:self.minimum=values
        return self.minimum
    def geometry(self,value):
        super().geometry(value)
        self.width,self.height=map(int,re.match(r'(\d+)x(\d+)',value).groups())
    def bind(self,event,callback,add=None):self.bindings[event]=callback
    def state(self):return 'normal'
    def after(self,delay,callback):
        name=f'job{len(self.jobs)}';self.jobs[name]=callback;return name
    def after_cancel(self,name):self.jobs.pop(name,None)


class Observer:
    def __init__(self):self.calls=0
    def winfo_exists(self):return True
    def redraw(self):self.calls+=1


class DpiTests(unittest.TestCase):
    def test_logical_sizes_are_converted_once(self):
        window=FakeWindow()
        self.assertEqual(px(window,20),30)
        with patch('ui_dpi.work_area',return_value=(0,0,1920,1080)):
            fit_window(window,860,1000,logical=True,min_width=1290,min_height=1290)
        self.assertEqual(window.minimum,(1290,1008))
        self.assertEqual(window.geometry_value,'1290x1008')

    def test_small_work_area_caps_minimum_and_saved_size(self):
        window=FakeWindow()
        with patch('ui_dpi.work_area',return_value=(-1280,0,0,720)):
            fit_window(window,5000,5000,min_width=1290,min_height=1290,position=(-2000,-100))
        self.assertEqual(window.minimum,(1244,648))
        self.assertEqual(window.geometry_value,'1244x648+-1280+0')

    def test_style_scaling_uses_original_metrics(self):
        class Style:
            def configure(self,name,**values):self.values=values
        style=Style();tracker=object.__new__(DpiTracker)
        baseline={'padding':(8,6),'rowheight':28}
        tracker._style(style,'Example',baseline,2)
        self.assertEqual(style.values,{'padding':(16,12),'rowheight':56})
        tracker._style(style,'Example',baseline,1.25)
        self.assertEqual(style.values,{'padding':(10,8),'rowheight':35})
        self.assertEqual(baseline,{'padding':(8,6),'rowheight':28})

    def test_monitor_round_trip_restores_original_minimum(self):
        root=TrackedWindow()
        with patch('ui_dpi._window_dpi',side_effect=lambda w:w.dpi),patch.object(DpiTracker,'_fonts'),patch('ui_dpi.work_area',side_effect=lambda w:w.area):
            tracker=DpiTracker(root)
            fit_window(root,860,1000,min_width=860,min_height=860)
            root.dpi=144;root.area=(0,0,1280,720);tracker._update(root)
            self.assertEqual(root.minimum,(1244,648))
            root.dpi=96;root.area=(0,0,1920,1080);tracker._update(root)
            self.assertEqual(root.minimum,(860,860))
            self.assertEqual(root._dpi_minimum,(860,860))

    def test_popups_share_font_scale_and_receive_root_changes(self):
        root=TrackedWindow();popup=TrackedWindow(root);popup.dpi=192
        observer=Observer()
        with patch('ui_dpi._window_dpi',side_effect=lambda w:w.dpi),patch.object(DpiTracker,'_fonts') as fonts,patch('ui_dpi.work_area',side_effect=lambda w:w.area):
            tracker=DpiTracker(root);tracker.watch_window(popup)
            tracker.windows[popup]['widgets'][observer]=weakref.WeakMethod(observer.redraw)
            self.assertEqual(ui_scale(popup),1)
            tracker._update(popup)
            self.assertEqual(observer.calls,0)
            root.dpi=144;tracker._update(root)
            self.assertEqual(ui_scale(popup),1.5)
            self.assertEqual(popup._ui_scale,1.5)
            self.assertEqual(observer.calls,1)
            fonts.assert_called_with(1.5)

    def test_destroy_cancels_pending_dpi_callback(self):
        root=TrackedWindow();popup=TrackedWindow(root)
        with patch('ui_dpi._window_dpi',return_value=96),patch.object(DpiTracker,'_fonts'):
            tracker=DpiTracker(root);tracker.watch_window(popup)
            tracker._schedule(popup)
            self.assertEqual(len(popup.jobs),1)
            event=type('Event',(),{'widget':popup})()
            popup.exists=False;popup.bindings['<Destroy>'](event)
            self.assertEqual(popup.jobs,{})
            self.assertNotIn(popup,tracker.windows)
            tracker._update(popup)

    def test_dialog_uses_owner_work_area_with_negative_coordinates(self):
        owner=FakeWindow();dialog=FakeWindow()
        with patch('ui_dpi.work_area',return_value=(-1920,-1080,0,0)) as area:
            fit_window(dialog,400,300,position=(-1800,-900),reference=owner)
        area.assert_called_once_with(owner)
        self.assertEqual(dialog.geometry_value,'400x300+-1800+-900')


if __name__=='__main__':unittest.main()
