import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile

from training_alignment import write_aligned
from training_evaluation import FRAME_KEYS


class TrainingAlignmentTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.wav = root / 'capture.wav'
        self.annotations = root / 'capture_confirmed.jsonl'
        self.output = root / 'aligned.jsonl'
        wavfile.write(self.wav, 48000, np.zeros(960, dtype=np.int16))

    def annotation(self, **values):
        row = dict(source_id='capture', game_id='game', session_id='session',
                   start_s=0.004, end_s=0.010, label='impact',
                   status='confirmed', origin='human_review', raw_model_label='candidate')
        return row | values

    def write_annotations(self, *rows):
        self.annotations.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')

    def test_confirmed_intervals_use_frame_end_and_keep_unreviewed_frames(self):
        self.write_annotations(self.annotation(),
                               self.annotation(start_s=0.006, end_s=0.012, label='texture'),
                               self.annotation(start_s=0.014, end_s=0.015, label='short'),
                               self.annotation(start_s=0.016, end_s=0.018, label='subframe'),
                               self.annotation(start_s=0, end_s=0.02, status='suggested', label='music'))
        report = write_aligned(self.wav, self.annotations, self.output)
        rows = [json.loads(line) for line in self.output.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(report, dict(frames=4, labeled_frames=3, unmatched_intervals=1))
        self.assertEqual([row['labels'] for row in rows], [['impact'], ['impact', 'texture'], ['short'], None])
        self.assertEqual([row['frame']['sample_index'] for row in rows], [239, 479, 719, 959])
        self.assertTrue(all(len(row['frame']['features']) == 16 for row in rows))
        with self.assertRaises(FileExistsError):
            write_aligned(self.wav, self.annotations, self.output)

    def test_rejects_wrong_source_mixed_sessions_and_invalid_annotation(self):
        for rows in ((self.annotation(source_id='wrong'),),
                     (self.annotation(), self.annotation(session_id='second')),
                     (self.annotation(origin='visual_ai'),),
                     (self.annotation(end_s=float('nan')),),
                     (self.annotation(end_s=0.1),),
                     (self.annotation(status='suggested'),)):
            with self.subTest(rows=rows):
                self.write_annotations(*rows)
                with self.assertRaises(ValueError):
                    write_aligned(self.wav, self.annotations, self.output)
                self.assertFalse(self.output.exists())

    def test_explicit_absence_is_aligned_and_conflicts_are_rejected(self):
        negative = self.annotation(present=False)
        self.write_annotations(self.annotation(), negative)
        with self.assertRaisesRegex(ValueError, 'Conflicting positive and negative'):
            write_aligned(self.wav, self.annotations, self.output)
        self.assertFalse(self.output.exists())
        self.write_annotations(negative)
        self.assertEqual(write_aligned(self.wav, self.annotations, self.output)['labeled_frames'], 2)
        rows = [json.loads(line) for line in self.output.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([row.get('negative_labels') for row in rows], [['impact'], ['impact'], None, None])
        self.assertTrue(all(row['labels'] is None for row in rows))

    def test_cli_handoff_from_reviewed_wav_to_paired_report(self):
        def run(script, *args):
            command = Path(__file__).with_name(script)
            result = subprocess.run([sys.executable, '-B', str(command), *map(str, args)],
                                    capture_output=True, encoding='utf-8', check=True, timeout=20)
            return json.loads(result.stdout)

        self.write_annotations(self.annotation(),
                               self.annotation(start_s=.013, end_s=.017, present=False))
        alignment = run('training_alignment.py', self.wav, self.annotations, self.output)
        self.assertEqual(alignment['labeled_frames'], 3)
        rows = [json.loads(line) for line in self.output.read_text(encoding='utf-8').splitlines()]
        root = self.output.parent
        model = root / 'fixture-model.bin'
        model.write_bytes(b'Fixture model bytes used for hash validation only.')

        def predictions(name, scores):
            results, manifest = root / f'{name}.jsonl', root / f'{name}.json'
            entries = []
            for row, score in zip(rows, scores):
                identity = {key: row['frame'][key] for key in FRAME_KEYS}
                entries.append(dict(identity, kind='inference_result', version=1,
                                    model_id=name, probabilities=[score], valid=True))
            results.write_text(''.join(json.dumps(entry) + '\n' for entry in entries), encoding='utf-8')
            info = dict(version=1, model_id=name, threshold=.5, labels=['impact'],
                        aligned_sha256=sha256(self.output.read_bytes()).hexdigest())
            if name == 'gru':
                info.update(model_sha256=sha256(model.read_bytes()).hexdigest(),
                            feature_schema_id=rows[0]['frame']['feature_schema_id'])
            manifest.write_text(json.dumps(info), encoding='utf-8')
            return results, manifest

        candidate = predictions('gru', [.9, .9, .1, .9])
        reference = predictions('dsp', [.9, .1, .9, .9])
        report = run('training_evaluation.py', self.output, *candidate, '--model-artifact', model,
                     '--reference', *reference)
        comparison = report['reference_comparison']['per_label']['impact']
        self.assertEqual(comparison['recall_delta'], .5)
        self.assertEqual(comparison['false_positive_rate_delta'], -1.0)
        self.assertEqual(report['unreviewed_frames'], 1)
