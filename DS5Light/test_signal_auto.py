"""Signal behavior, channel negotiation and Studio UI safety regressions."""
import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from core import Processor,Controls,RATE,BLOCK
from channel_policy import candidates,open_capture,process_hint
from channel_mix import ChannelMixer
from preferences import validate as validate_preferences,default_preferences
from presets import PresetStore
import test_modified_ui as _fixtures
from studio_slots import Slot


def process(x,controls):
    p=Processor();y=[];g=[]
    for i in range(0,len(x),BLOCK):
        y.append(p.process(np.repeat(x[i:i+BLOCK,None],2,axis=1),controls)[:,0])
        g.append(p.gain.copy())
    return np.concatenate(y),np.array(g),p


class SignalBehavior(unittest.TestCase):
    def test_steady_low_tones_do_not_keep_triggering_protection(self):
        t=np.arange(3*RATE)/RATE
        for hz in (30,50,60,80):
            x=.08*np.sin(2*np.pi*hz*t);y,g,p=process(x,Controls())
            self.assertLess(float(np.ptp(20*np.log10(g[-100:,0]))),.04)
            self.assertLess(np.sqrt(np.mean(y[-RATE:]**2)),np.sqrt(np.mean(x[-RATE:]**2))*.46)

    def test_impact_control_preserves_bursts_without_boosting_steady_background(self):
        t=np.arange(4*RATE)/RATE;u=t-2
        x=np.where((u>=0)&(u<.2),.24*np.sin(2*np.pi*60*u)*np.exp(-np.maximum(u,0)/.055),0)
        protected,_,_=process(x,Controls(impact=.85));reduced,_,_=process(x,Controls(impact=0))
        window=slice(2*RATE,2*RATE+9600)
        self.assertGreater(np.linalg.norm(protected[window]),np.linalg.norm(reduced[window])*1.6)
        self.assertLess(np.linalg.norm(protected[window]),np.linalg.norm(x[window])*1.02)

    def test_relative_detection_is_stable_across_game_volume(self):
        t=np.arange(3*RATE)/RATE;u=t-1
        x=np.where((u>=0)&(u<.2),.24*np.sin(2*np.pi*60*u)*np.exp(-np.maximum(u,0)/.055),0)
        loud,_,_=process(x,Controls());quiet,_,_=process(x*.03,Controls())
        np.testing.assert_allclose(quiet,loud*.03,atol=2e-5)

    def test_start_is_attenuated_and_repeated_events_do_not_freeze_learning(self):
        p=Processor();x=np.full((BLOCK,2),.15,dtype=np.float32)
        y=p.process(x,Controls())
        self.assertLess(float(np.max(y)),.09)
        t=np.arange(5*RATE)/RATE
        pulses=.08*np.sin(2*np.pi*60*t)*(np.mod(t,.1)<.06)
        _,_,p=process(pulses,Controls())
        self.assertGreater(float(p.bg[0]),1e-5)
        self.assertTrue(np.all(p.event_cooldown<=.25));self.assertTrue(np.all(p.learn_pause<=.08))

    def test_finite_bounded_and_no_noise_protection(self):
        rng=np.random.default_rng(14);x=rng.normal(0,.8,RATE)
        y,_,_=process(x,Controls(strength=1,impact=1))
        self.assertTrue(np.isfinite(y).all());self.assertLessEqual(float(np.max(np.abs(y))),1.)
        _,_,p=process(np.full(RATE,1e-7),Controls())
        self.assertTrue(np.all(p.hold==0))


class AutomaticChannels(unittest.TestCase):
    def test_supported_choices_and_unknown_fallback(self):
        self.assertEqual(candidates(0,2),(2,));self.assertEqual(candidates(0,6),(6,2))
        self.assertEqual(candidates(0,None),(8,6,2));self.assertEqual(candidates(8),(8,))
        with self.assertRaises(ValueError):candidates(4)

    def test_format_rejection_falls_back_but_target_errors_do_not(self):
        called=[]
        def factory(pid,ch):
            called.append(ch)
            if ch==8:raise RuntimeError('ERROR initialize 0x88890008 Unsupported format')
            return SimpleNamespace(channels=ch)
        stream,ch,hint=open_capture(123,0,factory,hint_reader=lambda _:None)
        self.assertEqual(called,[8,6]);self.assertEqual(ch,6);self.assertIsNone(hint)
        for error in ('access denied','TARGET_EXITED','activation timeout'):
            with self.assertRaises(RuntimeError):
                open_capture(123,0,lambda *_:(_ for _ in ()).throw(RuntimeError(error)),hint_reader=lambda _:None)

    def test_hint_never_reports_partial_enumeration_as_detected(self):
        with patch('channel_policy.snapshot',return_value={'complete':False,'sessions':{123:{'channels':6}}}):
            self.assertIsNone(process_hint(123))
        with patch('channel_policy.snapshot',return_value={'complete':True,'sessions':{123:{'channels':2}}}) as query:
            self.assertEqual(process_hint(123),2);query.assert_called_once_with(channel_pid=123)

    def test_71_sides_and_rears_both_reach_correct_stereo_side(self):
        for column in (4,5,6,7):
            x=np.zeros((1920,8),dtype='<i2');x[:,column]=8000
            y=np.frombuffer(ChannelMixer().process(x.tobytes(),8,RATE,rear=True),'<i2').reshape(-1,8)
            self.assertEqual(y[-1,column%2],2000);self.assertEqual(y[-1,1-column%2],0)

    def test_legacy_options_migrate_to_auto_and_presets_preserve_impact(self):
        data=default_preferences();data.pop('channel_auto');data['channels']=6;data['controls'].pop('impact')
        out=validate_preferences({'version':1,'preferences':data})
        self.assertTrue(out['channel_auto']);self.assertEqual(out['controls']['impact'],.85)
        with tempfile.TemporaryDirectory() as d:
            store=PresetStore(Path(d)/'slots.json')
            value=dict(name='Auto',game_exe='Game.exe',scope='process',channels=0,input='',output='',controls=asdict(Controls(impact=.6)))
            store.save(0,value);again=PresetStore(store.path)
            self.assertEqual(again.slots[0]['channels'],0);self.assertEqual(again.slots[0]['controls']['impact'],.6)


