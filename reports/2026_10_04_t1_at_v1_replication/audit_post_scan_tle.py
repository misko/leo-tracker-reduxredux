"""Reconstruct matched ephemeris fits; distinguish fit quality from location truth."""
import argparse
import json
from pathlib import Path
import numpy as np
import post_scan_tle_localization as experiment
from post_scan_tle_bank import OUT as BANKS, load_variant, frozen_fields_equal, HOUR_NS
from render_leave_one_satellite_out import check_stationarity
from subset_positions import serial
from timing_bound_comparison import digest


def diagnostics(obj, data, record):
    vector = np.asarray(record['vector'])
    score, kkt = check_stationarity(obj, record, 4.)
    probabilities = obj.likelihood.last_result['row_association_probability'].copy()
    penalty = obj.base.penalty(vector[:obj.size])[0]
    predicted, _ = obj.base.predict(vector[:obj.size])
    predicted += (obj.features @ vector[obj.size:])[:, None]
    residual = (data.measured[:, None] - predicted + obj.likelihood.alias_hz / 2) % obj.likelihood.alias_hz - obj.likelihood.alias_hz / 2
    rows = np.arange(len(data.times))
    owners = np.array([int(np.flatnonzero(data.numbers == n)[0]) for n in data.owners])
    most_likely = probabilities.argmax(axis=1)
    supported = probabilities[rows, most_likely] > .5
    return dict(objective=score, data_nll=score-penalty, timing_prior_nll=penalty, kkt=kkt,
        distance_m=1000*np.linalg.norm(record['point_km']),
        converged=bool(kkt <= 1e-3 and not record['fixed_location']),
        boundary=bool(np.linalg.norm(record['point_km']) >= 3.9999),
        strong_soft_windows=int(sum(supported)),
        strong_original_owner_windows=int(sum(probabilities[rows, owners] > .5)),
        strong_changed_owner_windows=int(sum(supported & (most_likely != owners))),
        owner_rms_hz=float(np.sqrt(np.mean(residual[rows, owners]**2))),
        owner_median_absolute_residual_hz=float(np.median(abs(residual[rows, owners]))),
        posterior_weighted_residual_rms_hz=float(np.sqrt(np.sum(probabilities*residual**2)/np.sum(probabilities))))


def validate_element(row, end):
    old, new = row['original'], row['selected']
    if row['post_scan']:
        assert end < new['epoch_utc_ns'] <= end + 24*HOUR_NS
        assert end < new['collected_utc_ns'] <= end + 48*HOUR_NS
    else:
        assert (old['line1'], old['line2']) == (new['line1'], new['line2'])
    assert row['changed'] == ((old['line1'], old['line2']) != (new['line1'], new['line2']))


def main(root):
    rows = []; cohort = []; pairs = []; source_hashes = {}; changed = fallback = 0
    for scan in experiment.SCANS:
        receipt = json.loads((BANKS/scan/'bank.json').read_text())
        assert receipt['original_bank_reproduced']
        for element in receipt['elements']:
            validate_element(element, receipt['scan_end_utc_ns'])
            source = element['selected']['source']
            if source not in source_hashes:source_hashes[source] = digest(Path(source))
            assert source_hashes[source] == element['selected']['source_sha256']
        changed += receipt['summary']['changed']; fallback += receipt['summary']['fallback']
        data = {v: load_variant(scan, v) for v in experiment.VARIANTS}
        frozen_fields_equal(data['original'][0], data['post-scan'][0])
        cases = {}
        for arm in experiment.ARMS:
            for variant in experiment.VARIANTS:
                path = root/scan/f'{arm}-{variant}.json'; r = json.loads(path.read_text())
                d, meta, _, _ = data[variant]
                assert r['input_sha256'] == meta['input_sha256']
                assert r['numbers'] == d.numbers.tolist()
                assert r['fit_original_rows'] == r['evaluation_original_rows'] == d.original_rows.tolist()
                assert not r['heldout_original_rows']
                assert r['bank_receipt_sha256'] == digest(BANKS/scan/'bank.json')
                obj = experiment.make_objective(d, meta, arm)
                metrics = diagnostics(obj, d, r['best'])
                assert abs(metrics['objective'] - r['objective']) < 1e-7
                assert abs(metrics['kkt'] - r['kkt']) < 1e-7
                assert metrics['converged'] == r['converged']
                assert np.linalg.norm(r['best']['point_km']) <= 4.+1e-7
                assert np.max(abs(np.asarray(r['best']['parameters'])[6:])) <= 20.+1e-7
                if arm == 'zero-c':assert abs(r['best']['vector'][-1]) < 1e-10
                roof = diagnostics(obj, d, r['roof'])
                row = dict(scan=scan, arm=arm, variant=variant, **metrics,
                    roof_objective=roof['objective'], roof_data_nll=roof['data_nll'],
                    roof_timing_prior_nll=roof['timing_prior_nll'],
                    roof_posterior_weighted_residual_rms_hz=roof['posterior_weighted_residual_rms_hz'],
                    original_owner_windows=len(d.times), receipt_sha256=digest(path))
                rows.append(row); cases[arm, variant] = r
            a, b = [next(x for x in rows if (x['scan'], x['arm'], x['variant']) == (scan, arm, v)) for v in experiment.VARIANTS]
            pairs.append(dict(scan=scan, arm=arm, both_converged=a['converged'] and b['converged'],
                error_change_m=b['distance_m']-a['distance_m'], objective_change=b['objective']-a['objective'],
                data_nll_change=b['data_nll']-a['data_nll'], prior_nll_change=b['timing_prior_nll']-a['timing_prior_nll'],
                roof_data_nll_change=b['roof_data_nll']-a['roof_data_nll']))
        reference = cases['fitted-c', 'original']
        for r in cases.values():
            for key in ('input_sha256', 'numbers', 'fit_original_rows', 'maximum_budgets_s',
                        'roof_starts', 'spatial_starts', 'radius_km', 'total_timing_bound_s'):
                assert r[key] == reference[key], (scan, key)
            assert r.get('polish_maximum_budgets_s') == reference.get('polish_maximum_budgets_s')
    for arm in experiment.ARMS:
        for variant in experiment.VARIANTS:
            subset = [r for r in rows if (r['arm'], r['variant']) == (arm, variant)]
            errors = np.array([r['distance_m'] for r in subset])
            cohort.append(dict(arm=arm, variant=variant, scans=len(subset), below_1km=int(sum(errors < 1000)),
                median_error_m=float(np.median(errors)), mean_error_m=float(np.mean(errors)),
                unconverged=sum(not r['converged'] for r in subset), boundary=sum(r['boundary'] for r in subset)))
    assert len(rows) == 64
    report = dict(status='passed', cases=len(rows), converged=sum(r['converged'] for r in rows),
        post_scan_elements=changed, fallback_elements=fallback, cohort=cohort, rows=rows, pairs=pairs,
        notes=['All localization fit/evaluation rows identical; no held-out position fits.',
               'Legacy upstream fold-derived receiver baseline remains unchanged in this orbit-only test.',
               'Posterior-weighted residual RMS is conditional fit quality, not coverage or position accuracy.',
               'A passed audit does not certify optimizer convergence or a global minimum.'])
    (root/'audit.json').write_text(json.dumps(report, default=serial, indent=2, allow_nan=False))
    print(json.dumps(dict(converged=report['converged'], cohort=cohort), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--polished', action='store_true'); args = parser.parse_args()
    main(BANKS/'polished' if args.polished else BANKS)
