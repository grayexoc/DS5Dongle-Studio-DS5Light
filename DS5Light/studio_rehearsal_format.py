"""Bounds shared by Studio rehearsal file generation and playback."""
import math

REHEARSAL_MAX_FRAMES = 72000
REHEARSAL_PEAK = 4915
LIVE_PCM_SCALE = REHEARSAL_PEAK / 32768


def rehearsal_bounds(frames, rate, start, output_rate=48000):
    if not math.isfinite(start) or not 0 <= start < frames / rate:
        raise ValueError('시험 시작 초는 WAV 재생 범위 안에 있어야 합니다.')
    first = int(start * rate)
    length = (REHEARSAL_MAX_FRAMES * rate + output_rate - 1) // output_rate
    return first, length


def measure_rehearsal_output(output):
    import numpy as np

    magnitude = np.abs(output.astype(np.int32))
    peak = np.max(magnitude, axis=0)
    rear = magnitude[:, 2:]
    return dict(front_peak=int(max(peak[:2])), rear_peak=int(max(peak[2:])),
                rear_nonnegative=bool(np.all(output[:, 2:] >= 0)),
                rear_frames=int(np.count_nonzero(np.any(rear, axis=1))),
                rear_rms_lr=np.sqrt(np.mean(np.square(rear, dtype=np.float64), axis=0)).tolist(),
                rear_ceiling_frames=int(np.count_nonzero(np.any(rear >= REHEARSAL_PEAK, axis=1))))


def read_rehearsal_wav(path, *, stereo_start=None):
    from scipy.io import wavfile

    try:
        rate, pcm = wavfile.read(path, mmap=True)
    except ValueError as exc:
        if 'mmap=True not compatible' not in str(exc):
            raise
        if stereo_start is not None:
            packed = read_packed_stereo_window(path, stereo_start)
            if packed is not None:
                return packed
        # shortcut: use the existing decoder for packed formats not handled by wave.
        rate, pcm = wavfile.read(path)

    if stereo_start is not None and pcm.ndim == 2 and pcm.shape[1] == 2:
        first, length = rehearsal_bounds(len(pcm), rate, stereo_start)
        return rate, pcm[first:first + length]
    return rate, pcm


def read_packed_stereo_window(path, start):
    import wave
    import numpy as np

    try:
        wav = wave.open(str(path), 'rb')
    except (wave.Error, EOFError):
        return None
    with wav:
        if wav.getnchannels() != 2 or wav.getsampwidth() != 3:
            return None
        rate = wav.getframerate()
        first, length = rehearsal_bounds(wav.getnframes(), rate, start)
        wav.setpos(first)
        triplets = np.frombuffer(wav.readframes(length), np.uint8).reshape(-1, 3)
    pcm = np.zeros((len(triplets), 4), np.uint8)
    pcm[:, 1:] = triplets
    return rate, pcm.view('<i4').reshape(-1, 2)
