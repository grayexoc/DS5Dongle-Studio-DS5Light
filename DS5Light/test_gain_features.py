import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np

from audio import Engine, OutputProcessor, select_output_device
from core import Controls
from output_gain import OutputGain
from preferences import default_preferences,validate as validate_preferences
from presets import PresetStore
from process_audio import ProcessSampler
from stream_health import StreamHealth


class GainTests(unittest.TestCase):
    def test_unity_bypass_is_bit_exact(self):
        x=np.arange(-32768,32768,dtype=np.int32).astype('<i2').reshape(-1,4).tobytes()
        self.assertEqual(OutputProcessor().process(x,Controls(bypass=True)),x)
    def test_boost_mute_and_output_limit(self):
        x=np.tile(np.array([1000,-1000,30000,-30000],dtype='<i2'),(1920,1)).tobytes()
        level=OutputGain(); y=np.frombuffer(level.process(x,1.5),'<i2').reshape(-1,4)
        np.testing.assert_array_equal(y[-1],[1500,-1500,32767,-32768])
        self.assertGreater(level.limited_samples,0)
        muted=np.frombuffer(level.process(x,0),'<i2').reshape(-1,4)
        np.testing.assert_array_equal(muted[-1],[0,0,0,0])
    def test_slew_is_bounded_and_chunk_independent(self):
        x=np.full((1920,4),8000,dtype='<i2')
        a=OutputGain(); full=np.frombuffer(a.process(x.tobytes(),1.5),'<i2')
        b=OutputGain(); split=np.frombuffer(b''.join(b.process(chunk.tobytes(),1.5) for chunk in np.split(x,16)),'<i2')
        self.assertLessEqual(int(np.max(np.abs(full.astype(int)-split))),1)
        frames=full.reshape(-1,4)[:,0]
        self.assertLessEqual(int(np.max(np.abs(np.diff(frames.astype(int))))),10)
        b.reconnect(); self.assertEqual(b.current,0)
    def test_gain_is_independent_of_filter_bypass(self):
        p=OutputProcessor(); p.level.current=.5
        data=np.full((480,4),1000,dtype='<i2').tobytes()
        output=p.process(data,Controls(bypass=True,gain=.5))
        self.assertTrue(np.all(np.frombuffer(output,'<i2')==500))
    def test_mix_front_only_zeros_rear_with_filter_on_or_off_and_restores(self):
        wave=np.tile([2000,-4000,900,-800],(480,1)).astype('<i2')
        for bypass in (True,False):
            controls=Controls(bypass=bypass)
            def output(front_only):
                p=OutputProcessor();p.level.current=1.
                return np.frombuffer(p.process(wave.tobytes(),controls,front_only=front_only),'<i2').reshape(-1,4)
            legacy=output(False);front=output(True)
            np.testing.assert_array_equal(front[:,:2],legacy[:,:2])
            self.assertTrue(np.any(legacy[:,2:]));self.assertFalse(np.any(front[:,2:]))
    def test_invalid_gain_rejected(self):
        for value in (-.1,1.51,float('nan'),True):
            with self.assertRaises(ValueError): OutputGain().process(bytes(8),value)


class PersistenceTests(unittest.TestCase):
    def test_legacy_preferences_gain_defaults_to_unity(self):
        data=default_preferences(); data['controls'].pop('gain')
        self.assertEqual(validate_preferences({'version':1,'preferences':data})['controls']['gain'],1.)
        data['controls']['gain']=1.51
        with self.assertRaises(ValueError): validate_preferences({'version':1,'preferences':data})
    def test_game_link_migrates_atomically_and_can_be_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'presets.json'
            value=dict(name='Game',game_exe='Game.exe',scope='process',channels=6,input='',output='',controls=asdict(Controls(gain=1.25)))
            legacy=copy.deepcopy(value); legacy['controls'].pop('gain')
            original=json.dumps({'version':4,'slots':[legacy]+[None]*11}).encode()
            path.write_bytes(original)
            store=PresetStore(path); self.assertIsNone(store.error)
            store.save(0,value,bind_game='Game.exe',auto_apply=True)
            loaded=PresetStore(path)
            self.assertEqual(loaded.bound_slot('GAME.EXE'),0)
            self.assertEqual(loaded.slots[0]['controls']['gain'],1.25)
            self.assertEqual(path.with_name('presets.v4.backup.json').read_bytes(),original)
            before=path.read_bytes()
            with patch('presets.os.replace',side_effect=OSError('disk full')):
                with self.assertRaises(OSError): loaded.save(0,value,bind_game='Game.exe',auto_apply=False)
            self.assertEqual(path.read_bytes(),before); self.assertEqual(loaded.bound_slot('Game.exe'),0)
            loaded.save(0,value,bind_game='Game.exe',auto_apply=False)
            self.assertIsNone(PresetStore(path).bound_slot('Game.exe'))


