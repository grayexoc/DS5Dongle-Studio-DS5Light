"""Opt-in, bounded device diagnostics. No background polling or saved settings.

Inspired by https://luoshengjin.netlify.app/ (reuse permission supplied by user).
Studio commands and Windows device binding remain specific to this project.
"""
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import math
import secrets
import statistics
import struct
import time

from studio_settings_protocol import SettingsClient
from studio_slots import _DEVICE_LOCK

CONTROL_BYTES = ('flags0', 'flags1', 'right_rumble', 'left_rumble',
                 'mute_power', 'motor_reduction', 'flags2', 'haptic_filter')
COUNTERS = ('sent', 'overflow', 'expired', 'retry_expired', 'retry_exhausted',
            'send_error', 'max_age_ms', 'recoveries', 'retries')
TESTS = {'rumble_left': 1, 'rumble_right': 2, 'rumble_both': 3,
         'trigger_left': 4, 'trigger_right': 5,
         'haptic_left': 6, 'haptic_right': 6, 'speaker': 6}
TEST_AUDIO_FRAMES = 72000  # 1.5 s PCM leaves room for the 2 s device lease and STOP.


def tagged_command(client, command, value):
    tag = secrets.token_bytes(4)
    reply = client.command(command, bytes([value]) + tag, report=0x84,
                           echo=bytes([1, value]) + tag, echo_offset=3, attempts=6)
    if len(reply) != 63 or reply[2] != 0:
        raise ValueError('시험 요청이 거부됐거나 응답 형식이 맞지 않습니다. 신호는 확인되지 않았습니다. 상태 새로 고침으로 연결·프로필·오디오 사용 여부를 확인하세요.')
    return reply


class DiagnosticsUnsupported(ValueError):
    pass


def probe_support(device, cancel=lambda: False):
    client = SettingsClient(device, cancel=cancel)
    tag = secrets.token_bytes(4)
    reply = client.command(0x1e, bytes([0])+tag, report=0x84,
                           echo=bytes([1,0])+tag, echo_offset=3, attempts=6)
    if len(reply)==63 and reply[2]==1:
        raise DiagnosticsUnsupported('현재 펌웨어는 장치 진단을 지원하지 않습니다.')
    return decode_status(reply)


def decode_status(reply):
    if len(reply) != 63 or reply[:5] != b'\x66\x1e\x00\x01\x00':
        raise ValueError('Invalid diagnostic status')
    flags = reply[9]
    def control(offset):
        values = dict(zip(CONTROL_BYTES, reply[offset:offset + 8]))
        values.update(mode='rumble' if values['flags0'] & 2 or values['flags2'] & 4 else 'native PCM',
                      haptic_mute=bool(values['mute_power'] & 0x80),
                      haptic_power_save=bool(values['mute_power'] & 4))
        return values
    return dict(connected=bool(flags & 1), ready=bool(flags & 2),
                audio_processing=bool(flags & 4), audio_stream=bool(flags & 8),
                usb_mode='XInput' if reply[10] else 'DualSense',
                auto_haptics=reply[11], channels=reply[12],
                front_peak=struct.unpack_from('<H', reply, 13)[0],
                rear_peak=struct.unpack_from('<H', reply, 15)[0],
                rssi=struct.unpack_from('b', reply, 17)[0] if flags & 16 else None,
                last_host=control(19) if reply[18] & 1 else None,
                current=control(27), last_accepted=control(35) if reply[18] & 2 else None,
                uptime_ms=struct.unpack_from('<I', reply, 43)[0])


def decode_transport(reply):
    if len(reply) != 63 or reply[:5] != b'\x66\x1e\x00\x01\x01':
        raise ValueError('Invalid diagnostic counters')
    return dict(zip(COUNTERS, struct.unpack_from('<9I', reply, 9)),
                queue_depth=struct.unpack_from('<H', reply, 45)[0])


