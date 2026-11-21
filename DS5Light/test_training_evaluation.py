from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from training_evaluation import compare_reference, evaluate


class TrainingEvaluationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.aligned, self.results, self.manifest = (root / name for name in ('aligned', 'results', 'manifest'))
        identity = dict(source_id='replay', game_id='game', session_id='session')
        self.frames = [
            dict(kind='feature_frame', version=1, stream_generation=1, profile_revision=0,
                 feature_schema_id='evidence.v1', inference_epoch=1, sequence=i,
                 sample_index=239+i*240, features=[0] * 16)
            for i in range(5)
        ]
        truth = [['impact'], ['impact', 'texture'], None, ['impact'], ['unmapped']]
        self.write_rows(self.aligned, [dict(identity, labels=tags, frame=frame)
                                       for frame, tags in zip(self.frames, truth)])
        self.setup_manifest = dict(version=1, model_id='gru.probe', threshold=.6,
                                   aligned_sha256=sha256(self.aligned.read_bytes()).hexdigest(),
                                   labels=['texture', 'impact'])
        self.manifest.write_text(json.dumps(self.setup_manifest), encoding='utf-8')

    def write_rows(self, path, rows):
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf-8')

    def prediction(self, index, probabilities=(.1, .9), **changes):
        row = dict(self.frames[index], kind='inference_result', model_id='gru.probe',
                   probabilities=list(probabilities), valid=True)
        del row['features']
        return row | changes

    def test_reports_recall_only_on_covered_confirmed_frames(self):
        self.write_rows(self.results, [
            self.prediction(0), self.prediction(1, (.7, .2)), self.prediction(2),
            self.prediction(3, valid=False),
        ])
        report = evaluate(self.aligned, self.results, self.manifest)
        self.assertEqual((report['matched_results'], report['valid_results']), (4, 3))
        self.assertEqual(report['unreviewed_frames'], 1)
        self.assertEqual(report['labels_outside_model'], {'unmapped': 1})
        self.assertEqual(report['per_label']['impact'],
                         dict(confirmed=3, evaluated=2, detected=1, recall_on_evaluated=.5))
        self.assertEqual(report['per_label']['texture']['recall_on_evaluated'], 1)

    def test_rejects_wrong_metadata_duplicate_order_and_invalid_probabilities(self):
        good = self.prediction(0)
        cases = ([good, good], [self.prediction(1), good],
                 [self.prediction(0, inference_epoch=2)], [self.prediction(0, sample_index=240)],
                 [self.prediction(0, (True, .5))], [self.prediction(0, (float('nan'), .5))],
                 [self.prediction(0, (.5,))], [self.prediction(0, model_id='other')],
                 [self.prediction(0, sequence=11)])
        for rows in cases:
            with self.subTest(rows=rows):
                self.write_rows(self.results, rows)
                with self.assertRaises(ValueError):
                    evaluate(self.aligned, self.results, self.manifest)

    def test_reference_comparison_requires_identical_confirmed_frame_coverage(self):
        self.write_rows(self.results, [self.prediction(0), self.prediction(2)])
        candidate = evaluate(self.aligned, self.results, self.manifest)
        reference_manifest = self.setup_manifest | {'model_id': 'dsp.only'}
        self.manifest.write_text(json.dumps(reference_manifest), encoding='utf-8')
        self.write_rows(self.results, [self.prediction(0, (.1, .2), model_id='dsp.only')])
        reference = evaluate(self.aligned, self.results, self.manifest)
        comparison = compare_reference(candidate, reference)
        self.assertEqual(comparison['reference_id'], 'dsp.only')
        self.assertEqual(comparison['per_label']['impact']['recall_delta'], 1.0)
        self.assertIsNone(comparison['per_label']['texture']['recall_delta'])
        self.write_rows(self.results, [self.prediction(3, model_id='dsp.only')])
        with self.assertRaisesRegex(ValueError, 'covered confirmed frames'):
            compare_reference(candidate, evaluate(self.aligned, self.results, self.manifest))

    def test_optional_artifact_checks_model_bytes_and_replay_schema(self):
        self.write_rows(self.results, [self.prediction(0)])
        model = self.manifest.with_name('model.bin')
        model.write_bytes(b'Test model bytes')
        digest = sha256(model.read_bytes()).hexdigest()
        manifest = self.setup_manifest | dict(model_sha256=digest, feature_schema_id='evidence.v1')
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        report = evaluate(self.aligned, self.results, self.manifest, model_artifact=model)
        self.assertEqual((report['model_sha256'], report['feature_schema_id']), (digest, 'evidence.v1'))
        self.assertNotIn('model_sha256', evaluate(self.aligned, self.results, self.manifest))
        self.manifest.write_text(json.dumps(manifest | dict(feature_schema_id='other.v1')), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'feature schema'):
            evaluate(self.aligned, self.results, self.manifest, model_artifact=model)
        model.write_bytes(b'Changed model bytes')
        with self.assertRaisesRegex(ValueError, 'Model artifact SHA-256'):
            evaluate(self.aligned, self.results, self.manifest, model_artifact=model)

    def test_false_positive_rate_uses_only_explicitly_reviewed_negatives(self):
        rows = [json.loads(line) for line in self.aligned.read_text(encoding='utf-8').splitlines()]
        rows[2]['negative_labels'] = ['impact']
        rows[4]['negative_labels'] = ['impact']
        self.write_rows(self.aligned, rows)
        manifest = self.setup_manifest | dict(aligned_sha256=sha256(self.aligned.read_bytes()).hexdigest())
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        self.write_rows(self.results, [self.prediction(2), self.prediction(3), self.prediction(4, (.1, .2))])
        candidate = evaluate(self.aligned, self.results, self.manifest)
        self.assertEqual(candidate['negative_per_label']['impact'],
                         dict(confirmed=2, evaluated=2, false_positives=1, false_positive_rate=.5))
        self.assertIsNone(candidate['negative_per_label']['texture']['false_positive_rate'])
        self.write_rows(self.results, [self.prediction(i, (.1, .2)) for i in (2, 3, 4)])
        reference = evaluate(self.aligned, self.results, self.manifest)
        delta = compare_reference(candidate, reference)['per_label']['impact']
        self.assertEqual(delta['false_positive_rate_delta'], .5)

        rows[3]['negative_labels'] = ['impact']
        self.write_rows(self.aligned, rows)
        manifest['aligned_sha256'] = sha256(self.aligned.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Conflicting positive and negative'):
            evaluate(self.aligned, self.results, self.manifest)

    def test_rejects_replay_content_changes_and_duplicate_manifest_labels(self):
        self.write_rows(self.results, [self.prediction(0)])
        amended = self.setup_manifest | {'labels': ['impact', 'impact']}
        self.manifest.write_text(json.dumps(amended), encoding='utf-8')
        with self.assertRaises(ValueError):
            evaluate(self.aligned, self.results, self.manifest)
        self.manifest.write_text(json.dumps(self.setup_manifest), encoding='utf-8')
        with self.aligned.open('a', encoding='utf-8') as handle:
            handle.write('\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            evaluate(self.aligned, self.results, self.manifest)
