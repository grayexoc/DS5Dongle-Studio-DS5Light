"""0.2: original bridge transport + optional output DSP. No recording/network."""

from studio_i18n import text as _ui_tr
import ast

import ctypes

import io

import json

import subprocess

import threading

import time

from collections import deque

from pathlib import Path

from types import SimpleNamespace

import numpy as np

import pyaudiowpatch as pa

from core import Controls, Processor, RumbleStateProvider

from process_audio import ProcessCaptureStream

from channel_mix import ChannelMixer

from output_gain import OutputGain

from stream_health import StreamHealth

from windows_audio import attach_endpoint_ids, snapshot as endpoint_snapshot

from channel_policy import open_capture

from reconnect_policy import RetryCadence



ORIGINAL = Path(__file__).parent/'vendor/ds5audio_original.py'



def original_namespace(pyaudio_module=pa):

    # Keep original functions/constants verbatim. Omit launcher-only imports-in-try,

    # __main__, and pythonw logging redirection; the GUI owns lifecycle/logging.

    tree = ast.parse(ORIGINAL.read_text(encoding='utf-8'), filename=str(ORIGINAL))

    tree.body = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef))]

    ns = {'__name__':'ds5audio_embedded', 'pyaudio':pyaudio_module}

    exec(compile(tree,str(ORIGINAL),'exec'),ns)

    ns['pyaudio'] = pyaudio_module

    ns['print'] = lambda *a,**k: None

    ns['sys'] = SimpleNamespace(stderr=io.StringIO())

    return ns



def devices(p=None):

    owned=p is None
    if owned:p=pa.PyAudio()

    try:

        api=p.get_host_api_info_by_type(pa.paWASAPI)['index']

        return attach_endpoint_ids([dict(d) for d in p.get_device_info_generator() if d['hostApi']==api])

    finally:
        if owned:p.terminate()





def select_output_device(rows,name=None,endpoint_id=None):

    candidates=[d for d in rows if d.get('maxOutputChannels',0)>=4 and not d.get('isLoopbackDevice')

                and any(name in d.get('name','').lower() for name in ('dualsense','studio xinput experiment'))]

    if endpoint_id: candidates=[d for d in candidates if d.get('endpoint_id')==endpoint_id]

    elif name is not None: candidates=[d for d in candidates if d['name']==name]

    if not candidates: raise RuntimeError(_ui_tr('선택한 DualSense 출력 장치가 연결되어 있지 않습니다.'))

    if len(candidates)!=1: raise RuntimeError(_ui_tr('DualSense 출력 장치가 여러 개입니다. 직접 선택하세요.'))

    return candidates[0]



def bridge_conflict():

    command = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python.*\\.exe$' -and $_.CommandLine -match '(?i)(?:[\\\\/]|[\"\\s])ds5audio\\.py(?=[\"\\s]|$)' } | Select-Object ProcessId,Name | ConvertTo-Json -Compress"

    result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,timeout=8,creationflags=0x08000000)

    if result.returncode: raise RuntimeError(_ui_tr('기존 브리지 조회 실패. 프로세스 조회 권한을 확인하세요.'))

    if result.stdout.strip(): raise RuntimeError(_ui_tr('기존 ds5audio.py 실행 중: 기존 창에서 먼저 종료하세요.'))



class InstanceLock:

    def __init__(self,name='Local\\DS5LightPreprocessor-v1'):

        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)

        self.kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]

        self.kernel.CreateMutexW.restype=ctypes.c_void_p

        self.handle=self.kernel.CreateMutexW(None,False,name)

        if not self.handle or ctypes.get_last_error()==183:

            if self.handle: self.close()

            raise RuntimeError(_ui_tr('전처리기가 이미 실행 중입니다.'))

    def close(self):

        if self.handle:

            self.kernel.CloseHandle.argtypes=[ctypes.c_void_p]

            self.kernel.CloseHandle(self.handle); self.handle=None



