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
RUMBLE_TEST_MODES = (('classic', 64), ('classic', 128), ('improved', 64), ('improved', 128))


def audio_recovery_candidates(identity, outputs, inventory):
    from windows_device_identity import usb_parent_id

    def match_device(endpoint):
        endpoint_id = endpoint.get('id') or endpoint.get('endpoint_id')
        parent = endpoint.get('usb_parent_id')
        if not parent and identity.usb_parent_id and endpoint_id:
            parent = usb_parent_id(endpoint_id, endpoint=True)
        if parent and identity.usb_parent_id:
            return parent == identity.usb_parent_id
        container = endpoint.get('container_id')
        if container and identity.container_id:
            return (container == identity.container_id or
                    (endpoint_id == identity.endpoint_id and container == identity.confirmed_container_id))
        return True if endpoint_id and endpoint_id == identity.endpoint_id else None

    endpoints = {row['id']: row for row in inventory['endpoints']}
    candidates = {}
    for row in outputs:
        endpoint = endpoints.get(row['endpoint_id'], {})
        channels = endpoint.get('mix_channels') or row.get('maxOutputChannels', 0)
        if endpoint.get('state', 1) == 1 and channels >= 4:
            match = match_device({**row, **endpoint})
            if match is not False:
                candidates[row['endpoint_id']] = (row, match)
    active = [row for row, match in candidates.values() if match is True]
    if len(active) == 1:
        return 'matched', active
    if active:
        return 'choose', active
    known = [row for row in endpoints.values() if match_device(row) is True]
    if any(row['state'] == 1 and 0 < row.get('mix_channels', 0) < 4 for row in known):
        return 'channels', []
    if known and not any(row['state'] == 1 for row in known):
        return ('disabled' if any(row['state'] == 2 for row in known) else 'missing'), []
    if candidates:
        return 'choose', [row for row, _ in candidates.values()]
    if not inventory['complete']:
        return 'unavailable', []
    return ('no_output' if known else 'missing'), []
SPEAKER_COUNTERS = ('pcm_dropped', 'encode_failed', 'underrun', 'stale')
RUMBLE_TEST_OFFSETS = (0, 6, 9, 12)
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


def decode_status(reply, firmware=b''):
    if len(reply) != 63 or reply[:5] != b'\x66\x1e\x00\x01\x00':
        raise ValueError('Invalid diagnostic status')
    flags = reply[9]
    def control(offset):
        values = dict(zip(CONTROL_BYTES, reply[offset:offset + 8]))
        values.update(mode='rumble' if values['flags0'] & 2 or values['flags2'] & 4 else 'native PCM',
                      haptic_mute=bool(values['mute_power'] & 0x80),
                      haptic_power_save=bool(values['mute_power'] & 4))
        return values
    status = dict(connected=bool(flags & 1), ready=bool(flags & 2),
                audio_processing=bool(flags & 4), audio_stream=bool(flags & 8),
                usb_mode='XInput' if reply[10] else 'DualSense',
                auto_haptics=reply[11], channels=reply[12], rumble_comparison=reply[56] == 1,
                front_peak=struct.unpack_from('<H', reply, 13)[0],
                rear_peak=struct.unpack_from('<H', reply, 15)[0],
                rssi=struct.unpack_from('b', reply, 17)[0] if flags & 16 else None,
                last_host=control(19) if reply[18] & 1 else None,
                current=control(27), last_accepted=control(35) if reply[18] & 2 else None,
                uptime_ms=struct.unpack_from('<I', reply, 43)[0])
    # v36 acknowledged selectors 7..15, but its state handler dropped them.
    if firmware[3:].split(b'\0', 1)[0] in (b'36', b'v36'):
        status['rumble_comparison'] = False
    if reply[47] == 1:
        left, right, blocks = struct.unpack_from('<HHI', reply, 48)
        status.update(rear_left_peak=left, rear_right_peak=right, usb_audio_blocks=blocks)
    if reply[57] == 1:
        status['speaker_diagnostics'] = True
        status['output_route'] = {1: 'speaker', 2: 'headset'}.get(reply[58])
    return status


def decode_speaker_counters(reply):
    if len(reply) != 63 or reply[:5] != b'\x66\x1e\x00\x01\x02':
        raise ValueError('Invalid speaker counters')
    return dict(zip(SPEAKER_COUNTERS, struct.unpack_from('<4I', reply, 9)))


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
                          'Counters are cumulative modulo 2^32; no counters are reset.',
                          'Speaker underruns may include startup/silence fallback; they are not measured RF loss.'])
    try:
        firmware = client.metadata(5)
        report['firmware'] = firmware.hex()
        report['profile'] = client.profile()
        report['status'] = decode_status(tagged_command(client, 0x1e, 0), firmware)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        report['diagnostic_error'] = str(exc)
        return report

    status = report['status']
    route = status.get('output_route')
    pages = {
        'transport': lambda: decode_transport(tagged_command(client, 0x1e, 1)),
        'speaker_settings': lambda: speaker_settings(client, route),
    }
    if status.get('speaker_diagnostics'):
        pages['speaker_counters'] = lambda: decode_speaker_counters(tagged_command(client, 0x1e, 2))
    for key, read in pages.items():
        if cancel():
            return report
        try:
            report[key] = read()
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            report.setdefault('page_errors', {})[key] = str(exc)

    return report


