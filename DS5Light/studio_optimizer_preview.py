"""Read-only DSP Only route candidates based on observed Studio values."""
from device_diagnostics import decode_status, tagged_command
from studio_fields import FIELDS
from studio_rehearsal_format import measure_rehearsal_output as _measure_rehearsal_output
from studio_replay import ROUTE_FIELDS, playback_snapshot
from studio_settings_protocol import PartialApplyError, validate_changes
from studio_slots import profile_matches_revision

STUDIO_DSP_FIELDS = ('auto_haptics_gain', 'auto_haptics_lowpass_hz', 'auto_haptics_slope',
                     'auto_haptics_smooth', 'auto_haptics_gate', 'ah_xover_hz',
                     'ah_low_gain', 'ah_high_gain')
LIVE_ROUTE = dict(zip(ROUTE_FIELDS, (2, 1, 1)))


def read_route_preview(client, *, live_output, endpoint_verified):
    before = client.profile(include_revision=True)
    status = decode_status(tagged_command(client, 0x1e, 0))
    playback = {}
    if live_output and endpoint_verified and status.get('usb_playback_diagnostics'):
        playback = playback_snapshot(client)
    fields = (*ROUTE_FIELDS, 'mix_native_level')
    values, _ = client.read_fields([FIELDS[key] for key in (*fields, *STUDIO_DSP_FIELDS, 'haptics_gain')])
    after = client.profile(include_revision=True)

    if (before != after or not after.get('config_token') or not status['ready']
            or not all(key in values for key in fields)
            or status['auto_haptics'] != values['auto_haptics_enable']
            or values['auto_haptics_enable'] not in (0, 1, 2)
            or values['ah_dsp_source'] not in (0, 1) or values['auto_mute_replace'] not in (0, 1)
            or not 0 <= values['mix_native_level'] <= 100):
        return dict(reason='현재 Studio 설정과 프로필 리비전을 다시 확인하세요.', changes={})

    observed = {key: values[key] for key in ROUTE_FIELDS}
    context = dict(observed=observed, revision=after['config_token'])
    if all(key in values for key in STUDIO_DSP_FIELDS):
        baseline = {key: values[key] for key in STUDIO_DSP_FIELDS}
        try:
            validate_changes({}, baseline)
        except ValueError:
            pass
        else:
            context['studio_dsp_baseline'] = baseline
            if 'haptics_gain' in values:
                try:
                    validate_changes({}, {'haptics_gain': values['haptics_gain']})
                except ValueError:
                    pass
                else:
                    context['studio_output_gain'] = values['haptics_gain']
    native_mix = values['auto_haptics_enable'] == 1 and values['mix_native_level'] > 0
    reasons = {}
    if live_output:
        if native_mix:
            return dict(reason='실시간 독점 출력은 현재 Native Mix 설정과 충돌합니다.', changes={}, **context)
        if not endpoint_verified or 'rear_link_epoch' not in playback or status.get('usb_mode') != 'DualSense':
            return dict(reason='Studio 독점 출력의 장치 식별 또는 펌웨어 지원을 확인하세요.', changes={}, **context)
        if not profile_matches_revision(after, playback.get('config_revision')):
            return dict(reason='USB 진단과 Studio 설정의 리비전이 다릅니다. 다시 조회하세요.', changes={})
        context['live_route_verified'] = True
        reasons = {
            'auto_haptics_enable': 'PC 후면 제어 스트림에는 Replace 모드가 필요합니다.',
            'ah_dsp_source': 'PC 제어값은 후면 CH2–3으로 전달됩니다.',
            'auto_mute_replace': 'Studio 독점 출력은 Replace의 스피커 자동 음소거를 요구합니다.',
        }
        changes = {key: (values[key], value) for key, value in LIVE_ROUTE.items() if values[key] != value}
        reason = ('Studio 실시간 독점 출력에 필요한 설정 후보입니다.' if changes
                  else 'Studio 독점 출력의 설정 조건이 충족됐습니다. 독점권은 시작할 때 확인합니다.')
    elif native_mix and values['ah_dsp_source'] == 1:
        changes = {'ah_dsp_source': (1, 0)}
        reason = 'Native Mix의 후면 채널을 유지하려면 DSP 입력을 전면으로 선택하세요.'
        reasons = {'ah_dsp_source': reason}
    else:
        changes = {}
        reason = '확인된 설정에서 변경할 경로 후보가 없습니다.'
    validate_changes(values, {key: candidate for key, (_, candidate) in changes.items()})
    return dict(reason=reason, changes=changes,
                field_reasons={key: reasons[key] for key in changes}, **context)