class OutputProcessor:

    """Input is the original bridge's final interleaved 4ch int16 bytes."""

    def __init__(self):

        self.processor=Processor(); self.last_policy=None; self.level=OutputGain()

        self._capacity=0

    def _buffers(self,n):

        if n>self._capacity:

            self._capacity=max(n,480)

            self._input=np.empty((self._capacity,2),np.float32)

            self._output=np.empty((self._capacity,2),np.float32)

            self._pcm=np.empty((self._capacity,4),dtype="<i2")

    def process(self, data, controls):

        if controls.mode=='pure':

            self.last_policy='pure'

            return bytes(len(data))

        if controls.mode!='normal': raise ValueError(_ui_tr('알 수 없는 모드'))

        if controls.bypass:

            self.last_policy='bypass'

            return self.level.process(data,controls.gain)  # Exact original bytes at steady 100%.

        if self.last_policy in ('bypass','pure'):

            self.processor=Processor()

        self.last_policy='filtered'

        source=np.frombuffer(data,'<i2').reshape(-1,4)

        n=len(source)

        if not n:return self.level.process(data,controls.gain)

        self._buffers(n)

        x=self._input[:n];out=self._output[:n];pcm=self._pcm[:n]

        np.copyto(x,source[:,:2]);x/=32768

        for i in range(0,n,240):

            out[i:i+240]=self.processor.process(x[i:i+240],controls,now=time.perf_counter())

        np.multiply(out,32768,out=out);np.rint(out,out=out);np.clip(out,-32768,32767,out=out)

        pcm[:,:2]=out;pcm[:,2:]=pcm[:,:2]

        return self.level.process(pcm.tobytes(),controls.gain)



def duplicate_stereo_pcm(data):

    """Exact [L,R,L,R] routing without per-frame Python packing."""

    stereo=np.frombuffer(data,dtype='<i2').reshape(-1,2)

    return np.tile(stereo,(1,2)).tobytes()





class StereoDuplicator:

    """One audio-thread scratch buffer; returned bytes own their memory."""

    def __init__(self):self.capacity=0

    def process(self,data):

        source=np.frombuffer(data,dtype='<i2').reshape(-1,2);n=len(source)

        if not n:return b''

        if n>self.capacity:

            self.capacity=max(n,480);self.pcm=np.empty((self.capacity,4),dtype='<i2')

        output=self.pcm[:n];output[:,:2]=source;output[:,2:]=source

        return output.tobytes()





