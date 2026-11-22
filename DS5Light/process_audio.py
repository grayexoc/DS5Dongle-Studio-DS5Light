"""Windows per-process loopback helper transport. Fail closed, never full-system fallback."""
from thread_start import start_thread
from studio_i18n import text as _ui_tr
import csv
import ctypes
import io
import math
import os
import struct
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from datetime import datetime
from ctypes import wintypes
from windows_audio import snapshot as audio_snapshot
from process_filter import is_excluded_process
from capture_clock import CaptureClock

HELPER=Path(__file__).with_name('ProcessCapture.exe')
CAPTURE_RATE=48000
CAPTURE_READ_FRAMES=480
MAX_TRANSPORT_AGE=.060

def processes():
    result=subprocess.run(['tasklist.exe','/FO','CSV','/NH'],capture_output=True,timeout=8,creationflags=0x08000000)
    if result.returncode: raise RuntimeError(_ui_tr('프로그램 목록 조회 실패'))
    import locale
    rows=csv.reader(io.StringIO(result.stdout.decode(locale.getpreferredencoding(False),errors='replace')))
    out=[]
    for row in rows:
        if len(row)>1 and row[1].isdigit() and not is_excluded_process(row[0]) and int(row[1])!=os.getpid():
            out.append((row[0],int(row[1])))
    return sorted(out,key=lambda x:(x[0].lower(),x[1]))


