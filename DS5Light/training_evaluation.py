"""Check external GRU replay results against one human-labeled DS5Light replay."""

import argparse
from collections import Counter
from hashlib import file_digest, sha256
import json
from pathlib import Path
import re


FRAME_KEYS = ('stream_generation', 'profile_revision', 'feature_schema_id',
              'inference_epoch', 'sequence', 'sample_index')
RESULT_KEYS = set(FRAME_KEYS) | {'kind', 'version', 'model_id', 'valid', 'probabilities'}
IDENTIFIER = re.compile(r'[A-Za-z0-9_.:-]{1,96}')


def frame_identity(frame):
    generation, revision, schema, epoch, sequence, sample = (frame.get(key) for key in FRAME_KEYS)
    if (any(type(value) is not int or not minimum <= value <= maximum
            for value, minimum, maximum in ((generation, 1, 0xffffffff), (revision, 0, 0xffffffff),
                                           (epoch, 1, 0xffffffff), (sequence, 0, 0xffffffff),
                                           (sample, 0, 9007199254740991)))
            or not isinstance(schema, str) or IDENTIFIER.fullmatch(schema) is None):
        raise ValueError('Invalid V1 frame identity.')
    return generation, revision, schema, epoch, sequence, sample


def json_rows(handle):
    for line_number, line in enumerate(handle, 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f'JSONL line {line_number} must be an object.')
        yield row


def evaluate(aligned_path, results_path, manifest_path, *, model_artifact=None):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if not isinstance(manifest, dict) or type(manifest.get('version')) is not int or manifest['version'] != 1:
        raise ValueError('Unsupported evaluation manifest version.')
    model_id = manifest.get('model_id')
    labels = manifest.get('labels')
    threshold = manifest.get('threshold')
    if (not isinstance(model_id, str) or IDENTIFIER.fullmatch(model_id) is None
            or not isinstance(labels, list) or not 1 <= len(labels) <= 64
            or any(not isinstance(label, str) or not label or label != label.strip() for label in labels)
            or len(set(labels)) != len(labels)
            or type(threshold) not in (int, float) or not 0 <= threshold <= 1):
        raise ValueError('Invalid model ID, ordered labels, or decision threshold.')
    columns = {label: index for index, label in enumerate(labels)}
    artifact = {}
    if model_artifact is not None:
        schema = manifest.get('feature_schema_id')
        if not isinstance(schema, str) or IDENTIFIER.fullmatch(schema) is None:
            raise ValueError('The model artifact requires a declared feature schema ID.')
        with model_artifact.open('rb') as handle:
            if not handle.read(1):
                raise ValueError('The model artifact is empty.')
            handle.seek(0)
            model_digest = file_digest(handle, 'sha256').hexdigest()
        if manifest.get('model_sha256') != model_digest:
            raise ValueError('Model artifact SHA-256 does not match the prediction manifest.')
        artifact = dict(model_sha256=model_digest, feature_schema_id=schema)

    with aligned_path.open('rb') as handle:
        digest = file_digest(handle, 'sha256').hexdigest()
        if manifest.get('aligned_sha256') != digest:
            raise ValueError('Aligned replay SHA-256 does not match the prediction manifest.')

    predictions = {}
    previous = -1
    with results_path.open(encoding='utf-8-sig') as handle:
        for row in json_rows(handle):
            sequence = row.get('sequence')
            probabilities = row.get('probabilities')
            if (row.keys() != RESULT_KEYS
                    or row.get('kind') != 'inference_result'
                    or type(row.get('version')) is not int or row['version'] != 1
                    or row.get('model_id') != model_id or type(row.get('valid')) is not bool
                    or type(sequence) is not int or not previous < sequence <= 0xffffffff
                    or not isinstance(probabilities, list) or len(probabilities) != len(labels)
                    or any(type(value) not in (int, float) or not 0 <= value <= 1 for value in probabilities)):
                raise ValueError(f'Invalid, duplicate, or out-of-order inference result at sequence {sequence}.')
            previous = sequence
            predictions[sequence] = (frame_identity(row), row)
    if not predictions:
        raise ValueError('No inference results to evaluate.')

    totals, evaluated, detected = Counter(), Counter(), Counter()
    negative_totals, negative_evaluated, false_positives = Counter(), Counter(), Counter()
    coverage = sha256()
    identity = None
    frame_count = confirmed = matched = valid = 0
    with aligned_path.open(encoding='utf-8-sig') as handle:
        for sequence, row in enumerate(json_rows(handle)):
            frame, truth = row.get('frame'), row.get('labels')
            negatives = row.get('negative_labels', [])
            source = tuple(row.get(key) for key in ('source_id', 'game_id', 'session_id'))
            if (any(not isinstance(value, str) or not value for value in source)
                    or (identity is not None and identity != source) or not isinstance(frame, dict)
                    or frame.get('kind') != 'feature_frame' or type(frame.get('version')) is not int or frame['version'] != 1
                    or type(frame.get('sequence')) is not int or frame['sequence'] != sequence
                    or 'labels' not in row
                    or not isinstance(negatives, list)
                    or any(not isinstance(label, str) or not label or label != label.strip()
                           for label in negatives)
                    or (truth is not None and (not isinstance(truth, list) or not truth
                                               or any(not isinstance(label, str) or not label for label in truth)))):
                raise ValueError(f'Invalid aligned frame at sequence {sequence}.')
            frame_key = frame_identity(frame)
            if artifact and frame['feature_schema_id'] != artifact['feature_schema_id']:
                raise ValueError(f'Model feature schema does not match aligned frame at sequence {sequence}.')
            identity = source
            frame_count += 1
            truth = set(truth or ())
            negatives = set(negatives)
            if truth & negatives:
                raise ValueError(f'Conflicting positive and negative labels at sequence {sequence}.')
            confirmed += bool(truth or negatives)
            totals.update(truth)
            negative_totals.update(negatives)
            prediction = predictions.pop(sequence, None)
            if prediction is None:
                continue
            result_key, result = prediction
            if result_key != frame_key:
                raise ValueError(f'Inference result does not match aligned frame at sequence {sequence}.')
            matched += 1
            if not result['valid']:
                continue
            valid += 1
            if (truth | negatives) & columns.keys():
                coverage.update(sequence.to_bytes(4, 'little'))
            for label in truth & columns.keys():
                evaluated[label] += 1
                detected[label] += result['probabilities'][columns[label]] >= threshold
            for label in negatives & columns.keys():
                negative_evaluated[label] += 1
                false_positives[label] += result['probabilities'][columns[label]] >= threshold
    if predictions:
        raise ValueError('Inference results contain sequences absent from the aligned replay.')

    return dict(model_id=model_id, aligned_sha256=digest, threshold=threshold, frames=frame_count,
                confirmed_coverage_sha256=coverage.hexdigest(),
                matched_results=matched, valid_results=valid, confirmed_frames=confirmed,
                unreviewed_frames=frame_count-confirmed,
                labels_outside_model={label: totals[label] for label in sorted(totals.keys() - columns.keys())},
                negative_labels_outside_model={label: negative_totals[label]
                    for label in sorted(negative_totals.keys() - columns.keys())},
                negative_per_label={label: dict(confirmed=negative_totals[label], evaluated=negative_evaluated[label],
                    false_positives=false_positives[label], false_positive_rate=(
                        false_positives[label] / negative_evaluated[label] if negative_evaluated[label] else None))
                    for label in labels},
                per_label={label: dict(confirmed=totals[label], evaluated=evaluated[label],
                                       detected=detected[label],
                                       recall_on_evaluated=detected[label]/evaluated[label] if evaluated[label] else None)
                           for label in labels}, **artifact)


