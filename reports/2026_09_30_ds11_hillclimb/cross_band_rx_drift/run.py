"""Training-only cross-source slope transfer, scored on frozen held pairs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
spec = importlib.util.spec_from_file_location('offset_audit', HILL/'cross_source_rx_offset/run.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
PERIOD = audit.PERIOD


def slope_fit(donors):
    if len(donors) < 3:
        return None
    t = np.array([v[0] for v in donors])
    y = np.array([v[1] for v in donors])
    center = audit.medoid(y)
    y = center + audit.wrap(y-center)
    slopes = [(y[j]-y[i])/(t[j]-t[i]) for i in range(len(t))
              for j in range(i+1, len(t)) if abs(t[j]-t[i]) >= 1]
    if not slopes:
        return None
    slope = float(np.median(slopes))
    return (slope, float(t.min()), float(t.max())) if abs(slope) <= 20 else None


def predict(train_t, train_y, held_t, fit):
    center = audit.medoid(train_y)
    unwrapped = center + audit.wrap(np.asarray(train_y)-center)
    constant = float(np.median(unwrapped))
    baseline = np.full(len(held_t), constant)
    result = baseline.copy()
    if fit is not None:
        slope, lower, upper = fit
        origin = float(np.median(train_t))
        intercept = float(np.median(unwrapped-slope*(np.asarray(train_t)-origin)))
        use = (held_t >= lower) & (held_t <= upper)
        result[use] = intercept+slope*(held_t[use]-origin)
    return baseline, result


def main():
    source = HILL/'same_source_cfo_audit/results.json'
    data = json.loads(source.read_text())
    audit.verify_tree(data['source_sha256'])
    plan_path = HILL.parent/'2026_09_30_ds11_single10/plan.json'
    plan = json.loads(plan_path.read_text())
    paths = [source, plan_path, Path(__file__), HERE/'PROTOCOL.md', HERE/'test_run.py',
             HILL/'cross_source_rx_offset/run.py']
    output = []
    for index in range(0, 32, 4):
        entry = plan['inputs'][index]
        artifact = next(a for a in entry['artifacts'] if a['kind'] == 'observations')
        path = Path(artifact['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact['sha256'].removeprefix('sha256:')
        paths.append(path)
        doc = json.loads(path.read_text())
        assert doc['session_id'] == entry['session_id']
        tracks = {t['track_id']: t for t in doc['tracks']}
        pairs = []
        for row in data['cross_receiver_pair_rows']:
            if row['scan_index'] != index:
                continue
            a, b = tracks[row['track_a']], tracks[row['track_b']]
            if a['receiver_id'] == 0:
                a, b = b, a
            assert a['receiver_id'] == 1 and b['receiver_id'] == 0
            assert a['rf_hz'] == b['rf_hz']
            def unique_indices(track):
                visits = track['visits']
                return {v:i for i,v in enumerate(visits) if visits.count(v) == 1}
            left, right = unique_indices(a), unique_indices(b)
            train, held = [], []
            for visit in sorted(left.keys() & right.keys()):
                i, j = left[visit], right[visit]
                ta, tb = a['times_s'][i], b['times_s'][j]
                if abs(ta-tb) > 1e-4:
                    continue
                ma, mb = a['training_mask'][i], b['training_mask'][j]
                if ma != mb:
                    continue
                y = audit.wrap((a['measured_hz'][i]-b['measured_hz'][j])*a['rf_hz']/11.2e9)
                (train if ma else held).append([(ta+tb)/2, y])
            if len(train) < 6:
                continue
            pairs.append(dict(norad=row['norad_a'], rf_hz=a['rf_hz'],
                              tracks=[a['track_id'], b['track_id']],
                              train=np.array(train), held=np.array(held).reshape(-1,2)))
        for target in pairs:
            donors = {}
            for other in pairs:
                if other['norad'] == target['norad']:
                    continue
                donors.setdefault(other['norad'], []).append((float(np.median(other['train'][:,0])),
                                                              audit.medoid(other['train'][:,1])))
            centers = [(float(np.median([v[0] for v in rows])), audit.medoid([v[1] for v in rows]))
                       for rows in donors.values()]
            fit = slope_fit(centers)
            baseline, predicted = predict(target['train'][:,0], target['train'][:,1], target['held'][:,0], fit)
            errors0 = abs(audit.wrap(target['held'][:,1]-baseline))
            errors1 = abs(audit.wrap(target['held'][:,1]-predicted))
            output.append(dict(scan_index=index, norad=target['norad'], rf_hz=target['rf_hz'],
                               tracks=target['tracks'], training_rows=len(target['train']),
                               held_rows=len(target['held']), donor_count=len(donors), fit=fit,
                               applied_rows=int(np.sum(predicted != baseline)),
                               constant_absolute_errors_hz=errors0.tolist(),
                               drift_absolute_errors_hz=errors1.tolist(),
                               mean_gain_hz=float(np.mean(errors0-errors1)) if len(errors0) else None))
    scans = {}
    for index in range(0,32,4):
        by_source = {}
        for row in output:
            if row['scan_index'] == index and row['mean_gain_hz'] is not None:
                by_source.setdefault(row['norad'], []).append(row['mean_gain_hz'])
        scans[index] = float(np.mean([np.mean(v) for v in by_source.values()])) if by_source else None
    gains = [v for v in scans.values() if v is not None]
    summary = dict(pairs=len(output), fitted_pairs=sum(r['fit'] is not None for r in output),
                   held_rows=sum(r['held_rows'] for r in output),
                   applied_rows=sum(r['applied_rows'] for r in output), scan_gains_hz=scans,
                   mean_scan_gain_hz=float(np.mean(gains)) if gains else None,
                   median_scan_gain_hz=float(np.median(gains)) if gains else None,
                   gate_pass=bool(len(gains)==8 and sum(v>0 for v in gains)>=5 and np.mean(gains)>0 and np.median(gains)>0))
    result = dict(summary=summary, rows=output, position_fits=0, reference_used=False,
                  sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (HERE/'outcome.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
