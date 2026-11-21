"""Join HT-GRU-Lab-Lite human-confirmed events with DS5Light offline features."""

import argparse
from bisect import bisect_left
from decimal import Decimal
import json
from pathlib import Path

from core import RATE
from offline import feature_record, process_array, read_wav


def read_annotations(path, source_id, duration):
    session = None
    intervals = []
    with path.open(encoding='utf-8-sig') as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line, parse_float=Decimal)
            if not isinstance(row, dict):
                raise ValueError(f'Annotation line {line_number} must be an object.')
            if row.get('status') != 'confirmed':
                continue
            identity = tuple(row.get(key) for key in ('source_id', 'game_id', 'session_id'))
            if (any(not isinstance(value, str) or not value.strip() for value in identity)
                    or identity[0] != source_id or (session is not None and session != identity)):
                raise ValueError(f'Annotation line {line_number} does not match one WAV and one game/session.')
            label = row.get('label')
            present = row.get('present', True)
            start, end = row.get('start_s'), row.get('end_s')
            if (row.get('origin') not in ('human_review', 'human_export')
                    or not isinstance(label, str) or not label.strip()
                    or label.strip() == 'transient_unclassified'
                    or type(present) is not bool
                    or type(start) not in (int, Decimal) or type(end) not in (int, Decimal)
                    or not Decimal(start).is_finite() or not Decimal(end).is_finite()
                    or not 0 <= start < end or start >= duration
                    or end > duration + Decimal('0.0005')):
                raise ValueError(f'Invalid human-confirmed annotation at line {line_number}.')
            session = identity
            intervals.append((start * RATE, end * RATE, label.strip(), present))
    if not intervals:
        raise ValueError('No human-confirmed annotations found.')
    return session, intervals


def write_aligned(wav_path, annotations_path, output_path):
    if output_path.exists():
        raise FileExistsError(output_path)
    rate, audio = read_wav(wav_path)
    session, intervals = read_annotations(annotations_path, wav_path.stem, Decimal(len(audio)) / rate)
    frames = []
    process_array(audio, rate, feature_frames=frames)
    sample_indices = [index for index, _ in frames]
    labels = [set() for _ in frames]
    negatives = [set() for _ in frames]
    unmatched = 0
    for start, end, label, present in intervals:
        left = bisect_left(sample_indices, start)
        right = bisect_left(sample_indices, end, lo=left)
        if left == right:
            unmatched += 1
        for index in range(left, right):
            active, opposite = (labels[index], negatives[index]) if present else (negatives[index], labels[index])
            if label in opposite:
                raise ValueError(f'Conflicting positive and negative annotations at sequence {index}.')
            active.add(label)
    labeled = sum(bool(active or absent) for active, absent in zip(labels, negatives))
    if not labeled:
        raise ValueError('No confirmed interval contains a feature frame; check WAV and annotation timing.')

    with output_path.open('x', encoding='utf-8') as handle:
        for sequence, ((sample_index, values), active) in enumerate(zip(frames, labels)):
            row = dict(source_id=session[0], game_id=session[1], session_id=session[2],
                       labels=sorted(active) if active else None,
                       frame=feature_record(sequence, sample_index, values))
            if negatives[sequence]:
                row['negative_labels'] = sorted(negatives[sequence])
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
    return dict(frames=len(frames), labeled_frames=labeled, unmatched_intervals=unmatched)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav', type=Path)
    parser.add_argument('annotations', type=Path, help='HT-GRU-Lab-Lite *_confirmed.jsonl')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        report = write_aligned(args.wav, args.annotations, args.output)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
