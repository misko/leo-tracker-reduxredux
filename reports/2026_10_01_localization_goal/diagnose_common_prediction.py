"""Common omitted-sample prediction for three sealed inference arms; no GPS."""
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from adapter import TrackPort
from physics import TrackObservations
from regression_batch import digest, verify_sources

from leo.analysis.localization_predictive import conditional_student_logpdf

HERE = Path(__file__).resolve().parent


def main():
    start = time.monotonic()
    rows = []
    for unit in ['DS9-F001', 'DS10-F056', 'DS11-F001']:
        baseline_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        paths = [baseline_path, HERE/'track-partition-v1'/(unit+'.json'),
                 HERE/'track-fragments-v1'/(unit+'.json')]
        receipts = []
        for path in paths:
            assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                'prediction_sha256']
            receipt = json.loads(path.read_text())
            verify_sources(receipt['source_sha256'])
            verify_sources(receipt['inputs'])
            assert receipt['best']['converged']
            receipts.append(receipt)
        states = [np.asarray(r['best']['mean']) for r in receipts]
        common = set.intersection(*[set(map(tuple, r['observations'])) for r in receipts])
        used = {v for r in receipts for t in r['observations'] for v in t}
        scan, height, ports = prepare(unit)
        details, skipped = [], 0
        for (track_id, track), port in zip(scan.tracks, ports, strict=True):
            if tuple(port.observation_ids) not in common:
                continue
            assert len(set(track.receiver_indices)) == 1
            train = [track.observation_ids.index(v) for v in port.observation_ids]
            omitted = [i for i, v in enumerate(track.observation_ids) if v not in used]
            if len(omitted) < 3:
                skipped += 1
                continue
            chosen = np.unique(np.linspace(0, len(omitted)-1, min(8, len(omitted)), dtype=int))
            check = [omitted[i] for i in chosen]
            indices = sorted(train+check)
            observation = TrackObservations(
                tuple(track.observation_ids[i] for i in indices), track.times_s[indices],
                track.frequencies_hz[indices], track.receiver_indices[indices], track.rf_hz)
            full = TrackPort(observation, scan.bank, scan.layout,
                             replace(scan.config, max_points=len(indices)), height)
            basis = full.likelihood.contrasts
            assert np.allclose(basis@basis.T, np.eye(len(indices)-1))
            contrast = np.zeros((len(indices)-1, len(indices)))
            train_columns = [indices.index(i) for i in train]
            k = len(train)-1
            contrast[:k, train_columns] = port.likelihood.contrasts
            for j, i in enumerate(check):
                contrast[k+j, indices.index(i)] = 1.
                contrast[k+j, train_columns] = -1./len(train)
            transform = contrast@basis.T
            scores, assignments = [], []
            for state in states:
                index = int(np.argmax(port.score_all(state)))
                assignments.append(index)
                if index == port.candidate_count:
                    break
                prediction = full.predict_selected(state, index)
                residual = transform@(full.observation-prediction.mean)
                scale = transform@prediction.covariance@transform.T
                scores.append(conditional_student_logpdf(residual, scale, k))
            if len(scores) != 3:
                skipped += 1
                continue
            details.append(dict(track_id=track_id, training_ids=list(port.observation_ids),
                                check_ids=[track.observation_ids[i] for i in check],
                                assigned_norad_ids=[scan.bank.norad_ids[i] for i in assignments],
                                conditional_log_scores=scores))
        totals = np.sum([r['conditional_log_scores'] for r in details], axis=0)
        rows.append(dict(unit=unit, common_tracks=len(common), scored_tracks=len(details),
                         skipped=skipped, check_samples=sum(len(r['check_ids']) for r in details),
                         total_log_scores=totals.tolist(), details=details,
                         parents={str(p): digest(p) for p in paths}))
    result = dict(arms=['baseline', 'detector_margin', 'append_fragments'], rows=rows,
                  seconds=time.monotonic()-start, source_sha256={
                      str(Path(__file__)): digest(__file__),
                      str(HERE.parents[1]/'src/leo/analysis/localization_predictive.py'):
                      digest(HERE.parents[1]/'src/leo/analysis/localization_predictive.py')},
                  qualification='Common original tracks only; checking visits excluded from all '
                  'three arms fitting/acquisition samples. Up to8checking points per track; '
                  'conditional joint t4 accounts for shared noise scale, temporal covariance '
                  'and fitted frequency offset via contrasts. State and identities are plug-in '
                  'training estimates, not posterior integration. All points participated in '
                  'upstream trajectory construction: this is post-selection prediction, NOT '
                  'independent validation. Common subset omits changed tracks; no GPS or refit.')
    output = HERE/'common-prediction-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps([{k: v for k, v in r.items() if k not in ['details', 'parents']}
                      for r in rows], indent=2))


if __name__ == '__main__':
    main()