class Engine:

    def __init__(self,input_name=None,output_name=None,controls=Controls(),silent=False,process_pid=None,process_channels=0,transport_frames=None,binding=None):

        # Measured benefit for process capture; device loopback retains its

        # larger block because smaller blocks did not reduce host latency.

        if transport_frames is None:transport_frames=240 if process_pid else 480

        if type(transport_frames) is not int or transport_frames not in (240,480):raise ValueError('Unsupported transport block size')

        self.transport_frames=transport_frames;self.buffer_fallbacks=0

        self.binding=binding;self.retry_cadence=RetryCadence()

        self.input_name,self.output_name=input_name,output_name

        self.controls,self.silent=controls,silent

        self.provider=RumbleStateProvider()

        self.stop_event=threading.Event(); self.thread=None

        self.status=_ui_tr('대기'); self.times=deque(maxlen=12000)

        self.blocks=0; self.errors=0; self.peak=0.; self.latencies={}; self.opens=[]

        self.output_processor=OutputProcessor()

        self.process_pid,self.process_channels=process_pid,process_channels

        self.process_stream=None

        self.capture_channels=None

        self.output_lookup_active=False;self.output_wait_reason='';self.output_id=None; self.phase='starting'; self.reconnecting=False; self.reconnect_count=0

        self.requested_channels=process_channels;self.channel_hint=None;self.mix_supported=True

        self.last_block_time=None; self.health=StreamHealth()

        self.capture_timing_source='process_timestamp' if process_pid else 'device_queue_estimate'

        self.capture_read_errors=0

        self._capture_timing=None

        self.diagnostics_enabled=False
        self.latency_samples={key:deque(maxlen=512) for key in ('pc_queue_ms','capture_to_output_call_ms','output_write_wait_ms')}

    def start(self):

        if self.thread and self.thread.is_alive(): return

        def launch():

            try:

                bridge_conflict(); self._check(); self._run()

            except KeyboardInterrupt: self.status=_ui_tr('정지'); self.phase='stopped'

            except Exception as exc: self.status=_ui_tr('오류: ')+str(exc); self.phase='error'; self.errors+=1

        self.thread=threading.Thread(target=launch,daemon=True); self.thread.start()

    def stop(self):

        self.stop_event.set()

        wake=getattr(self.process_stream,'wake_waiters',None)

        if wake:wake()

        if self.thread: self.thread.join(timeout=4)

        return not self.thread or not self.thread.is_alive()

    def stats(self):

        a=list(self.times)

        drops=self.process_stream.drops if self.process_stream else 0

        stale=self.process_stream.stale if self.process_stream else 0

        latency_ms={}

        for key,samples in self.latency_samples.items():

            values=list(samples)

            latency_ms[key]=dict(zip(('p50','p95','max'),np.percentile(values,[50,95,100]).tolist())) if values else {}

        buffer_snapshot=getattr(self.process_stream,'buffer_snapshot',None)

        return dict(status=self.status,blocks=self.blocks,errors=self.errors,peak=self.peak,

            dsp_ms=dict(zip(('p50','p95','p99','max'),np.percentile(a,[50,95,99,100]).tolist())) if a else {},

            stream_latency=self.latencies,transport=f'legacy int16 / {self.transport_frames} / blocking',

            transport_frames=self.transport_frames,buffer_fallbacks=self.buffer_fallbacks,

            capture_timing_source=self.capture_timing_source,capture_read_errors=self.capture_read_errors,

            drop_underrun=_ui_tr('원본 방식: 드라이버 손실 횟수 계측 안 함'),pure=self.provider.status,

            process_pid=self.process_pid,process_channels=self.process_channels if self.process_pid else None,

            capture_channels=self.capture_channels,

            channel_hint=self.channel_hint,channel_auto=self.requested_channels==0,mix_supported=self.mix_supported,

            process_drop=drops,process_stale=stale,

            latency_ms=latency_ms,capture_buffer=buffer_snapshot() if buffer_snapshot else {},

            latency_scope='PC only; USB, Bluetooth and controller playback are not measured',

            health=self.health.sample(self.phase,self.last_block_time,self.blocks,self.errors,drops,stale),

            reconnect_count=self.reconnect_count,output_name=self.output_name,

            output_limited_samples=self.output_processor.level.limited_samples)

    def _output_issue(self,rows):
        from output_debug import record
        record('output_identification_failed', rows, self.binding, self.output_name)
        issue=self.binding.output_issue(rows) if self.binding is not None else 'missing'
        return {'missing':_ui_tr('4채널 오디오 출력 없음 · 듀얼센스 연결과 Windows 출력 장치를 확인하세요'),
                'ambiguous':_ui_tr('오디오 출력 이름 중복 · 장치 이름을 구분한 뒤 다시 선택하세요'),
                'identity':_ui_tr('출력 식별 실패 · 설정·진단에서 Pico 오디오 출력을 직접 선택하고 시작하세요')}[issue]

    def _waiting(self):

        self.phase='waiting'; self.reconnecting=True; self.status=_ui_tr('장치 연결 대기 중')

    def _check(self):

        if self.stop_event.is_set(): raise KeyboardInterrupt()

    def _run(self):

        engine=self
        from stream_cleanup import OwnedStream
        owned_streams=[]

        class Stream(OwnedStream):

            def __init__(self,stream,kwargs):

                super().__init__(stream, output=bool(kwargs.get("output")))
                self.kwargs=kwargs
                owned_streams[:]=[item for item in owned_streams if not item.closed]
                owned_streams.append(self)

                self.channel_mixer=ChannelMixer()

                if kwargs.get('input'): engine.capture_channels=kwargs['channels']

            def __getattr__(self,name): return getattr(self.stream,name)

            def read(self,n,**kwargs):

                # The process pipe wakes on data/EOF. Device-wide PortAudio keeps

                # its existing waiting policy until a different backend is evaluated.

                try:

                    event_read=getattr(self.stream,'read_wait',None)

                    if event_read:

                        data=event_read(n,engine.stop_event)

                    else:

                        available=self.stream.get_read_available()

                        while available<n:

                            engine._check(); engine.stop_event.wait(.002)

                            available=self.stream.get_read_available()

                        engine._check()

                        # Queue-depth estimate, not a hardware/ADC timestamp.

                        captured=time.perf_counter()-available/self.kwargs['rate'] if engine.diagnostics_enabled else None

                        data=self.stream.read(n,**kwargs)

                except OSError:

                    engine.capture_read_errors+=1

                    engine._waiting(); raise

                engine._capture_timing=(getattr(self.stream,'last_read_timing',None) if event_read

                                        else ((captured,time.perf_counter()) if engine.diagnostics_enabled else None))

                if engine.diagnostics_enabled and engine._capture_timing:

                    engine.latency_samples['pc_queue_ms'].append(max(0.,time.perf_counter()-engine._capture_timing[1])*1000)

                controls=engine.controls

                ch=self.kwargs['channels']

                if ch==8 and not engine.process_pid and not engine.mix_supported:ch=0

                return self.channel_mixer.process(data,ch,self.kwargs['rate'],controls.rear,controls.lfe,controls.limiter,center=controls.center)

            def write(self,data,**kwargs):

                engine._check(); diagnose=engine.diagnostics_enabled; start=time.perf_counter() if diagnose else 0.

                try: out=engine.output_processor.process(data,engine.controls)

                except Exception as exc:

                    engine.errors+=1; engine.status=_ui_tr('필터 오류: 무음 ')+str(exc); out=bytes(len(data))

                if diagnose: engine.times.append((time.perf_counter()-start)*1000)

                if engine.silent: out=bytes(len(out))

                submitted=time.perf_counter() if diagnose else 0.

                timing=engine._capture_timing

                if diagnose and timing and timing[0] is not None:

                    engine.latency_samples['capture_to_output_call_ms'].append(max(0.,submitted-timing[0])*1000)

                engine._check()
                try: self.stream.write(out,**kwargs)

                except OSError:

                    engine.output_wait_reason=_ui_tr('오디오 전송 실패 · 출력 장치 연결 상태를 확인하세요'); engine._waiting(); raise

                if diagnose: engine.latency_samples['output_write_wait_ms'].append((time.perf_counter()-submitted)*1000)

                engine.blocks+=1

                engine.last_block_time=time.monotonic()

                engine.retry_cadence.reset()

                if diagnose and data:

                    samples=np.frombuffer(data,'<i2')

                    engine.peak=max(int(samples.max()),-int(samples.min()))/32768

        class PA:

            def __init__(self):

                self.actual=pa.PyAudio(); self.output_name=engine.output_name;self.selected_output=None

                if engine.binding is not None:

                    api=self.actual.get_host_api_info_by_type(pa.paWASAPI)['index']

                    rows=[dict(d) for d in self.actual.get_device_info_generator() if d.get('hostApi')==api]

                    endpoints=(endpoint_snapshot(False)['endpoints'] if engine.reconnecting else

                               [dict(id=d['endpoint_id'],name=d['name'],container_id=d.get('container_id'))

                                for d in engine.input_devices if d.get('endpoint_id') and not d.get('isLoopbackDevice')])

                    attach_endpoint_ids(rows,endpoints=endpoints)

                    self.selected_output=engine.binding.output(rows)

                    self.output_name=self.selected_output['name'] if self.selected_output else None

                elif engine.reconnecting and engine.output_id:

                    matches=[d for d in endpoint_snapshot(False)['endpoints'] if d['id']==engine.output_id]

                    self.output_name=matches[0]['name'] if len(matches)==1 else None

            def __getattr__(self,name): return getattr(self.actual,name)

            def get_device_info_by_index(self,index):

                if index==-7007:

                    return dict(name=_ui_tr('게임 PID ')+str(engine.process_pid),defaultSampleRate=48000,maxInputChannels=engine.process_channels)

                return self.actual.get_device_info_by_index(index)

            def open(self,**kwargs):

                engine._check()

                if kwargs.get('output'):

                    d=self.actual.get_device_info_by_index(kwargs['output_device_index'])

                    selected_ok=(engine.binding is None or self.selected_output is not None and d['index']==self.selected_output['index'])

                    if not selected_ok or not self.output_name or d['name']!=self.output_name or d.get('maxOutputChannels',0)<4:

                        engine.output_wait_reason=engine._output_issue(engine.input_devices); engine._waiting(); raise OSError(engine.output_wait_reason)

                    if 'hostApi' in d and d['hostApi']!=self.actual.get_host_api_info_by_type(pa.paWASAPI)['index']:

                        engine.output_wait_reason=engine._output_issue(engine.input_devices); engine._waiting(); raise OSError(engine.output_wait_reason)

                    try:

                        self.actual.is_format_supported(48000,output_device=d['index'],output_channels=4,output_format=pa.paInt16)

                    except ValueError as exc:

                        raise RuntimeError(_ui_tr('출력 장치가 4채널 48kHz 형식을 지원하지 않습니다.')) from exc

                if engine.process_pid and kwargs.get('input') and kwargs.get('input_device_index')!=-7007:

                    raise RuntimeError(_ui_tr('지정 프로세스에서 장치 전체 캡처로 전환하려는 경로를 차단했습니다'))

                if kwargs.get('input') and kwargs.get('input_device_index')==-7007:

                    if engine.process_stream is None or engine.process_stream.closed:

                        engine.process_stream=ProcessCaptureStream(engine.process_pid,engine.process_channels)

                    engine.latencies['input_s']=None

                    return Stream(engine.process_stream,kwargs)

                if kwargs.get('input'):

                    d=self.actual.get_device_info_by_index(kwargs['input_device_index'])

                    match=next((row for row in engine.input_devices if row['name']==d['name']),{})

                    engine.mix_supported=kwargs['channels']!=8 or match.get('channel_mask')==0x63f

                    if any(name in d['name'].lower() for name in ('dualsense','studio xinput experiment')):

                        raise OSError(_ui_tr('자기 출력 재캡처 차단'))

                try: s=self.actual.open(**kwargs)

                except OSError:

                    engine.output_wait_reason=(_ui_tr('오디오 입력 열기 실패 · 재생 장치와 캡쳐 권한을 확인하세요') if kwargs.get('input') else _ui_tr('오디오 출력 열기 실패 · 다른 앱의 독점 사용과 장치 상태를 확인하세요'))
                    # Some drivers reject the smaller host buffer. Fall back on

                    # the same selected endpoint, without changing the routing.

                    if kwargs.get('frames_per_buffer')!=240:

                        engine._waiting(); raise

                    kwargs=dict(kwargs,frames_per_buffer=480)

                    try:s=self.actual.open(**kwargs)

                    except OSError:

                        engine._waiting();raise

                    engine.buffer_fallbacks+=1

                engine.opens.append(dict(kwargs)); engine.opens=engine.opens[-8:]

                if kwargs.get('input'): engine.latencies['input_s']=s.get_input_latency()

                else:

                    discard=getattr(engine.process_stream,'discard_backlog',None)

                    if discard:discard()

                    engine._capture_timing=None

                    if engine.reconnecting: engine.output_processor.level.reconnect()

                    if engine.binding is not None and self.selected_output:

                        engine.binding.bind_output(self.selected_output);engine.output_id=engine.binding.snapshot().endpoint_id

                    engine.output_wait_reason=''; engine.phase='running'; engine.reconnecting=False; engine.output_name=self.output_name

                    engine.latencies['output_s']=s.get_output_latency()

                    engine.status=_ui_tr('전역 오디오 캡쳐 작동중..')+(_ui_tr(' · 무음 시험') if engine.silent else '')

                    if engine.process_pid: engine.status=_ui_tr('지정 프로세스 PID ')+str(engine.process_pid)+(_ui_tr(' · 무음 시험') if engine.silent else '')

                return Stream(s,kwargs)

        class PAModule:

            PyAudio=PA

            def __getattr__(self,name): return getattr(pa,name)

        class Clock:

            def time(self): engine._check(); return time.time()

            def sleep(self,seconds):

                if engine.reconnecting:

                    engine.reconnect_count+=1

                    expected=engine.binding is not None and time.monotonic()<engine.binding.fast_until

                    seconds=engine.retry_cadence.next_delay(expected)

                engine.stop_event.wait(seconds); engine._check()

        ns=original_namespace(PAModule()); ns['time']=Clock()

        ns['FRAMES_PER_BUFFER']=self.transport_frames

        duplicate_pcm=StereoDuplicator()

        original_map=ns.get('map_stereo_to_4ch')

        if original_map is not None:

            ns['map_stereo_to_4ch']=lambda data,mode: (duplicate_pcm.process(data) if mode=='duplicate'

                                                     else original_map(data,mode))

        if self.process_pid:

            # Legacy reconnect code can fall back to the default device. Never

            # permit that when process isolation was requested.

            ns['find_loopback_by_name']=lambda p,name:-7007

            ns['find_default_loopback']=lambda p:-7007

        try:

            ds=devices()

            self.input_devices=ds

            if self.binding is not None:

                output=self.binding.output(ds,self.output_name)

                self.output_lookup_active=True
                deadline=time.monotonic()+8

                while output is None and time.monotonic()<deadline:

                    self.output_wait_reason=self._output_issue(ds)
                    self._waiting()

                    self.stop_event.wait(min(self.retry_cadence.next_delay(True),max(0.,deadline-time.monotonic())));self._check()

                    ds=devices();self._check();self.input_devices=ds;output=self.binding.output(ds,self.output_name)

                self.output_lookup_active=False
                if output is None:raise RuntimeError(self._output_issue(ds))

                from output_debug import record
                record('output_selected', [output], self.binding, self.output_name)
                self.binding.bind_output(output)

            else:output=select_output_device(ds,self.output_name,self.output_id)

            self.output_name=output['name']; self.output_id=output.get('endpoint_id')

            if self.process_pid:

                self.process_stream,self.process_channels,self.channel_hint=open_capture(self.process_pid,self.requested_channels,ProcessCaptureStream,self._check)

                self.capture_channels=self.process_channels

            def pinned_output(p,debug=False):

                if engine.binding is not None:return p.selected_output['index'] if p.selected_output else None

                expected=p.output_name

                api=p.get_host_api_info_by_type(pa.paWASAPI)['index']

                matches=[d for d in p.get_device_info_generator() if expected and d['name']==expected

                         and d.get('hostApi')==api and d.get('maxOutputChannels',0)>=4 and not d.get('isLoopbackDevice')]

                return matches[0]['index'] if len(matches)==1 else None

            ns['find_dongle_output']=pinned_output

            def index(name,is_input):

                if name is None: return None

                found=[d for d in ds if d['name']==name and (d.get('isLoopbackDevice') if is_input else d['maxOutputChannels']>=4)]

                if len(found)!=1: raise RuntimeError(_ui_tr('선택한 장치 없음/중복: 다시 선택하세요'))

                return found[0]['index']

            args=SimpleNamespace(list=False,in_index=-7007 if self.process_pid else index(self.input_name,True),out_index=output['index'],

                capture_name=None,auto_capture=False,wait_device=30.,map='duplicate',verbose=False)

            code=ns['run'](args)

            if code: self.status=_ui_tr('브리지 오류: ')+ns['sys'].stderr.getvalue()[-600:]; self.errors+=1

            else: self.status=_ui_tr('정지')

        except KeyboardInterrupt: self.status=_ui_tr('정지')

        except Exception as exc: self.status=_ui_tr('오류: ')+str(exc); self.errors+=1

        finally:

            self.phase='stopped' if self.stop_event.is_set() or self.status==_ui_tr('정지') else 'error'
            # Also runs if legacy cleanup fails before reaching another stream.
            # Playback first, then capture; each resource has an independent close.
            for owned in sorted(owned_streams, key=lambda item: not item.output):
                try: owned.close()
                except Exception: pass
            self._capture_timing=None


            if self.process_stream:

                try: self.process_stream.close()

                except Exception: pass

            self.provider.close()



if __name__=='__main__':

    import argparse

    parser=argparse.ArgumentParser(); parser.add_argument('--list',action='store_true')

    parser.add_argument('--silent-probe',type=float,default=0)

    args=parser.parse_args()

    if args.list: print(json.dumps(devices(),ensure_ascii=False,indent=2))

    elif args.silent_probe:

        lock=InstanceLock(); e=Engine(controls=Controls(bypass=True),silent=True)

        try: e.start(); time.sleep(min(args.silent_probe,30))

        finally:

            e.stop(); print(json.dumps(e.stats(),ensure_ascii=False,indent=2)); lock.close()