def finish_speaker_measurement(device, report, max_elapsed_ms, cancel):
    client = SettingsClient(device, cancel=cancel)
    before = report['speaker_counters']
    status = report['status']
    final = decode_status(tagged_command(client, 0x1e, 0))
    after = decode_speaker_counters(tagged_command(client, 0x1e, 2))
    elapsed_ms = (final['uptime_ms'] - status['uptime_ms']) & 0xffffffff
    if (not final['ready'] or final.get('output_route') != status.get('output_route')
            or final['auto_haptics'] != status['auto_haptics'] or elapsed_ms > max_elapsed_ms):
        raise RuntimeError('오디오 경로가 변경됐습니다. 다시 검사하세요.')
    report['speaker_delta'] = {key: (after[key] - before[key]) & 0xffffffff for key in before}
    report['speaker_interval_ms'] = elapsed_ms
    report['speaker_counters'] = after


def speaker_settings(client, route=None):
    from studio_fields import FIELDS
    keys = ['disable_speaker']
    if route in ('speaker', None):
        keys.extend(('speaker_volume', 'speaker_gain'))
    if route == 'headset':
        keys.append('headset_volume')
    values = {key: client.read_one(FIELDS[key]) for key in keys}
    if route is None and not values['speaker_volume'] and not values['disable_speaker']:
        values['headset_volume'] = client.read_one(FIELDS['headset_volume'])
    return values


def speaker_block_reason(values, route=None):
    if values['disable_speaker']:
        return '듀얼센스 스피커 끄기가 켜져 있습니다. Studio 설정에서 해제한 뒤 시험하세요.'
    if route == 'speaker' and not values['speaker_volume']:
        return '듀얼센스 스피커 음량이 0입니다. Studio 설정에서 음량을 조정한 뒤 시험하세요.'
    if route == 'headset' and not values['headset_volume']:
        return '듀얼센스 헤드셋 음량이 0입니다. Studio 설정에서 음량을 조정한 뒤 시험하세요.'
    if route is None and not (values.get('speaker_volume') or values.get('headset_volume')):
        return '스피커와 헤드셋 음량이 모두 0입니다. Studio 설정에서 음량을 조정한 뒤 시험하세요.'
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
    pcm = np.zeros((frames, 4), dtype='<i2')
    def tone(channel, start, length, frequency):
        local = positions - start
        envelope = np.clip(np.minimum(local, length - 1 - local) / (rate * .01), 0, 1)
        pcm[:, channel] += np.rint(np.sin(local * (2 * np.pi * frequency / rate))
                                    * envelope * (.12 * 32767)).astype('<i2')
    if kind == 'speaker':
        for channel, starts in enumerate(((.04, .24), (.70, .90, 1.10))):
            for start in starts:
                tone(channel, round(rate * start), round(rate * .12), 440)
    else:
        tone(2 if kind == 'haptic_left' else 3, 0, TEST_AUDIO_FRAMES, 80)
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


def run_output_test(device, kind, cancel, binding, identity, row=None, rumble_mode=0):
    if kind not in TESTS or not 0 <= rumble_mode < len(RUMBLE_TEST_MODES):
        raise ValueError('Invalid output test')
    is_rumble = kind.startswith('rumble_')
    selector = TESTS[kind] + (RUMBLE_TEST_OFFSETS[rumble_mode] if is_rumble else 0)
    client = SettingsClient(device)  # STOP must still run after user cancellation.
    reply = tagged_command(client, 0x1e, 0)
    status = decode_status(reply)
    if is_rumble and rumble_mode:
        if not status['rumble_comparison'] or not decode_status(reply, client.metadata(5))['rumble_comparison']:
            raise RuntimeError('현재 펌웨어는 일반 진동 세기·모드 비교를 지원하지 않습니다.')
    if not status['ready']:
        raise RuntimeError('시험 시작 안 됨 · 듀얼센스 연결 준비가 완료되지 않았습니다.')
    if status['auto_haptics'] != 0:
        raise RuntimeError('시험 시작 안 됨 · 오디오햅틱 OFF인 Native 프로필을 선택하세요.')
    if status['audio_processing']:
        raise RuntimeError('시험 시작 안 됨 · 게임·다른 앱의 Pico 오디오 출력 또는 마이크 사용을 중지하세요.')
    if kind.startswith('haptic_') or kind == 'speaker':
        if row is None or not row.get('endpoint_id'):raise RuntimeError('시험 시작 안 됨 · Pico의 4채널 오디오 출력 연결을 확인하지 못했습니다. 오디오 출력 연결 버튼에서 장치를 선택하세요.')
    route = status.get('output_route')
    settings = speaker_settings(client, route) if kind == 'speaker' else None
    reason = speaker_block_reason(settings, route) if settings is not None else None
    if reason:
        return dict(test=kind, completed=False, speaker_settings=settings, blocked_reason=reason)
    started = False
    def begin():
        nonlocal started
        deadline = time.monotonic() + 2
        tagged_command(client, 0x1f, selector)
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
    if is_rumble:
        result['rumble_mode'], result['rumble_strength'] = RUMBLE_TEST_MODES[rumble_mode]
    if settings is not None:result.update(speaker_settings=settings, output_route=route)
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
