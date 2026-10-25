"""Geographic reporter for sealed diagnostic endpoints; no inference imports."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCIENCE = ROOT/'scientific'
CENTER = (37.906, -122.545)
SITE = (37.849061591561885, -122.48574968092912)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def coordinates(x):
    east, north = x
    return [CENTER[0]+north/111., CENTER[1]+east/(111.32*np.cos(np.radians(CENTER[0])))]


def error_km(latlon):
    a, b = np.radians(np.array([latlon, SITE]))
    h = np.sin((a[0]-b[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((a[1]-b[1])/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(h, 0, 1))))


def csv_new(name, rows):
    with (HERE/name).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def main():
    seal_path = SCIENCE/'RF_seal03.json'
    seal = read(seal_path)
    for path, digest in seal['files'].items():
        assert sha(path) == digest, path
    independent = read(ROOT/'audit/terminal_audit.json')
    math = read(ROOT/'math_audit/terminal03_audit.json')
    assert independent['status'] == 'passed' and math['all_passed'] is True
    assert math['RF_seal_sha256'] == sha(seal_path)
    assert independent['RF_seal_sha256'] == sha(seal_path)
    result = read(SCIENCE/'execution_result03.json')
    with (ROOT/'audit/saved_control_reference.csv').open() as stream:
        controls = list(csv.DictReader(stream))
    csv_new('saved_controls.csv', controls)
    baseline = {(row['case'], row['arm']):row for row in controls if row['saved_control'] == 'saved_baseline'}
    rows = []
    for fit in result['fits']:
        case, arm, branch = (fit[key] for key in ('case', 'arm', 'branch'))
        directory = SCIENCE/'fits03'/case/arm/branch
        gates = read(directory/'parent_gates.json')
        diagnostics = read(directory/'rf_diagnostics.json')
        x = fit.get('endpoint_east_north_km')
        ll = coordinates(x) if x is not None else None
        error = error_km(ll) if ll is not None else None
        base_error = float(baseline[(case, arm)]['error_km'])
        parent_summary = gates['original_summary']
        rows.append(dict(case=case, arm=arm, branch=branch, status=fit['status'],
            parent_qualified=fit['parent_qualified'], numerical_qualified=fit['numerical_qualified'],
            east_km=x[0] if x is not None else None, north_km=x[1] if x is not None else None,
            latitude=ll[0] if ll is not None else None, longitude=ll[1] if ll is not None else None,
            error_km=error, baseline_error_km=base_error,
            experimental_error_change_vs_baseline_km=error-base_error if error is not None else None,
            original_curved_RMS_hz=parent_summary['RMS_hz'],
            parent_negative_twice_elbo=diagnostics['parent_negative_twice_elbo'],
            target_conditional_NLL=diagnostics['target_conditional']['objective'],
            total_negative_twice_elbo=diagnostics['total_negative_twice_elbo'],
            original_curved_points=diagnostics['original_parent_curved_points'],
            original_predictive_points=diagnostics['original_parent_predictive_points'],
            experimental_predictive_target_points=diagnostics['experimental_predictive_target_points'],
            experimental_likelihood_input_points=diagnostics['original_parent_curved_points']+
                diagnostics['original_parent_predictive_points']+diagnostics['experimental_predictive_target_points'],
            endpoint_compatible_parent_report_IDs_after_target_exclusion=len(gates['endpoint_compatible_IDs_after_target_exclusion']),
            target_accepted_association_points=0, target_association_qualified=False,
            operational_policy='saved_baseline', operational_error_km=base_error,
            scientific_adoption=False, seconds=fit['seconds']))
    assert len(rows) == 8
    csv_new('experimental_endpoints.csv', rows)
    comparison = []
    for case in ('DS24-0095', 'DS24-0087'):
        for arm in ('c0', 'fitted_c'):
            zero = next(row for row in rows if (row['case'], row['arm'], row['branch']) == (case, arm, 'predictive_shape_zero'))
            prior = next(row for row in rows if (row['case'], row['arm'], row['branch']) == (case, arm, 'predictive_shape_prior'))
            selected = {row['saved_control']:row for row in controls if row['case'] == case and row['arm'] == arm}
            separation = float(np.linalg.norm(np.array([zero['east_km'], zero['north_km']])-
                np.array([prior['east_km'], prior['north_km']])))
            comparison.append(dict(case=case, arm=arm,
                baseline_error_km=float(selected['saved_baseline']['error_km']),
                invalid_shape_present_graph_error_km=float(selected['saved_ordinary_shape_present_graph']['error_km']),
                saved_phase_only_support_error_km=float(selected['saved_phase_only_support_control']['error_km']),
                predictive_shape_zero_error_km=zero['error_km'], predictive_shape_prior_error_km=prior['error_km'],
                shape_prior_minus_zero_error_km=prior['error_km']-zero['error_km'],
                shape_prior_minus_baseline_error_km=prior['error_km']-prior['baseline_error_km'],
                between_branch_endpoint_separation_km=separation,
                all_diagnostic_arms_parent_and_numerically_qualified=True,
                new_target_association_qualified=False, operational_policy='saved_baseline',
                operational_error_km=prior['baseline_error_km']))
    csv_new('endpoint_comparison.csv', comparison)
    summary = dict(status='complete', source_sha256=sha(Path(__file__)),
        RF_seal_sha256=sha(seal_path), independent_terminal_audit_sha256=sha(ROOT/'audit/terminal_audit.json'),
        independent_math_terminal_audit_sha256=sha(ROOT/'math_audit/terminal03_audit.json'),
        evaluation_reference=SITE, geographic_distance='same6371km-radiusgreat-circle as R1; regional coordinate mapping unchanged',
        no_new_fits_or_selection=True, previously_exposed_same_site_development=True,
        operational_policy='saved_baseline', target_association_qualified=False,
        comparisons=comparison, experimental_endpoint_rows=len(rows), saved_control_rows=len(controls),
        limitation='Only two new predictive branches isolate shape covariance. Saved controls change evidence role/prior conditioning. No target identity/orbit truth or new-location efficacy is established.')
    with (HERE/'summary.json').open('x') as stream:
        json.dump(summary, stream, indent=2); stream.write('\n')
    with (HERE/'seal.json').open('x') as stream:
        json.dump(dict(files={str(path.relative_to(ROOT)):sha(path) for path in sorted(HERE.glob('*')) if path.is_file() and path.name != 'seal.json'}), stream, indent=2); stream.write('\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
