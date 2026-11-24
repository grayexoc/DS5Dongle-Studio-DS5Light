"""Manually rehearse a short four-channel Studio PCM fixture on a verified rear-DSP route."""

import argparse
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import time

import numpy as np

from audio import InstanceLock, devices
from device_binding import DeviceBinding
from device_diagnostics import decode_status, decode_usb_playback, tagged_command
from studio_fields import FIELDS
from studio_rehearsal_format import REHEARSAL_MAX_FRAMES, REHEARSAL_PEAK, read_rehearsal_wav
from studio_settings_protocol import SettingsClient
from studio_slots import devices as studio_devices, profile_matches_revision
from windows_device_identity import usb_parent_id


ROUTE_FIELDS = ('auto_haptics_enable', 'ah_dsp_source', 'auto_mute_replace')


def prepare_stereo_fixture(pcm, rate, controls, *, live_pcm_scale=False):
    from offline import limit_rehearsal, normalize_wav, process_array, rehearsal_window

    if pcm.ndim != 2 or pcm.shape[1] != 2:
        raise ValueError('Studio DSP analysis requires a stereo WAV.')
    window = normalize_wav(rehearsal_window(pcm, rate))
    converted, _ = process_array(window, rate, controls, studio_pcm16=True,
                                 stereo_control=True, shape_control=True, live_pcm_scale=live_pcm_scale)
    converted = limit_rehearsal(converted)
    if controls.gain != 1.0:
        from output_gain import OutputGain

        adjusted = OutputGain().process(converted.tobytes(), controls.gain, rear_peak=REHEARSAL_PEAK)
        converted = np.frombuffer(adjusted, '<i2').reshape(-1, 4)
    return converted


def read_fixture(path, *, stereo_controls=None):
    rate, pcm = read_rehearsal_wav(path, stereo_start=0 if stereo_controls is not None else None)
    if stereo_controls is not None and pcm.ndim == 2 and pcm.shape[1] == 2:
        pcm = prepare_stereo_fixture(pcm, rate, stereo_controls)
        rate = 48000
    if (rate != 48000 or pcm.dtype != np.dtype('<i2') or pcm.ndim != 2
            or pcm.shape[1] != 4 or not 0 < len(pcm) <= REHEARSAL_MAX_FRAMES):
        raise ValueError('Use a 48 kHz, four-channel PCM16 WAV of at most 1.5 seconds.')
    if np.max(np.abs(pcm.astype(np.int32))) > REHEARSAL_PEAK or np.any(pcm[:, 2:] < 0):
        raise ValueError('Limit all channels to 15% PCM peak and use nonnegative rear controls.')
    return np.array(pcm) if isinstance(pcm, np.memmap) else pcm


def verify_route(client, *, idle, shared_rear_control=False):
    before = client.profile(include_revision=True)
    status = decode_status(tagged_command(client, 0x1e, 0))
    if status.get('usb_mode') == 'XInput':
        raise RuntimeError('Studio Rear control is unavailable in Xbox mode.')
    values, missing = client.read_fields([FIELDS[key] for key in ROUTE_FIELDS])
    after = client.profile(include_revision=True)
    if before != after or not after.get('config_token'):
        raise RuntimeError('Cannot verify a stable active Studio profile revision.')
    if (not status['connected'] or not status['ready'] or status['auto_haptics'] != 2
            or missing or tuple(values.get(key) for key in ROUTE_FIELDS) != (2, 1, 1)):
        raise RuntimeError('The rehearsal requires Replace, rear DSP, and Replace speaker auto-mute.')
    if idle and (status['audio_processing'] or status['audio_stream']):
        raise RuntimeError('Studio is already processing audio. Stop the other sender first.')
    if (shared_rear_control and status.get('usb_playback_diagnostics')
            and 'rear_link_epoch' in playback_snapshot(client)):
        raise RuntimeError('This Studio firmware requires --exclusive for rear control.')
    return after


