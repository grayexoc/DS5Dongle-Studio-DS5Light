"""Compare aligned WAV features with the production PC Rear block processor."""
import argparse
from bisect import bisect_left
from decimal import Decimal
from hashlib import sha256
from itertools import zip_longest
import json
from pathlib import Path

import numpy as np
import scipy
from scipy.io import wavfile

from core import BLOCK, RATE, Controls, Processor
from haptic_control import HapticControlDsp
from offline import FEATURE_SCHEMA_ID, feature_record
from studio_live_output import live_rear_blocks
from training_alignment import read_annotations


def compare(wav, annotations, aligned, live_jsonl):
    rate, stereo = wavfile.read(wav)
    if rate != RATE or stereo.dtype != np.int16 or stereo.ndim != 2 or stereo.shape[1] != 2:
        raise ValueError('Parity fixture must be 48 kHz stereo PCM16.')
    session, intervals = read_annotations(annotations, wav.stem, Decimal(len(stereo)) / RATE)
    dsp = HapticControlDsp(Processor(), stereo=True, shape=True)
    controls = Controls()
    features = np.empty((4, 4), dtype=np.float32)

    def live_frames():
        cursor = 0
        for start in range(0, len(stereo), BLOCK * 4):
            front = stereo[start:start + BLOCK * 4]
            packet = np.zeros((len(front), 4), dtype='<i2')
            packet[:, :2] = front
            for cursor, _ in live_rear_blocks(packet.tobytes(), dsp, controls, cursor,
                                              stereo_capture=True, feature_buffer=features):
                yield cursor - 1, features

    selected = []
    count = 0
    with aligned.open(encoding='utf-8-sig') as expected_file, live_jsonl.open('x', encoding='utf-8') as recorded:
        for index, pair in enumerate(zip_longest(expected_file, live_frames())):
            line, live = pair
            if line is None or live is None:
                raise ValueError(f'Frame count differs at sequence {index}.')
            row = json.loads(line)
            if tuple(row[key] for key in ('source_id', 'game_id', 'session_id')) != session:
                raise ValueError('Aligned dataset refers to a different source or session.')
            sample, values = live
            frame = feature_record(index, sample, values)
            expected = row['frame']
            if any(expected[key] != frame[key] for key in ('sequence', 'sample_index', 'feature_schema_id')):
                raise ValueError(f'Frame index or schema differs at sequence {index}.')
            if expected['features'] != frame['features']:
                raise ValueError(f'Float32 feature values differ at sequence {index}.')
            recorded.write(json.dumps(frame, allow_nan=False) + '\n')
            count += 1
            if index % 2 == 1:
                selected.append(sample)
    if not count:
        raise ValueError('No frames compared.')
    unmatched = 0
    for start, end, _, _ in intervals:
        index = bisect_left(selected, start)
        unmatched += index == len(selected) or selected[index] >= end
    if unmatched:
        raise ValueError(f'{unmatched} confirmed intervals have no 10 ms frame.')
    sources = ('core.py', 'haptic_control.py', 'offline.py', 'studio_live_output.py',
               'training_alignment.py', 'training_parity.py')
    source_dir = Path(__file__).parent
    return {
        'status': 'passed', 'feature_schema_id': FEATURE_SCHEMA_ID,
        'route': 'PC Rear DSP PCM16 replay', 'sample_rate_hz': RATE,
        'frames_5ms': count, 'frames_10ms': len(selected),
        'selection_rule': 'zero-based odd sequence starting at 1',
        'confirmed_intervals': len(intervals), 'unmatched_10ms_intervals': unmatched,
        'source_sha256': {name: sha256((source_dir / name).read_bytes()).hexdigest() for name in sources},
        'wav_sha256': sha256(wav.read_bytes()).hexdigest(),
        'aligned_sha256': sha256(aligned.read_bytes()).hexdigest(),
        'live_sha256': sha256(live_jsonl.read_bytes()).hexdigest(),
        'numpy': np.__version__, 'scipy': scipy.__version__,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('wav', 'annotations', 'aligned', 'live_jsonl', 'report'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        parser.error('Report already exists.')
    report = compare(args.wav, args.annotations, args.aligned, args.live_jsonl)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