class IntegratedUI(unittest.TestCase):
    setUp=_fixtures.ModifiedUITests.setUp
    tearDown=_fixtures.ModifiedUITests.tearDown
    def test_advanced_controls_are_inline_gold_circles(self):
        self.assertFalse(hasattr(self.ui,'details_button'))
        self.assertEqual(self.ui.advanced.winfo_manager(),'pack')
        self.assertTrue(all(isinstance(w,self.ui.binding_check.__class__) for w in self.ui.advanced_checks))
        self.ui.impact.set(63);self.ui.update_controls();self.assertEqual(self.ui.controls.impact,.63)
        self.assertEqual(self.ui.channel.get(),self.ui.tr('자동') if hasattr(self.ui,'tr') else __import__('app').tr('자동'))

    def test_studio_only_queries_on_demand_and_selection_does_not_activate(self):
        panel=self.ui.studio
        self.assertFalse(panel.busy);self.assertIsNone(panel.poll_id)
        panel.paths=[b'device'];panel.slot_paths=[b'device']
        panel.slots=[Slot(0,'saved','Audio Haptics')];panel.choice.configure(values=['Audio Haptics']);panel.choice.current(0)
        with patch('studio_panel.run_device') as call:
            panel.render();self.assertEqual(call.call_count,0)
            self.ui.engine=SimpleNamespace();panel.activate();self.assertEqual(call.call_count,0)
        self.ui.engine=None

    def test_studio_errors_allow_read_retry_and_leave_no_idle_timer(self):
        panel=self.ui.studio;panel.busy=True
        panel.results.put(('slots',None,'device unplugged'));panel.poll()
        self.assertFalse(panel.busy);self.assertIsNone(panel.poll_id)
        self.assertNotIn('disabled',panel.apply.state());self.assertFalse(panel.slots)
        with patch.object(panel,'discover') as discover:
            panel.apply.invoke()
        discover.assert_called_once_with(allow_running=True,refresh=True)

    def test_channel_rows_are_only_shown_for_explicit_surround_choices(self):
        import app as ui
        for channels in (0,2,6,8):
            self.ui.channel.set(next(label for label,value in ui.CHANNELS.items() if value==channels))
            self.ui.render()
            self.assertEqual(self.ui.channel_details.winfo_manager()=='pack',channels in (6,8))

    def test_compact_studio_resolves_each_profile_to_its_own_device(self):
        panel=self.ui.studio
        self.assertFalse(hasattr(panel,'device'));self.assertFalse(hasattr(panel,'refresh'));self.assertFalse(hasattr(panel,'note'))
        rows=[({'path':b'A','serial_number':'First'},[Slot(0,'saved','One')],None),
              ({'path':b'B','serial_number':'Second'},[Slot(0,'saved','Two')],None)]
        panel.busy=True;panel.results.put(('discover',(rows,[]),None));panel.poll()
        self.assertEqual(panel.slot_paths,[b'A',b'B'])
        self.assertIn('Second',panel.choice['values'][1])
        panel.choice.current(1)
        def activate(path,index=None,action=None):
            self.assertEqual(path,b'B')
            if action=='read_profile_state':
                return dict(index=0,name='Two',auto_haptics_enable=1)
            self.assertEqual(index,0)
            return dict(slot=Slot(0,'saved','Two'),reconnect=False,deferred=False)
        # Keep connected physical hardware out of this two-device fixture.
        with patch('studio_panel.devices',return_value=[row[0] for row in rows]),patch('studio_panel.run_device',side_effect=activate) as call:
            panel.activate()
            until=time.monotonic()+2
            while panel.busy and time.monotonic()<until:self.root.update();time.sleep(.01)
            self.assertFalse(panel.busy)
            self.assertEqual(call.call_count,2)
            self.assertEqual(call.call_args_list[0].args,(b'B',0))
            self.assertEqual(call.call_args_list[1].kwargs,{'action':'read_profile_state'})