def verified_endpoint(binding, rows):
    identity = binding.snapshot()
    endpoint = binding.output(rows)
    if endpoint and endpoint.get('endpoint_id') and endpoint.get('maxOutputChannels') == 4:
        parent = endpoint.get('usb_parent_id') or usb_parent_id(endpoint['endpoint_id'], endpoint=True)
        same_parent = identity.usb_parent_id and identity.usb_parent_id == parent
        same_container = identity.container_id and identity.container_id == endpoint.get('container_id')
        if same_parent or (same_container and not (identity.usb_parent_id and parent)):
            return endpoint
    raise RuntimeError('Cannot positively identify a four-channel endpoint on the selected Studio device.')


def observed_usb_transition(before, after, *, active):
    event, other = ('opens', 'closes') if active else ('closes', 'opens')
    return (
        before['active'] != active and after['known'] and after['active'] == active
        and (after['generation'] - before['generation']) & 0xffffffff == 1
        and (after[event] - before[event]) & 0xffffffff == 1
        and after[other] == before[other]
        and after['invalidations'] == before['invalidations']
        and after['config_revision'] == before['config_revision']
    )


def playback_snapshot(client):
    return decode_usb_playback(tagged_command(client, 0x1e, 3))


@contextmanager
def leased_studio_renderer(client, open_exclusive):
    """Prepare the verified exclusive renderer, which must open with silence."""
    profile = verify_route(client, idle=True)

    before = playback_snapshot(client)
    if not profile_matches_revision(profile, before.get('config_revision')):
        raise RuntimeError('Studio profile changed before reserving exclusive output.')
    attempt, pending_until = client.rear_lease_exchange(1, before)
    with open_exclusive() as renderer:
        opened = playback_snapshot(client)
        if (not observed_usb_transition(before, opened, active=True)
                or opened.get('rear_link_epoch') != before['rear_link_epoch']
                or verify_route(client, idle=False) != profile
                or time.monotonic() >= pending_until):
            raise RuntimeError('Exclusive Studio session changed before lease commit.')
        _, valid_until = client.rear_lease_exchange(2, opened, attempt=attempt)
        yield renderer, opened, attempt, valid_until


def write_leased_fixture(path, client, open_exclusive, *, stereo_controls=None):
    """Write a bounded fixture from a synchronous worker using an exclusive PCM sink."""
    pcm = read_fixture(path, stereo_controls=stereo_controls)
    with leased_studio_renderer(client, open_exclusive) as (renderer, opened, attempt, deadline):
        sequence = 0

        def ensure_lease():
            nonlocal sequence, deadline
            client.check_cancel()
            now = time.monotonic()
            if now >= deadline:
                raise RuntimeError('Rear-control lease expired before PCM submission completed.')
            if deadline - now <= 0.5:
                sequence += 1
                _, deadline = client.rear_lease_exchange(3, opened, attempt=attempt, sequence=sequence)

        for start in range(0, len(pcm), 4800):
            ensure_lease()
            renderer.write(pcm[start:start + 4800].tobytes())
        ensure_lease()
        renderer.drain()
        if time.monotonic() >= deadline:
            raise RuntimeError('Rear-control lease expired before the renderer finished.')
    return opened


def play_exclusive_on_endpoint(path, client, endpoint_id, *, stereo_controls=None):
    from studio_exclusive import prepare_exclusive_renderer

    client.check_cancel()
    with prepare_exclusive_renderer(endpoint_id) as open_exclusive:
        opened = write_leased_fixture(path, client, open_exclusive, stereo_controls=stereo_controls)
    confirm_exclusive_close(client, opened)


def confirm_exclusive_close(client, opened):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        closed = playback_snapshot(client)
        if (observed_usb_transition(opened, closed, active=False)
                and closed.get('rear_link_epoch') == opened['rear_link_epoch']
                and closed.get('local_discard_complete')):
            return
        time.sleep(.05)
    raise RuntimeError('Studio USB close and local queue discard could not be confirmed.')