def _studio_headroom(preview, signal, *, live=False):
    baseline = preview.get('studio_dsp_baseline')
    output_gain = preview.get('studio_output_gain')
    if (not baseline or output_gain is None
            or not preview.get('live_route_verified') or not preview.get('revision') or preview['changes']
            or any(preview.get('observed', {}).get(key) != value for key, value in LIVE_ROUTE.items())
            or signal.get('dsp_controls', {}).get('bypass')):
        return None

    measured = signal.get('live_pcm' if live else 'current')
    pc_candidate = signal.get('pc_gain_candidate')
    trial = pc_candidate.get('live_pcm') if live and pc_candidate else pc_candidate
    if measured is None or (pc_candidate and trial is None):
        return None
    peak = measured['rear_peak']
    trial_peak = trial['rear_peak'] if trial else peak
    band_factor = 1.0
    basis = 'cold_start_single_band_pre_soft_clip'
    if baseline['ah_xover_hz']:
        if (not measured.get('rear_nonnegative')
                or (trial and not trial.get('rear_nonnegative'))
                or 'ah_low_gain' not in baseline or 'ah_high_gain' not in baseline):
            return None
        # With nonnegative input both low passes stay within [0, peak], so their difference is bounded by peak.
        band_factor = (baseline['ah_low_gain'] + baseline['ah_high_gain']) / 100
        basis = 'cold_start_split_band_pre_soft_clip'
    gain_scale = 9.0 * output_gain * band_factor / 32768
    current = baseline['auto_haptics_gain']
    intensity_scale = (current / 200) ** 1.5
    trial_scale = trial_peak * gain_scale
    return dict(observed=current, rear_peak=peak, trial_rear_peak=trial_peak,
                pc_gain=pc_candidate['gain'] if pc_candidate else None,
                current_upper_bound=peak * gain_scale * intensity_scale,
                trial_upper_bound=trial_scale * intensity_scale,
                basis=basis, band_factor=band_factor), trial_scale


def compare_studio_headroom(preview, signal):
    """Report both cold-start bounds at the observed Studio intensity."""
    rehearsal = _studio_headroom(preview, signal)
    live = _studio_headroom(preview, signal, live=True)
    if rehearsal is None or live is None:
        return None
    return dict(rehearsal=rehearsal[0], simulated_live=live[0], criterion=1.0)


def preview_studio_intensity(preview, signal):
    """Calculate a setting candidate from bounded rehearsal PCM."""
    from math import floor

    estimate = _studio_headroom(preview, signal)
    if estimate is None:
        return None
    headroom, scale = estimate
    if headroom['current_upper_bound'] <= 1.0:
        return None
    current = headroom['observed']
    candidate = current
    proposed_bound = headroom.pop('trial_upper_bound')
    if proposed_bound > 1.0:
        candidate = min(current - 1, floor(200 * (1.0 / scale) ** (2 / 3)))
        proposed_bound = scale * (candidate / 200) ** 1.5
        if proposed_bound > 1.0:
            candidate -= 1
            proposed_bound = scale * (candidate / 200) ** 1.5
    return dict(field='auto_haptics_gain', proposed=candidate, proposed_upper_bound=proposed_bound, **headroom)


