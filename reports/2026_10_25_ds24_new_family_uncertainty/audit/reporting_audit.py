"""Independent saved-artifact reporting checks; no inference or propagation."""

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / 'evaluation'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def rows(name):
    with (EVAL / name).open() as stream:
        return list(csv.DictReader(stream))


def sphere_distance(a, b):
    # Unit-vector atan2 oracle, independent of reporter's haversine formula.
    def unit(p):
        lat, lon = map(math.radians, p)
        return (math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat))
    u, v = unit(a), unit(b)
    cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    return 6371*math.atan2(math.sqrt(sum(x*x for x in cross)), sum(x*y for x, y in zip(u, v)))


def main():
    rf = ROOT/'scientific/RF_seal03.json'
    for name, digest in read(rf)['files'].items():
        assert sha(name) == digest, name
    for name, field in [('audit/terminal_audit.json', 'status'), ('math_audit/terminal03_audit.json', 'all_passed')]:
        data = read(ROOT/name)
        assert data[field] == ('passed' if field == 'status' else True)
        assert data['RF_seal_sha256'] == sha(rf)
    summary = read(EVAL/'summary.json')
    site = summary['evaluation_reference']
    experimental = rows('experimental_endpoints.csv')
    controls = rows('saved_controls.csv')
    comparison = rows('endpoint_comparison.csv')
    assert (len(experimental), len(controls), len(comparison)) == (8, 12, 4)
    with (ROOT/'audit/saved_control_reference.csv').open() as stream:
        assert controls == list(csv.DictReader(stream))
    control_receipt = read(ROOT/'audit/saved_control_reference_receipt.json')
    for name, digest in control_receipt['inputs'].items():
        assert sha(name) == digest, name
    baseline = {(v['case'], v['arm']):float(v['error_km']) for v in controls if v['saved_control'] == 'saved_baseline'}
    max_error_difference, max_native_identity = 0., 0.
    native_point_checks = 0
    for row in experimental:
        directory = ROOT/'scientific/fits03'/row['case']/row['arm']/row['branch']
        gates = read(directory/'parent_gates.json')
        diag = read(directory/'rf_diagnostics.json')
        ll = gates['original_summary']['endpoint_latlon']
        assert abs(float(row['latitude'])-ll[0]) < 1e-12
        assert abs(float(row['longitude'])-ll[1]) < 1e-12
        difference = abs(sphere_distance(ll, site)-float(row['error_km']))
        max_error_difference = max(max_error_difference, difference)
        assert difference < 1e-8
        assert row['target_association_qualified'] == row['scientific_adoption'] == 'False'
        assert row['operational_policy'] == 'saved_baseline'
        assert int(row['target_accepted_association_points']) == 0
        assert float(row['operational_error_km']) == baseline[(row['case'], row['arm'])]
        assert int(row['experimental_likelihood_input_points']) == sum(int(row[k]) for k in
            ('original_curved_points', 'original_predictive_points', 'experimental_predictive_target_points'))
        target = read(ROOT/'audit'/(row['case']+'_target_binding.json'))
        assert diag['target_observation_ids'] == target['observation_ids']
        assert len(set(target['observation_ids'])) == len(target['times_s'])
        for native, base, orbit, residual in zip(target['native_measured_cfo_hz'], diag['target_base_raw_hz'],
                diag['target_phase_marginal_mean_orbit_hz'],
                diag['target_phase_marginal_mean_residual_hz'], strict=True):
            # Verify the plotted native-gauge mean with source values/alias offset.
            # It deliberately omits target-local constant/shape posterior means.
            plotted = native-residual
            # base_raw already subtracts parent radio and E-conditional means.
            expected = native-base+orbit
            delta = abs(plotted-expected)
            max_native_identity = max(max_native_identity, delta)
            assert delta < 1e-7
            native_point_checks += 1
    component_rows = rows('profile_component_changes.csv')
    assert len(component_rows) == 8
    max_component_closure = 0.
    for row in component_rows:
        subtotal = sum(float(row[k]) for k in ('parent_change', 'target_quadratic_change', 'target_logdet_change',
            'target_normalization_change', 'phase_KL_change'))
        difference = abs(subtotal-float(row['total_change']))
        max_component_closure = max(max_component_closure, difference)
        assert difference < 1e-8
    for row in comparison:
        arms = {x['branch']:x for x in experimental if x['case'] == row['case'] and x['arm'] == row['arm']}
        zero, prior = (arms[k] for k in ('predictive_shape_zero', 'predictive_shape_prior'))
        assert abs(float(row['shape_prior_minus_zero_error_km'])-(float(prior['error_km'])-float(zero['error_km']))) < 1e-12
        assert abs(float(row['between_branch_endpoint_separation_km'])-math.hypot(
            float(prior['east_km'])-float(zero['east_km']), float(prior['north_km'])-float(zero['north_km']))) < 1e-12
    figure_receipt = read(EVAL/'figure_receipt.json')
    assert len(figure_receipt['figures']) == 14
    for name, digest in figure_receipt['figures'].items():
        assert sha(ROOT/name) == digest, name
    inventory = read(ROOT/'next_inventory/inventory.json')
    assert inventory['fully_bound_raw_transfer_candidate_count'] == 0
    assert inventory['provisional_rejected_graph_binding_count'] == 97
    receipt = dict(all_passed=True, source_sha256=sha(__file__), no_fits_or_propagation=True,
        RF_seal_sha256=sha(rf), experimental_rows=8, saved_control_rows=12, comparison_rows=4,
        independently_checked_native_plot_points=native_point_checks,
        max_geographic_error_formula_difference_km=max_error_difference,
        max_native_CFO_identity_difference_hz=max_native_identity,
        max_profile_component_closure=max_component_closure,
        verified_figure_files=14, ready_transfer_candidates=0, provisional_graph_bindings=97,
        all_target_associations_unqualified=True, all_operational_outputs_saved_baseline=True,
        physical_covariance_scope='All three physical modes together; no attribution to orthogonal curvature alone.',
        plotted_residual_scope='Before target-local constant/shape mean adjustments; descriptive, not full-fit RMS or held-out prediction.')
    destination = EVAL/'reporting_audit.json'
    destination.write_text(json.dumps(receipt, indent=2)+'\n')
    files = {str(path.relative_to(ROOT)):sha(path) for path in sorted(EVAL.iterdir()) if path.is_file() and path.name != 'reporting_seal.json'}
    (EVAL/'reporting_seal.json').write_text(json.dumps(dict(files=files,
        figures=figure_receipt['figures'], RF_seal_sha256=sha(rf)), indent=2)+'\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