def play(path, *, observe_boundary=False, exclusive=False):
    import hid
    import pyaudiowpatch as pa

    pcm = read_fixture(path)
    with ExitStack() as cleanup:
        cleanup.callback(InstanceLock().close)
        rows = studio_devices()
        if len(rows) != 1:
            raise RuntimeError('Connect exactly one Studio HID device for the rehearsal.')
        binding = DeviceBinding()
        binding.bind_hid(rows[0])
        device = hid.device()
        cleanup.callback(device.close)
        device.open_path(rows[0]['path'])
        client = SettingsClient(device)
        audio = pa.PyAudio()
        cleanup.callback(audio.terminate)
        endpoint = verified_endpoint(binding, devices(audio))
        if exclusive:
            play_exclusive_on_endpoint(path, client, endpoint['endpoint_id'])
            print(f'Submitted {len(pcm)} frames in exclusive mode to {endpoint["name"]}.')
            return
        profile = verify_route(client, idle=True, shared_rear_control=bool(pcm[:, 2:].any()))
        index = endpoint['index']
        if not audio.is_format_supported(48000, output_device=index, output_channels=4, output_format=pa.paInt16):
            raise RuntimeError('Studio endpoint rejected 48 kHz four-channel PCM16.')
        if verify_route(client, idle=True) != profile:
            raise RuntimeError('Studio profile changed before playback.')

        before = playback_snapshot(client) if observe_boundary else None
        during = None
        stream = audio.open(rate=48000, channels=4, format=pa.paInt16, output=True,
                            output_device_index=index, frames_per_buffer=480)
        try:
            deadline = time.monotonic() + 4
            # HID readback is synchronous. Check at bounded intervals rather than per audio buffer.
            for start in range(0, len(pcm), 12000):
                if verify_route(client, idle=False) != profile:
                    raise RuntimeError('Studio route changed during rehearsal.')
                if time.monotonic() >= deadline:
                    raise RuntimeError('Studio rehearsal timed out.')
                stream.write(pcm[start:start+12000].tobytes(), exception_on_underflow=False)
                if before is not None and during is None:
                    during = playback_snapshot(client)
            stream.stop_stream()
        finally:
            stream.close()
        print(f'Submitted {len(pcm)} frames to {endpoint["name"]}.')
        if before is not None:
            until = time.monotonic() + 2
            while True:
                after = playback_snapshot(client)
                closed = (observed_usb_transition(before, during, active=True)
                          and observed_usb_transition(during, after, active=False))
                discarded = after.get('local_discard_complete')
                if (closed and discarded is not False) or time.monotonic() >= until:
                    return dict(before=before, during=during, after=after, observed_close=closed,
                                observed_local_discard=bool(closed and discarded))
                time.sleep(.05)


def packaged_exclusive_main(argv):
    parser = argparse.ArgumentParser(prog='DS5Light --studio-exclusive-replay')
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    with args.report.open('x', encoding='utf-8') as report:
        try:
            play(args.fixture, exclusive=True)
            result = {'submitted': True}
        except (OSError, ValueError, RuntimeError) as exc:
            result = {'submitted': False, 'error': str(exc)}
        json.dump(result, report, ensure_ascii=False)
        report.write('\n')
    return 0 if result['submitted'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    parser.add_argument('--observe-boundary', action='store_true', help='read USB playback events from diagnostic firmware')
    parser.add_argument('--exclusive', action='store_true', help='use the opt-in Studio rear-control lease')
    args = parser.parse_args()
    if args.exclusive and args.observe_boundary:
        parser.error('--observe-boundary is for the shared rehearsal path')
    try:
        result = play(args.fixture, observe_boundary=args.observe_boundary, exclusive=args.exclusive)
        if result is not None:
            print(json.dumps(result))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