class ProcessSampler:
    """Collect creation time and interval CPU use without a third-party package."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class FILETIME(ctypes.Structure):
        _fields_ = [('low', wintypes.DWORD), ('high', wintypes.DWORD)]

    def __init__(self):
        self.previous = {}
        self.last_sample = None
        self.cores = max(1, os.cpu_count() or 1)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True) if os.name == 'nt' else None
        if self.kernel:
            self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.kernel.OpenProcess.restype = wintypes.HANDLE
            self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(self.FILETIME), ctypes.POINTER(self.FILETIME), ctypes.POINTER(self.FILETIME), ctypes.POINTER(self.FILETIME)]
            self.kernel.GetProcessTimes.restype = wintypes.BOOL
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            self.kernel.GetExitCodeProcess.restype = wintypes.BOOL

    @staticmethod
    def _ticks(value):
        return (value.high << 32) | value.low

    def _read_times(self, pid):
        if not self.kernel:
            return None
        handle = self.kernel.OpenProcess(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creation, exit_time, kernel_time, user_time = (self.FILETIME() for _ in range(4))
            if not self.kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                return None
            start_ticks = self._ticks(creation)
            cpu_ticks = self._ticks(kernel_time) + self._ticks(user_time)
            return (start_ticks - 116444736000000000) / 10_000_000, cpu_ticks / 10_000_000
        finally:
            self.kernel.CloseHandle(handle)

    def is_running(self, pid, expected_started=None):
        """Return True, False (confirmed exit/reuse), or None (cannot inspect)."""
        if not self.kernel:
            return None
        handle = self.kernel.OpenProcess(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False if ctypes.get_last_error() in (87, 1168) else None
        try:
            creation, exit_time, kernel_time, user_time = (self.FILETIME() for _ in range(4))
            if not self.kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                                               ctypes.byref(kernel_time), ctypes.byref(user_time)):
                return None
            if self._ticks(exit_time):
                return False
            if expected_started is not None:
                started = (self._ticks(creation) - 116444736000000000) / 10_000_000
                if abs(started - expected_started) > 0.01:
                    return False
            exit_code = wintypes.DWORD()
            if not self.kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return None
            return exit_code.value == 259
        finally:
            self.kernel.CloseHandle(handle)

    def snapshot(self, *, cpu_interval=0):
        rows = processes()
        rows = [(name,pid) for name,pid in rows if pid!=os.getpid() and not is_excluded_process(name)]
        audio=audio_snapshot()
        previous = self.previous
        sampled_at = self.last_sample
        if cpu_interval:
            sampled_at = time.perf_counter()
            previous = {pid:self._read_times(pid) for _,pid in rows}
            time.sleep(cpu_interval)
        now = time.perf_counter()
        current = {}
        elapsed = now - sampled_at if sampled_at is not None else 0
        result = []
        for name, pid in rows:
            times = self._read_times(pid)
            started = times[0] if times else None
            cpu_seconds = times[1] if times else None
            old = previous.get(pid)
            cpu_percent = None
            if times and old and old[0] == started and elapsed > 0:
                cpu_percent = max(0.0, min(100.0, (cpu_seconds - old[1]) / elapsed / self.cores * 100))
            if times:
                current[pid] = times
            session=audio['sessions'].get(pid)
            activity=('playing' if (session.get('peak') or 0)>.0001 else 'active') if session else 'inactive' if audio['complete'] else 'unknown'
            result.append({'name': name, 'pid': pid, 'started': started, 'cpu': cpu_percent,'audio':activity})
        self.previous = current
        self.last_sample = now
        return result

    @staticmethod
    def started_label(timestamp):
        if timestamp is None:
            return '—'
        try:
            return datetime.fromtimestamp(timestamp).strftime('%H:%M')
        except (OverflowError, OSError, ValueError):
            return '—'

class ProcessCaptureStream:
    def __init__(self,pid,channels=6):
        if channels not in (2,6,8): raise ValueError(_ui_tr('게임 캡처 채널은 2, 6 또는 8'))
        self.pid,self.channels=pid,channels
        self.closed=False; self.error=None; self.ready=threading.Event()
        self.lock=threading.Lock(); self.queue=deque(maxlen=8); self.pending=bytearray()
        self.condition=threading.Condition(self.lock); self.pending_segments=deque()
        self.pending_time=0.0
        self.drops=0; self.stale=0; self.messages=deque(maxlen=12)
        self.protocol=None; self.last_read_timing=None; self.discard_before=0.
        self.prefill_discarded_frames=0; self.timestamp_errors=0; self.discontinuities=0
        self._packet_frames=CAPTURE_READ_FRAMES
        self.reader=threading.Thread(target=self._read,daemon=True)
        self.err_reader=threading.Thread(target=self._errors,daemon=True)
        self.child=subprocess.Popen([str(HELPER),str(pid),str(channels)],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,creationflags=0x08000000)
        try:
            start_thread(self.reader)
            start_thread(self.err_reader)
            if not self.ready.wait(7) or self.error:
                raise RuntimeError(_ui_tr('게임 캡처 시작 실패: ')+(self.error or _ui_tr('시간 초과'))+' / '+' '.join(self.messages))
        except Exception:
            self.close()
            raise
    def _errors(self):
        import locale
        try:
            for line in iter(self.child.stderr.readline,b''):
                self.messages.append(line.decode(locale.getpreferredencoding(False),errors='replace').strip())
        except (OSError,ValueError): pass
    def _exact(self,n):
        parts=bytearray()
        while len(parts)<n:
            data=self.child.stdout.read(n-len(parts))
            if not data: raise EOFError(_ui_tr('게임 종료 또는 캡처 프로세스 중단'))
            parts.extend(data)
        return bytes(parts)
    def _read(self):
        try:
            magic,ch,rate=struct.unpack('<4sii',self._exact(12))
            if magic not in (b'DS5P',b'DS5T') or (ch,rate)!=(self.channels,CAPTURE_RATE): raise ValueError(_ui_tr('잘못된 게임 캡처 형식'))
            self.protocol=magic
            self.ready.set()
            while not self.closed:
                if magic==b'DS5T':
                    size,captured,stamp,position,flags=struct.unpack('<iddQI',self._exact(32))
                else:
                    size,stamp=struct.unpack('<id',self._exact(12));captured=None;position=None;flags=0
                if size<0 or size>48000*self.channels*2 or size%(self.channels*2): raise ValueError(_ui_tr('잘못된 캡처 패킷'))
                data=self._exact(size)
                received=time.perf_counter()
                if not math.isfinite(stamp) or stamp<=0 or stamp>received+1:raise ValueError(_ui_tr('잘못된 캡처 시각'))
                if captured is not None and (not math.isfinite(captured) or flags&4 or captured>stamp+.005 or stamp-captured>10):
                    captured=None;self.timestamp_errors+=1
                if flags&1:self.discontinuities+=1
                with self.condition:
                    if self.closed:break
                    if size:self._packet_frames=size//(self.channels*2)
                    if stamp<self.discard_before:
                        self.prefill_discarded_frames+=size//(self.channels*2);continue
                    if len(self.queue)==self.queue.maxlen: self.drops+=1
                    self.queue.append((stamp,data,captured,position,flags,received))
                    self.condition.notify_all()
        except Exception as exc:
            if not self.closed: self.error=str(exc)
        finally:
            self.ready.set()
            with self.condition:self.condition.notify_all()
    def _buffer_state(self):
        # Keep compatibility with older stream adapters and manually supplied buffers.
        if not hasattr(self,'condition'):self.condition=threading.Condition(self.lock)
        if not hasattr(self,'pending_segments'):self.pending_segments=deque()
        if not hasattr(self,'_clock'):
            self._clock=CaptureClock();self._clock_events=None
            self.rate_corrected_frames=0;self.rate_corrected_blocks=0
        if self.pending and not self.pending_segments:
            self.pending_segments.append([len(self.pending),None,self.pending_time,None,0,self.pending_time])
    def _available_locked(self,frames=CAPTURE_READ_FRAMES):
        if self.error or getattr(self,'closed',False) or self.child.poll() is not None:
            self.pending.clear();self.pending_segments.clear()
            raise RuntimeError(_ui_tr('지정 프로세스 캡처 중단: ')+(self.error or _ui_tr('종료'))+' / '+' '.join(self.messages))
        now=time.perf_counter()
        while self.pending_segments and now-self.pending_segments[0][2]>MAX_TRANSPORT_AGE:
            old=self.pending_segments.popleft();del self.pending[:old[0]];self.stale+=1
        # Preserve each packet's time/position, including boundaries inside a read.
        while len(self.pending)<frames*self.channels*2 and self.queue:
            packet=self.queue.popleft();stamp,data=packet[:2]
            if now-stamp>MAX_TRANSPORT_AGE:
                self.stale+=1;continue
            if not data:continue
            captured,position,flags,received=packet[2:] if len(packet)>2 else (None,None,0,stamp)
            self.pending.extend(data)
            self.pending_segments.append([len(data),captured,stamp,position,flags,received])
        self.pending_time=self.pending_segments[0][2] if self.pending_segments else 0.
        return len(self.pending)//(2*self.channels)
    def get_read_available(self):
        self._buffer_state()
        with self.condition:return self._available_locked()
    def _take_locked(self,n):
        count=n*self.channels*2
        first=self.pending_segments[0]
        self.last_read_timing=(first[1],first[2],first[5],first[3])
        data=bytes(self.pending[:count]);del self.pending[:count]
        remaining=count
        while remaining:
            segment=self.pending_segments[0];taken=min(remaining,segment[0]);frames=taken//(self.channels*2)
            segment[0]-=taken;remaining-=taken
            if segment[1] is not None:segment[1]+=frames/CAPTURE_RATE
            if segment[3] is not None:segment[3]+=frames
            if not segment[0]:self.pending_segments.popleft()
        self.pending_time=self.pending_segments[0][2] if self.pending_segments else 0.
        return data
    def read(self,n,**kwargs):
        self._buffer_state()
        with self.condition:
            if self._available_locked(n)<n:raise RuntimeError(_ui_tr('게임 캡처 버퍼 부족'))
            data=self._take_clocked_locked(n)
            if data is None:raise RuntimeError(_ui_tr('게임 캡처 버퍼 부족'))
            return data
    def _take_clocked_locked(self,n):
        events=(self.stale,getattr(self,'drops',0),getattr(self,'discontinuities',0))
        if self._clock_events!=events:
            self._clock.reset();self._clock_events=events
        buffered=(len(self.pending)+sum(len(p[1]) for p in self.queue))//(self.channels*2)
        plan=self._clock.plan(n,buffered,getattr(self,'_packet_frames',CAPTURE_READ_FRAMES))
        if plan is None:return self._take_locked(n)
        consumed,needed,_,_=plan
        # Only use available lookahead; never wait for another packet to correct drift.
        if self._available_locked(needed)<needed:
            self._clock.reset()
            return self._take_locked(n) if len(self.pending)>=n*self.channels*2 else None
        if events!=(self.stale,getattr(self,'drops',0),getattr(self,'discontinuities',0)):
            self._clock.reset();return self._take_locked(n)
        data=bytes(self.pending[:needed*self.channels*2])
        phase=self._clock.phase
        output=self._clock.render(data,self.channels,plan)
        self._take_locked(consumed)
        if self.last_read_timing[0] is not None:
            captured,*rest=self.last_read_timing
            self.last_read_timing=(captured+phase/CAPTURE_RATE,*rest)
        self.rate_corrected_frames+=consumed-n;self.rate_corrected_blocks+=1
        return output
    def read_wait(self,n,stop_event):
        self._buffer_state()
        with self.condition:
            while True:
                if stop_event.is_set():raise KeyboardInterrupt()
                if self._available_locked(n)>=n:
                    data=self._take_clocked_locked(n)
                    if data is not None:return data
                # Data/EOF/close notify immediately; timeout only backs up cancellation.
                self.condition.wait(.1)
    def wake_waiters(self):
        with self.condition:self.condition.notify_all()
    def discard_backlog(self):
        """Drop pre-open audio once when the output becomes ready, not during playback."""
        with self.condition:
            self.discard_before=time.perf_counter()
            self.prefill_discarded_frames+=len(self.pending)//(self.channels*2)
            self.prefill_discarded_frames+=sum(len(packet[1])//(self.channels*2) for packet in self.queue)
            self.pending.clear();self.pending_segments.clear();self.queue.clear()
            self.pending_time=0.;self.last_read_timing=None
            if hasattr(self,'_clock'):self._clock.reset()
            self.condition.notify_all()
    def buffer_snapshot(self):
        with self.condition:
            frames=(len(self.pending)+sum(len(packet[1]) for packet in self.queue))//(self.channels*2)
            return dict(buffer_ms=frames/CAPTURE_RATE*1000,prefill_discarded_frames=self.prefill_discarded_frames,
                        timestamp_errors=self.timestamp_errors,discontinuities=self.discontinuities,
                        rate_corrected_frames=getattr(self,'rate_corrected_frames',0),
                        rate_corrected_blocks=getattr(self,'rate_corrected_blocks',0),
                        capture_timestamp_supported=self.protocol==b'DS5T')
    def get_input_latency(self): return 0.0 # Not measured; process-mode status marks unknown.
    def stop_stream(self): self.close()
    def close(self):
        if self.closed: return
        self.closed=True
        self.wake_waiters()
        try:
            self.child.stdin.close()
            self.child.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            self.child.terminate()
            try:self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.child.kill();self.child.wait(timeout=2)
        finally:
            for reader in (self.reader,self.err_reader):
                if reader.is_alive():reader.join(timeout=1)
            self.child.stdout.close(); self.child.stderr.close()
        with self.condition:
            self.pending.clear();self.pending_segments.clear();self.queue.clear();self.condition.notify_all()