def describe_haptics_profile(controls, engine_controls, *, live_output, preview):
    """Describe current PC intent and the last verified Studio readback."""
    from dataclasses import asdict

    preview = preview or {}
    observed = preview.get('observed') if preview.get('revision') else None
    desired = dict(LIVE_ROUTE) if live_output else None
    if desired is None and observed is not None and preview.get('changes'):
        desired = {field: proposed for field, (_, proposed) in preview['changes'].items()}
    state = 'unverified'
    if observed is not None:
        if desired is None:
            state = 'observed'
        elif not live_output or preview.get('live_route_verified'):
            state = ('matches_readback' if all(observed.get(field) == value for field, value in desired.items())
                     else 'differs_from_readback')
    return dict(
        pc=dict(desired_controls=asdict(controls),
                engine_requested_controls=asdict(engine_controls) if engine_controls is not None else None),
        studio=dict(managed_live_requested=live_output, desired_route=desired,
                    observed_route=observed, route_status=state,
                    dsp_readback=preview.get('studio_dsp_baseline') if observed is not None else None),
    )


def analyze_rehearsal_signal(path, controls, *, start=0.0):
    """Compare the encoded PCM window with a bypass reference, without output."""
    rate, pcm = _load_rehearsal_window(path, start)
    return _analyze_rehearsal_window(pcm, rate, controls, start)


def _load_rehearsal_window(path, start):
    import numpy as np
    from offline import rehearsal_window
    from studio_rehearsal_format import read_rehearsal_wav

    rate, pcm = read_rehearsal_wav(path, stereo_start=start)
    if pcm.ndim != 2 or pcm.shape[1] != 2:
        raise ValueError('Studio DSP analysis requires a stereo WAV.')
    return rate, np.array(rehearsal_window(pcm, rate))


def _measure_live_pcm(pcm, rate, controls):
    from studio_replay import prepare_stereo_fixture

    return _measure_rehearsal_output(prepare_stereo_fixture(pcm, rate, controls, live_pcm_scale=True))


