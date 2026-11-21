import json
import unittest
from unittest.mock import patch
import numpy as np
from channel_mix import ChannelMixer, ChannelSignalCheck
from core import Controls
from audio import Engine, OutputProcessor, original_namespace
import test_presets


class MixTests(unittest.TestCase):
    def test_channel_observation_checks_pcm_before_any_mix(self):
        sample=np.array([[-32768,-32768,0,32767,500,500],
                         [0,0,0,0,500,-500],
                         [16384,16384,0,-16384,500,500],
                         [0,0,0,0,500,-500]],dtype='<i2')
        for channels in (6,8):
            with self.subTest(channels=channels):
                frames=np.pad(sample,((0,0),(0,channels-6)))
                check=ChannelSignalCheck(channels,4)
                self.assertIsNone(check.observe(frames[:2].tobytes()))
                observed=check.observe(frames[2:].tobytes())
                self.assertEqual(observed['duplicates'],((1,2),))
                self.assertEqual(observed['correlation'],(1,2,1.0))
                self.assertEqual(observed['clipped'][:4],(1,1,0,1))
                self.assertIsNone(observed['rms_dbfs'][2])
                self.assertIsNone(check.observe(frames[:2].tobytes()))

    def test_disabled_exact_and_stereo_unchanged(self):
        for ch in (1,2,6,8):
            x=np.random.default_rng(ch).integers(-32768,32768,(960,ch),dtype=np.int16).tobytes()
            self.assertEqual(ChannelMixer().process(x,ch,48000),x)
            if ch not in (6,8): self.assertEqual(ChannelMixer().process(x,ch,48000,True,True),x)

    def test_channels_and_center_exclusion(self):
        for rear,lfe in ((False,False),(True,False),(False,True),(True,True)):
            for channel in range(6):
                x=np.zeros((2000,6),dtype='<i2'); x[:,channel]=14000
                y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,rear,lfe),'<i2').reshape(-1,6)
                r=.5*rear; f=.25*lfe
                expected=np.rint(14000*np.array([float(channel==0)+r*(channel==4)+f*(channel==3),
                                                 float(channel==1)+r*(channel==5)+f*(channel==3)]))
                np.testing.assert_array_equal(y[-1,:2],expected)

    def test_slew_and_chunk_invariance_and_return_exact(self):
        x=np.zeros((2880,6),dtype='<i2'); x[:,4:]=24000
        a=ChannelMixer().process(x.tobytes(),6,48000,True,True)
        m=ChannelMixer()
        b=b''.join(m.process(chunk.tobytes(),6,48000,True,True) for chunk in np.split(x,6))
        self.assertEqual(a,b)
        y=np.frombuffer(a,'<i2').reshape(-1,6)[:,:2]
        self.assertLess(np.max(np.abs(np.diff(y.astype(int),axis=0))),20)
        m.process(x.tobytes(),6,48000,False,False)
        self.assertEqual(m.process(x.tobytes(),6,48000),x.tobytes())

    def test_full_scale_no_overflow(self):
        for value in (-32768,32767):
            x=np.full((2000,6),value,dtype='<i2')
            y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,True,True),'<i2').reshape(-1,6)
            np.testing.assert_array_equal(x,y)

    def test_front_only_unity_with_both_switches(self):
        for limiter in ('hard','soft'):
            x=np.zeros((4800,6),dtype='<i2')
            x[:,:2]=np.random.default_rng(23).integers(-32768,32768,(4800,2),dtype=np.int16)
            y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,True,True,limiter),'<i2').reshape(-1,6)
            np.testing.assert_array_equal(y[:,:2],x[:,:2])

    def test_hard_clips_only_excess(self):
        x=np.zeros((4800,6),dtype='<i2'); x[:,0]=30000; x[:,4]=20000; x[:,1]=10000
        y=np.frombuffer(ChannelMixer().process(x.tobytes(),6,48000,True,False,'hard'),'<i2').reshape(-1,6)
        self.assertEqual(y[-1,0],32767)
        np.testing.assert_array_equal(y[:,1],x[:,1])

    def test_soft_links_stereo_and_recovers(self):
        m=ChannelMixer(); m.rear=.5
        x=np.zeros((4800,6),dtype='<i2'); x[:,0]=5000; x[:,1]=10000
        x[0,0]=30000; x[0,4]=20000
        y=np.frombuffer(m.process(x.tobytes(),6,48000,True,False,'soft'),'<i2').reshape(-1,6)
        self.assertEqual(y[0,0],32767)
        self.assertAlmostEqual(y[0,1]/10000,32767/40000,places=4)
        self.assertLess(y[1,0],5000)
        self.assertTrue(np.all(np.diff(y[1:,0].astype(int))>=0))
        np.testing.assert_array_equal(y[-1,:2],x[-1,:2])
        self.assertEqual(m.gain,1.)

    def test_mode_transition_bounded_and_settles(self):
        m=ChannelMixer(); m.rear=.5
        x=np.zeros((1920,6),dtype='<i2'); x[:,0]=30000; x[:,4]=20000; x[:,1]=10000
        m.process(x.tobytes(),6,48000,True,False,'hard')
        y=np.frombuffer(m.process(x.tobytes(),6,48000,True,False,'soft'),'<i2').reshape(-1,6)
        self.assertLess(np.max(np.abs(np.diff(y[:,1].astype(int)))),5)
        self.assertEqual(m.soft_mix,1.)
        m.process(x.tobytes(),6,48000,True,False,'hard')
        self.assertEqual(m.soft_mix,0.)

    def run_capture_layout(self,channels,metadata,*,diagnostics=False):
        x=np.zeros((48000 if diagnostics else 1920,channels),dtype='<i2')
        x[:,:2]=(1000,-2000)
        x[:,2]=30000; x[:,3]=4000; x[:,4]=12000; x[:,5]=-8000
        chunks=[a.tobytes() for a in np.split(x,len(x)//480)]; writes=[]
        class Stream:
            def get_read_available(self): return 480
            def read(self,n,**kw):
                if not chunks: raise KeyboardInterrupt()
                return chunks.pop(0)
            def write(self,data,**kw): writes.append(data)
            def get_input_latency(self): return 0
            def get_output_latency(self): return 0
            def stop_stream(self): pass
            def close(self): pass
        class PA:
            def get_device_info_by_index(self,i):
                return dict(name='DualSense' if i==2 else 'fake',index=i,defaultSampleRate=48000,maxInputChannels=channels,maxOutputChannels=4 if i==2 else 0)
            def is_format_supported(self,*args,**kwargs): return True
            def open(self,**kw): return Stream()
            def terminate(self): pass
        def namespace(module):
            ns=original_namespace(module); run=ns['run']
            def explicit(args):
                args.in_index=1; args.out_index=2
                return run(args)
            ns['run']=explicit
            return ns
        engine=Engine(controls=Controls(bypass=True,rear=True,lfe=True))
        engine.diagnostics_enabled=diagnostics
        input_endpoint=dict(name='fake',index=1,isLoopbackDevice=True,maxOutputChannels=0,**metadata)
        rows=[input_endpoint,dict(name='DualSense',index=2,maxOutputChannels=4)]
        with patch('audio.pa.PyAudio',PA),patch('audio.devices',return_value=rows),patch('audio.original_namespace',side_effect=namespace):
            engine._run()
        self.assertEqual(engine.errors,0)
        actual=np.frombuffer(b''.join(writes),'<i2').reshape(-1,4)
        return engine, x, actual

    def test_legacy_engine_reads_verified_mix_before_channel_extraction(self):
        for channels,mask in ((6,0x3f),(6,0x60f),(8,0x63f)):
            with self.subTest(channels=channels,mask=mask):
                metadata=dict(endpoint_id='input',mix_channels=channels,mix_rate=48000,channel_mask=mask)
                engine,x,actual=self.run_capture_layout(channels,metadata)
                expected=ChannelMixer().process(x.tobytes(),channels,48000,True,True)
                stereo=np.frombuffer(expected,'<i2').reshape(-1,channels)[:,:2]
                self.assertTrue(engine.mix_supported)
                np.testing.assert_array_equal(actual,np.tile(stereo,(1,2)))
                self.assertEqual(OutputProcessor().process(actual.tobytes(),Controls(mode='pure',bypass=True,rear=True,lfe=True)),bytes(actual.nbytes))

    def test_ambiguous_capture_layout_keeps_legacy_first_pair(self):
        for metadata in ({},dict(endpoint_id='input',mix_channels=6,mix_rate=44100,channel_mask=0x3f),
                         dict(endpoint_id='input',mix_channels=6,mix_rate=48000,channel_mask=0x63f)):
            with self.subTest(metadata=metadata):
                engine,x,actual=self.run_capture_layout(6,metadata)
                self.assertFalse(engine.mix_supported)
                np.testing.assert_array_equal(actual,np.tile(x[:,:2],(1,2)))

    def test_diagnostics_observes_original_channels_without_enabling_unverified_mix(self):
        engine,x,actual=self.run_capture_layout(6,{},diagnostics=True)
        np.testing.assert_array_equal(actual,np.tile(x[:,:2],(1,2)))
        levels=engine.stats()['capture_signal']['rms_dbfs']
        np.testing.assert_allclose(levels,20*np.log10(np.abs(x[0].astype(float))/32768))


class MigrationTests(unittest.TestCase):
    setUp = test_presets.PresetTests.setUp
    def test_v1_backup_and_new_switches(self):
        self.path.write_text(json.dumps(dict(version=1,slots=[self.value]+[None]*11)),encoding='utf-8')
        original=self.path.read_bytes()
        from presets import PresetStore
        store=PresetStore(self.path)
        self.assertIsNone(store.error)
        self.value['controls'].update(rear=True,lfe=True)
        store.save(0,self.value)
        self.assertEqual(self.path.with_name('presets.v1.backup.json').read_bytes(),original)
        self.assertEqual(PresetStore(self.path).slots[0],self.value)


if __name__=='__main__': unittest.main()