class TransportTests(unittest.TestCase):
    def test_reconnect_pins_endpoint_and_never_routes_to_other_controller(self):
        target=dict(name='DualSense A',index=1,maxOutputChannels=4,endpoint_id='a',hostApi=1)
        other=dict(name='DualSense B',index=2,maxOutputChannels=4,endpoint_id='b',hostApi=1)
        renamed=dict(name='DualSense renamed',index=7,maxOutputChannels=4,endpoint_id='a',hostApi=1)
        rows=[target,other]; opened=[]; engine=Engine(output_name='DualSense A')
        class PA:
            def get_device_info_by_index(self,index): return next(row for row in rows if row['index']==index)
            def get_device_info_generator(self): return iter(rows)
            def get_host_api_info_by_type(self,_): return {'index':1}
            def is_format_supported(self,*args,**kwargs): return True
            def open(self,**kwargs):
                opened.append(kwargs['output_device_index'])
                return SimpleNamespace(get_output_latency=lambda:0)
        def namespace(module):
            ns={}
            def run(args):
                p=module.PyAudio(); p.open(output=True,output_device_index=1,channels=4,rate=48000)
                engine._waiting()
                rows[:]=[other]
                missing=module.PyAudio()
                self.assertIsNone(ns['find_dongle_output'](missing))
                with self.assertRaises(OSError): missing.open(output=True,output_device_index=2,channels=4,rate=48000)
                rows[:]=[renamed,other]
                restored=module.PyAudio()
                self.assertEqual(ns['find_dongle_output'](restored),7)
                restored.open(output=True,output_device_index=7,channels=4,rate=48000)
                self.assertEqual(engine.output_processor.level.current,0)
                return 0
            ns['run']=run; return ns
        endpoints=[{'endpoints':[{'id':'b','name':'DualSense B'}]},
                   {'endpoints':[{'id':'a','name':'DualSense renamed'},{'id':'b','name':'DualSense B'}]}]
        with patch('audio.devices',return_value=[target,other]),patch('audio.pa.PyAudio',PA),patch('audio.original_namespace',side_effect=namespace),patch('audio.endpoint_snapshot',side_effect=endpoints):
            engine._run()
        self.assertEqual(engine.errors,0,engine.status)
        self.assertEqual(opened,[1,7]); self.assertEqual(engine.output_id,'a')
    def test_start_validation_runs_off_ui_thread(self):
        release=threading.Event()
        def conflict():
            release.wait(1); raise RuntimeError('preflight refused')
        engine=Engine()
        with patch('audio.bridge_conflict',side_effect=conflict):
            try:
                start=time.perf_counter(); engine.start()
                self.assertLess(time.perf_counter()-start,.2)
            finally:
                release.set(); engine.thread.join(2)
        self.assertEqual(engine.phase,'error'); self.assertIn('preflight refused',engine.status)
    def test_output_selection_requires_unique_identity(self):
        rows=[dict(name='DualSense',index=1,maxOutputChannels=4,endpoint_id='a'),dict(name='DualSense',index=2,maxOutputChannels=4,endpoint_id='b')]
        with self.assertRaises(RuntimeError): select_output_device(rows)
        self.assertEqual(select_output_device(rows,endpoint_id='b')['index'],2)
        with self.assertRaises(RuntimeError): select_output_device(rows,endpoint_id='missing')
        with self.assertRaises(RuntimeError): select_output_device([dict(name='Speakers',maxOutputChannels=4)])
    def test_recent_health_recovers_and_disconnected_is_distinct(self):
        h=StreamHealth(); h.sample('running',0,1,0,0,0,now=0)
        self.assertEqual(h.sample('running',1,100,0,1,0,now=1)['label'],'전송 불안정')
        self.assertEqual(h.sample('running',7,500,0,1,0,now=7)['label'],'정상')
        self.assertEqual(h.sample('waiting',7,500,0,1,0,now=8)['label'],'장치 연결 대기')
    def test_audio_activity_is_only_sampled_with_list_refresh(self):
        sampler=ProcessSampler()
        audio={'sessions':{1:{'active':True,'peak':.1},2:{'active':True,'peak':0}},'complete':True}
        with patch('process_audio.processes',return_value=[('A.exe',1),('B.exe',2),('C.exe',3)]),patch.object(sampler,'_read_times',return_value=None),patch('process_audio.audio_snapshot',return_value=audio) as query:
            rows=sampler.snapshot()
        self.assertEqual([row['audio'] for row in rows],['playing','active','inactive'])
        query.assert_called_once()
    def test_audio_access_denied_does_not_hide_process_list(self):
        sampler=ProcessSampler()
        with patch('process_audio.processes',return_value=[('Game.exe',123)]),patch.object(sampler,'_read_times',return_value=None),patch('process_audio.audio_snapshot',return_value={'sessions':{},'complete':False}):
            rows=sampler.snapshot()
        self.assertEqual(rows[0]['name'],'Game.exe'); self.assertEqual(rows[0]['audio'],'unknown')


if __name__=='__main__': unittest.main(verbosity=2)