class ReportTiming:
    """Host HID read timing, NOT Bluetooth loss or end-to-end latency."""
    def __init__(self):
        self.deltas = deque(maxlen=8192)
        self.previous = None
        self.count = 0
        self.last_report = b''

    def mark(self, raw, now):
        if len(raw) < 11 or raw[0] != 1:return
        if self.previous is not None:self.deltas.append((now - self.previous) * 1000)
        self.previous = now
        self.count += 1
        self.last_report = bytes(raw)

    def snapshot(self):
        values = sorted(self.deltas)
        mean = statistics.fmean(values) if values else None
        return dict(reports=self.count, intervals=len(values),
                    hz=1000 / mean if mean and mean > 0 else None,
                    mean_ms=mean, jitter_ms=statistics.pstdev(values) if values else None,
                    p99_ms=values[max(0, math.ceil(len(values) * .99) - 1)] if values else None,
                    max_ms=values[-1] if values else None, last_report_hex=self.last_report.hex(),
                    intervals_ms=list(self.deltas),
                    meaning='PC HID read intervals; not RF packet loss or motor latency')


def collect_snapshot(device, identity, audio_stats=None, cancel=lambda: False):
    client = SettingsClient(device, cancel=cancel)
    report = dict(schema='ds5light-device-diagnostics-v1',
                  captured_utc=datetime.now(timezone.utc).isoformat(),
                  device=asdict(identity), audio=audio_stats,
                  limits=['BT sent means L2CAP accepted, not controller/motor receipt.',
                          'Pages are separate observations. Peaks are the latest PCM block.',
                          'Counters are cumulative modulo 2^32; no counters are reset.'])
    try:
        report['firmware'] = client.metadata(5).hex()
        report['profile'] = client.profile()
        report['status'] = decode_status(tagged_command(client, 0x1e, 0))
        report['transport'] = decode_transport(tagged_command(client, 0x1e, 1))
        report['speaker_settings'] = speaker_settings(client)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        report['diagnostic_error'] = str(exc)
    return report


def speaker_settings(client):
    from studio_fields import FIELDS
    return {key: client.read_one(FIELDS[key]) for key in
            ('disable_speaker', 'speaker_volume', 'speaker_gain')}


def speaker_block_reason(values):
    if values['disable_speaker']:
        return '듀얼센스 스피커 끄기가 켜져 있습니다. Studio 설정에서 해제한 뒤 시험하세요.'
    if not values['speaker_volume']:
        return '듀얼센스 스피커 음량이 0입니다. Studio 설정에서 음량을 조정한 뒤 시험하세요.'
    return None


def measure_reports(device, cancel, seconds=5):
    meter = ReportTiming()
    device.set_nonblocking(1)
    # Drop pre-existing host-buffered reports; bound draining even on a busy pad.
    for _ in range(256):
        if cancel.is_set() or not device.read(64):break
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not cancel.is_set():
        raw = device.read(64)
        if raw:meter.mark(raw, time.perf_counter())
        else:cancel.wait(.001)
    result=meter.snapshot()
    result['cancelled']=cancel.is_set()
    return result


def tone_block(kind, offset, frames=240, rate=48000):
    """Conservative 12% peak, four discrete channels, 10 ms start/end ramps."""
    if kind not in ('haptic_left', 'haptic_right', 'speaker'):raise ValueError('Invalid audio test')
    import numpy as np
    positions = np.arange(offset, offset + frames)
    envelope = np.clip(np.minimum(positions, TEST_AUDIO_FRAMES - 1 - positions) / (rate * .01), 0, 1)
    frequency = 440 if kind == 'speaker' else 80
    wave = np.rint(np.sin(positions * (2 * np.pi * frequency / rate)) * envelope * (.12 * 32767)).astype('<i2')
    pcm = np.zeros((frames, 4), dtype='<i2')
    if kind == 'speaker':pcm[:, :2] = wave[:, None]
    else:pcm[:, 2 if kind == 'haptic_left' else 3] = wave
    return pcm.tobytes()