def compare_reference(candidate, reference):
    if any(candidate[key] != reference[key] for key in (
            'aligned_sha256', 'threshold', 'confirmed_coverage_sha256')):
        raise ValueError('Comparison requires the same replay, threshold and covered confirmed frames.')
    if candidate['per_label'].keys() != reference['per_label'].keys():
        raise ValueError('Comparison requires the same evaluated labels.')
    comparisons = {}
    for label, current in candidate['per_label'].items():
        baseline = reference['per_label'][label]
        recall = current['recall_on_evaluated']
        reference_recall = baseline['recall_on_evaluated']
        negative = candidate['negative_per_label'][label]
        fpr = negative['false_positive_rate']
        reference_fpr = reference['negative_per_label'][label]['false_positive_rate']
        comparisons[label] = dict(evaluated=current['evaluated'], candidate_recall=recall,
                                  reference_recall=reference_recall,
                                  recall_delta=recall - reference_recall if recall is not None else None,
                                  negative_evaluated=negative['evaluated'],
                                  candidate_false_positive_rate=fpr, reference_false_positive_rate=reference_fpr,
                                  false_positive_rate_delta=fpr - reference_fpr if fpr is not None else None)
    return dict(reference_id=reference['model_id'], per_label=comparisons)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('aligned', 'results', 'manifest'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--model-artifact', type=Path, help='Check model bytes and feature schema without loading it.')
    parser.add_argument('--reference', nargs=2, type=Path, metavar=('RESULTS', 'MANIFEST'),
                        help='Compare with a DSP Only reference on the same confirmed frames.')
    args = parser.parse_args()
    try:
        report = evaluate(args.aligned, args.results, args.manifest, model_artifact=args.model_artifact)
        if args.reference:
            reference = evaluate(args.aligned, *args.reference)
            report['reference_comparison'] = compare_reference(report, reference)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