def _analyze_rehearsal_window(pcm, rate, controls, start):
    from dataclasses import asdict, replace
    import numpy as np
    from offline import normalize_wav
    from studio_rehearsal_format import REHEARSAL_PEAK
    from studio_replay import prepare_stereo_fixture

    window = normalize_wav(pcm)
    source = dict(sample_rate=rate, first_frame=int(start * rate), frames=len(window),
                  peak_lr=np.max(np.abs(window), axis=0).tolist(),
                  rms_lr=np.sqrt(np.mean(np.square(window, dtype=np.float64), axis=0)).tolist())

    output = prepare_stereo_fixture(pcm, rate, controls)
    current = _measure_rehearsal_output(output)
    bypass = _measure_rehearsal_output(prepare_stereo_fixture(pcm, rate, replace(controls, bypass=True)))
    candidate = None
    if not controls.bypass and controls.gain > 1.0 and current['rear_ceiling_frames']:
        unity = _measure_rehearsal_output(prepare_stereo_fixture(pcm, rate, replace(controls, gain=1.0)))

        def improves(measured):
            return (measured['rear_ceiling_frames'] < current['rear_ceiling_frames']
                    and all(trial_rms > 0 or current_rms == 0
                            for current_rms, trial_rms in zip(current['rear_rms_lr'], measured['rear_rms_lr'])))

        if improves(unity):
            candidate = dict(gain=1.0, **unity)
            if not unity['rear_ceiling_frames']:
                gain = ((REHEARSAL_PEAK - 1) * 100 // unity['rear_peak']) / 100
                if 1.0 < gain < controls.gain:
                    measured = _measure_rehearsal_output(prepare_stereo_fixture(pcm, rate, replace(controls, gain=gain)))
                    if not measured['rear_ceiling_frames'] and improves(measured):
                        candidate = dict(gain=gain, **measured)
    if candidate:
        candidate['live_pcm'] = _measure_live_pcm(pcm, rate, replace(controls, gain=candidate['gain']))
    return dict(frames=len(output), sample_rate=48000, rear_ceiling=REHEARSAL_PEAK,
                source=source, dsp_controls=asdict(controls), current=current, bypass=bypass,
                live_pcm=_measure_live_pcm(pcm, rate, controls), pc_gain_candidate=candidate)


def _peak_across_windows(measurements):
    return dict(rear_peak=max(measured['rear_peak'] for measured in measurements),
                rear_nonnegative=all(measured.get('rear_nonnegative') for measured in measurements),
                rear_ceiling_frames=sum(measured['rear_ceiling_frames'] for measured in measurements))


def analyze_rehearsal_windows(path, controls, starts):
    """Require a shared gain to pass all selected file windows."""
    from dataclasses import replace
    from studio_replay import prepare_stereo_fixture

    if not 1 <= len(starts) <= 3 or len(set(starts)) != len(starts):
        raise ValueError('Choose one to three different WAV start times.')
    inputs = [_load_rehearsal_window(path, start) for start in starts]
    windows = [_analyze_rehearsal_window(pcm, rate, controls, start)
               for start, (rate, pcm) in zip(starts, inputs)]
    if len(windows) == 1:
        return windows[0]
    report = dict(frames=sum(window['frames'] for window in windows), sample_rate=windows[0]['sample_rate'],
                  rear_ceiling=windows[0]['rear_ceiling'], dsp_controls=windows[0]['dsp_controls'],
                  windows=windows, pc_gain_candidate=None)
    for label in ('current', 'bypass', 'live_pcm'):
        report[label] = _peak_across_windows([window[label] for window in windows])
    gains = [window['pc_gain_candidate']['gain'] for window in windows if window['pc_gain_candidate']]
    if gains:
        gain = min(gains)
        trial_controls = replace(controls, gain=gain)
        trials = [_measure_rehearsal_output(prepare_stereo_fixture(pcm, rate, trial_controls))
                  for rate, pcm in inputs]
        rejected = []
        for window, trial in zip(windows, trials):
            before = window['current']
            if trial['rear_ceiling_frames'] > before['rear_ceiling_frames'] or any(
                    active > 0 and measured == 0
                    for active, measured in zip(before['rear_rms_lr'], trial['rear_rms_lr'])):
                rejected.append(window['source']['first_frame'])
        ceiling_frames = sum(trial['rear_ceiling_frames'] for trial in trials)
        trial_result = dict(gain=gain, rear_ceiling_frames=ceiling_frames,
                            rear_peak=max(trial['rear_peak'] for trial in trials),
                            rear_nonnegative=all(trial.get('rear_nonnegative') for trial in trials), windows=trials)
        if not rejected and ceiling_frames < report['current']['rear_ceiling_frames']:
            live_trials = [_measure_live_pcm(pcm, rate, trial_controls) for rate, pcm in inputs]
            trial_result['live_pcm'] = _peak_across_windows(live_trials)
            trial_result['live_pcm_windows'] = live_trials
            report['pc_gain_candidate'] = trial_result
        else:
            report['rejected_pc_gain_trial'] = dict(trial_result, failing_first_frames=rejected)
    return report

def applied_pc_gain_signal(signal, before, after):
    """Reuse the exact PCM measurements made at the accepted PC gain."""
    from dataclasses import asdict, replace

    trial = signal.get('pc_gain_candidate')
    if (not trial or signal.get('dsp_controls') != asdict(before)
            or after != replace(before, gain=trial['gain'])):
        return None
    controls = asdict(after)
    updated = dict(signal, dsp_controls=controls, pc_gain_candidate=None,
                   current={key: trial[key] for key in signal['current']})
    if 'live_pcm' in signal:
        updated['live_pcm'] = trial['live_pcm']
    if 'windows' in signal:
        updated['windows'] = [
            dict(window, dsp_controls=controls, current=measured, live_pcm=live, pc_gain_candidate=None)
            for window, measured, live in zip(signal['windows'], trial['windows'], trial['live_pcm_windows'],
                                              strict=True)
        ]
    return updated


def apply_route_preview(client, preview):
    observed = preview['observed']
    changes = preview['changes']
    if (not changes or any(key not in ROUTE_FIELDS or observed.get(key) != previous
                           for key, (previous, _) in changes.items())):
        raise ValueError('Refresh the Studio route candidate before applying.')
    target = dict(observed, **{key: candidate for key, (_, candidate) in changes.items()})
    token = apply_route(client, 1, preview['revision'], observed, target)
    return dict(revision=token, before=dict(observed), applied=target)


def rollback_route_apply(client, applied):
    return apply_route(client, 2, applied['revision'], applied['applied'], applied['before'])


def apply_route(client, operation, revision, observed, target):
    if set(observed) != set(ROUTE_FIELDS) or set(target) != set(ROUTE_FIELDS) or observed == target:
        raise ValueError('Refresh the Studio route candidate before writing.')
    capabilities = playback_snapshot(client)
    if (not capabilities.get('conditional_route_apply')
            or not profile_matches_revision({'config_token': revision}, capabilities.get('config_revision'))):
        raise ValueError('Studio revision or conditional route-write capability could not be verified.')
    token = client.conditional_studio_route_write(
        operation, revision, tuple(observed[key] for key in ROUTE_FIELDS),
        tuple(target[key] for key in ROUTE_FIELDS))
    try:
        return _verify_write_readback(client, token, target)
    except PartialApplyError as exc:
        # Only a correlated acknowledgement can authorize a conditional restore.
        exc.route_revision = token
        raise


def apply_intensity_preview(client, preview, signal, controls):
    from dataclasses import asdict

    if signal.get('dsp_controls') != asdict(controls) or signal.get('pc_gain_candidate'):
        raise ValueError('Reanalyze the WAV with the PC controls selected for Studio playback.')
    proposal = preview_studio_intensity(preview, signal)
    if not proposal or proposal['proposed'] >= proposal['observed']:
        raise ValueError('No verified Studio intensity decrease is available.')
    before, target = proposal['observed'], proposal['proposed']
    token = _apply_intensity(client, 1, preview['revision'], before, target)
    return dict(revision=token, before=before, applied=target)


def rollback_intensity_apply(client, receipt):
    return _apply_intensity(client, 2, receipt['revision'], receipt['applied'], receipt['before'])


def _apply_intensity(client, operation, revision, observed, target):
    playback = playback_snapshot(client)
    if (not playback.get('conditional_intensity_apply') or not playback.get('known')
            or playback.get('active') or not playback.get('local_discard_complete')
            or not profile_matches_revision({'config_token': revision}, playback.get('config_revision'))):
        raise ValueError('Studio intensity write requires the verified idle profile.')
    if not _settings_match(client, revision, dict(LIVE_ROUTE, auto_haptics_gain=observed)):
        raise ValueError('Studio intensity or route changed. Refresh the preview.')
    token = client.conditional_studio_intensity_write(operation, revision, observed, target)
    return _verify_write_readback(client, token, dict(LIVE_ROUTE, auto_haptics_gain=target))


def _settings_match(client, token, target):
    before = client.profile(include_revision=True)
    current, missing = client.read_fields([FIELDS[key] for key in target])
    after = client.profile(include_revision=True)
    return before == after and after.get('config_token') == token and not missing and current == target


def _verify_write_readback(client, token, target):
    try:
        verified = _settings_match(client, token, target)
    except (RuntimeError, OSError, ValueError, TimeoutError) as exc:
        raise PartialApplyError('Studio acknowledged the write but readback failed. Refresh the profile.') from exc
    if not verified:
        raise PartialApplyError('Studio settings changed or readback did not match. Refresh the profile.')
    return token