def audio_test(kind, row, cancel, binding, identity, begin=None):
    import pyaudiowpatch as pa
    from audio import devices
    if cancel.is_set():return
    p = pa.PyAudio()
    stream = None
    try:
        # Keep device indices within the same PortAudio enumeration and lifetime.
        current = binding.output(devices(p))
        if binding.snapshot() != identity or not current or current.get('endpoint_id') != row.get('endpoint_id'):
            raise RuntimeError('시험 출력 장치가 변경되었습니다. 다시 조회하세요.')
        if cancel.is_set():return
        p.is_format_supported(48000, output_device=current['index'], output_channels=4, output_format=pa.paInt16)
        stream = p.open(rate=48000, channels=4, format=pa.paInt16, output=True,
                        output_device_index=current['index'], frames_per_buffer=240, start=False)
        if cancel.is_set():return
        deadline = begin() if begin is not None else time.monotonic() + 2
        stream.start_stream()
        for offset in range(0, TEST_AUDIO_FRAMES, 240):
            if cancel.is_set() or binding.snapshot() != identity:break
            if time.monotonic() >= deadline:
                raise TimeoutError('오디오 시험 제한시간 초과 · 장치를 다시 확인하세요.')
            stream.write(tone_block(kind, offset), exception_on_underflow=False)
    finally:
        try:
            if stream is not None:
                try:stream.stop_stream()
                finally:stream.close()
        finally:p.terminate()


def run_output_test(device, kind, cancel, binding, identity, row=None):
    if kind not in TESTS:raise ValueError('Invalid output test')
    client = SettingsClient(device)  # STOP must still run after user cancellation.
    status = decode_status(tagged_command(client, 0x1e, 0))
    if not status['ready']:
        raise RuntimeError('시험 시작 안 됨 · 듀얼센스 연결 준비가 완료되지 않았습니다.')
    if status['auto_haptics'] != 0:
        raise RuntimeError('시험 시작 안 됨 · 오디오햅틱 OFF인 Native 프로필을 선택하세요.')
    if status['audio_processing']:
        raise RuntimeError('시험 시작 안 됨 · 게임·다른 앱의 Pico 오디오 출력 또는 마이크 사용을 중지하세요.')
    if kind.startswith('haptic_') or kind == 'speaker':
        if row is None or not row.get('endpoint_id'):raise RuntimeError('시험 시작 안 됨 · Pico의 4채널 오디오 출력 연결을 확인하지 못했습니다. 오디오 출력 연결 버튼에서 장치를 선택하세요.')
    settings = speaker_settings(client) if kind == 'speaker' else None
    reason = speaker_block_reason(settings) if settings is not None else None
    if reason:
        return dict(test=kind, completed=False, speaker_settings=settings, blocked_reason=reason)
    started = False
    def begin():
        nonlocal started
        deadline = time.monotonic() + 2
        tagged_command(client, 0x1f, TESTS[kind])
        started = True
        return deadline
    try:
        if cancel.is_set():return
        if row is not None and (kind.startswith('haptic_') or kind == 'speaker'):
            audio_test(kind, row, cancel, binding, identity, begin)
        else:
            begin()
            cancel.wait(2)
    finally:
        # A timed-out start may have executed. Always attempt STOP, never repeat START.
        tagged_command(client, 0x1f, 0)
    result = dict(test=kind, completed=started and not cancel.is_set(),
                  note='Submission only; confirm physical output separately.')
    if settings is not None:result['speaker_settings'] = settings
    if kind.startswith('trigger_'):
        from studio_records import build_effect
        result['trigger_effect_hex'] = bytes(build_effect('resistance', 2, 9, 29)).hex(' ')
    return result


def with_selected_device(binding, identity, operation, cancel):
    import hid
    # Reuse the existing transaction lock; do not steal a replacement device.
    while not _DEVICE_LOCK.acquire(timeout=.1):
        if cancel.is_set():raise RuntimeError('진단 취소됨')
    try:
        if cancel.is_set() or binding.snapshot() != identity or not identity.hid_path:
            raise RuntimeError('선택 장치가 변경되었거나 진단이 취소되었습니다.')
        device = hid.device()
        try:
            device.open_path(identity.hid_path)
            return operation(device)
        finally:device.close()
    finally:_DEVICE_LOCK.release()
