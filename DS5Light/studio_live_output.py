"""Explicit managed Studio output for the app's live capture loop."""
from contextlib import contextmanager
from queue import Empty, Full, Queue
from threading import Event, Thread
import time

import numpy as np

from core import BLOCK, RATE, Processor
from adaptive_gain import AdaptiveRearLevel
from device_diagnostics import with_selected_device
from haptic_control import HapticControlDsp, encode_studio_pcm
from output_gain import OutputGain
from studio_exclusive import prepare_exclusive_renderer
from studio_rehearsal_format import LIVE_PCM_SCALE, REHEARSAL_PEAK
from studio_optimizer_preview import apply_route_preview, read_route_preview, rollback_route_apply
from studio_replay import confirm_exclusive_close, leased_studio_renderer
from studio_settings_protocol import PartialApplyError, SettingsClient
from thread_start import start_thread


class StudioLiveOutput:
    def __init__(self, binding, identity, endpoint, stop_event, *, adaptive_gain=False):
        self._parent_stop = stop_event
        self._stop = Event()
        self._ready = Event()
        self._queue = Queue(maxsize=12)
        self._error = None
        self.route_status = ''
        self.restore_status = ''
        self.restore_detail = ''
        self._opened = None
        self.level = OutputGain()
        self.adaptive = AdaptiveRearLevel() if adaptive_gain else None
        self.queued_frames = self.submitted_frames = self.renewals = 0
        self._thread = Thread(target=self._run, args=(binding, identity, endpoint), daemon=True,
                              name='DS5Light-Studio-output')
        start_thread(self._thread)

    def wait_ready(self):
        expires = time.monotonic() + 14
        while not self._ready.wait(.05):
            if self._parent_stop.is_set() or time.monotonic() >= expires:
                self.close()
                if self._parent_stop.is_set():
                    raise KeyboardInterrupt()
                raise RuntimeError('Studio exclusive output preparation timed out.')
        if self._parent_stop.is_set():
            self.close()
            raise KeyboardInterrupt()
        if self._error:
            self.close()
            raise RuntimeError(f'Studio exclusive output: {self._error}')

    def check(self):
        if self._error or self._stop.is_set() or not self._thread.is_alive():
            raise RuntimeError(f'Studio exclusive output ended: {self._error or "closed"}')

    def write(self, data, controls, *, stereo_capture=False):
        self.check()
        try:
            self._queue.put_nowait((data, controls, stereo_capture))
            self.queued_frames += len(data) // 8
        except Full as exc:
            self._stop.set()
            raise RuntimeError('Studio exclusive output queue filled; playback stopped.') from exc

    def stats(self):
        policy = self.adaptive.policy if self.adaptive is not None else None
        return dict(queued_frames=self.queued_frames, submitted_frames=self.submitted_frames,
                    renewals=self.renewals, adaptive_gain=self.adaptive is not None,
                    route_status=self.route_status, restore_status=self.restore_status,
                    restore_detail=self.restore_detail,
                    adaptive_gain_target_percent=policy.target if policy is not None else None)

    def get_output_latency(self):
        return None

    def request_stop(self):
        self._stop.set()

    def is_closed(self):
        return not self._thread.is_alive()

    def wait_closed(self, timeout):
        self._thread.join(timeout=timeout)
        return self.is_closed()

    def close(self):
        self.request_stop()
        return self.wait_closed(2)

    def _run(self, binding, identity, endpoint):
        def render(device):
            changed = lambda: binding.snapshot() != identity
            client = SettingsClient(device, cancel=lambda: self._stop.is_set() or changed())
            cleanup = SettingsClient(device, cancel=changed)
            with self._managed_route(client, cleanup):
                self._render(client, endpoint)

        try:
            with_selected_device(binding, identity, render, self._stop)
        except Exception as exc:
            if self._error is None and not self._stop.is_set():
                self._error = exc
        finally:
            self._stop.set()
            self._ready.set()

    @contextmanager
    def _managed_route(self, client, cleanup):
        preview = read_route_preview(client, live_output=True, endpoint_verified=True)
        self.route_status = preview['reason']
        if not preview.get('live_route_verified'):
            raise RuntimeError(self.route_status)
        observed = preview['observed']
        if (observed['auto_haptics_enable'], observed['ah_dsp_source']) != (2, 1):
            raise RuntimeError('Studio 출력 경로가 변경되었습니다. 다시 시작하세요.')
        receipt = None
        try:
            if preview['changes']:
                try:
                    client.check_cancel()
                    # Finish reading the acknowledgement even if Stop arrives during the write.
                    receipt = apply_route_preview(cleanup, preview)
                except PartialApplyError as exc:
                    token = getattr(exc, 'route_revision', None)
                    if token:
                        before = preview['observed']
                        applied = dict(before, **{key: target for key, (_, target) in preview['changes'].items()})
                        receipt = dict(revision=token, before=before, applied=applied)
                    else:
                        self.restore_status = 'Studio 경로 복구 미확인'
                    raise
                self.route_status = 'Studio 임시 경로 적용 확인'
            yield
        finally:
            if receipt:
                try:
                    opened = self._opened
                    if opened is not None:
                        confirm_exclusive_close(cleanup, opened)
                    rollback_route_apply(cleanup, receipt)
                except (RuntimeError, ValueError, OSError) as exc:
                    self.restore_status = 'Studio 경로 복구 미확인'
                    self.restore_detail = str(exc)
                else:
                    self.restore_status = 'Studio 경로 복구 확인'

    def _render(self, client, endpoint):
        dsp = HapticControlDsp(Processor(), stereo=True, shape=True)
        sample_index = 0
        renewal = None
        try:
            with prepare_exclusive_renderer(endpoint, live=True, cancel=self._stop.is_set) as open_exclusive:
                with leased_studio_renderer(client, open_exclusive) as (renderer, opened, attempt, deadline):
                    self._opened = opened
                    def renew():
                        nonlocal deadline
                        sequence = 0
                        try:
                            while not self._stop.wait(max(0, deadline - time.monotonic() - .5)):
                                if time.monotonic() >= deadline:
                                    raise RuntimeError('Studio live output authorization expired.')
                                sequence += 1
                                _, deadline = client.rear_lease_exchange(3, opened, attempt=attempt, sequence=sequence)
                                self.renewals += 1
                        except Exception as exc:
                            if not self._stop.is_set():
                                self._error = exc
                                self._stop.set()

                    renewal = Thread(target=renew, daemon=True, name='DS5Light-Studio-renew')
                    start_thread(renewal)
                    self._ready.set()
                    last_input = time.monotonic()
                    try:
                        while not self._stop.is_set():
                            pcm = bytearray()
                            # Wait for up to 20 ms of input. Drain queued input up to the
                            # original batch limit to catch up after a slow renderer write.
                            collect_until = time.monotonic() + .020
                            while len(pcm) < 1920 * 8 and not self._stop.is_set():
                                try:
                                    data, controls, stereo_capture = self._queue.get(
                                        timeout=0 if len(pcm) >= 960 * 8 else
                                        max(0, collect_until - time.monotonic()))
                                except Empty:
                                    break
                                last_input = time.monotonic()
                                stereo = np.frombuffer(data, '<i2').reshape(-1, 4)[:, :2].astype(np.float32) / 32768
                                for start in range(0, len(stereo), BLOCK):
                                    block = stereo[start:start + BLOCK]
                                    _, rear = dsp.process(block, controls, now=sample_index / RATE,
                                                          allow_direction=stereo_capture, rear_only=True)
                                    sample_index += len(block)
                                    encoded = encode_studio_pcm(block * LIVE_PCM_SCALE, rear * LIVE_PCM_SCALE).tobytes()
                                    if self.adaptive is not None:
                                        encoded = self.adaptive.process(encoded, controls, self.level, REHEARSAL_PEAK)
                                    elif controls.gain != 1.0 or self.level.current != 1.0:
                                        encoded = self.level.process(encoded, controls.gain, rear_peak=REHEARSAL_PEAK)
                                    pcm.extend(encoded)

                            client.check_cancel()
                            now = time.monotonic()
                            if now >= deadline or now - last_input >= 1:
                                raise RuntimeError('Studio live output lost its lease or input.')
                            if pcm:
                                renderer.write(pcm)
                                self.submitted_frames += len(pcm) // 8
                            elif self.adaptive is not None:
                                self.adaptive.interrupt()
                    except Exception as exc:
                        if not self._stop.is_set():
                            self._error = exc
                        raise
                    finally:
                        self._stop.set()
        finally:
            if renewal is not None:
                renewal.join()
