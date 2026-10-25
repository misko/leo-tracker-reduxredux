"""Freeze causal inputs and deleted-prior projections; never fit positions.

This receipt explicitly blocks first-order Gaussian phase propagation because
the independent physical phase check found material nonlinear error.
"""

from pathlib import Path

import numpy as np

import adapter as a
import recovery as r
from ds23_height_problem import geometry_features


def project_original(d, arm, saved, node, keep, means):
    dd = dict(d, node=node, keep=np.asarray(keep, bool), means=np.asarray(means))
    p = r.build(dd, arm, saved['phase_reference'])
    x = np.asarray(saved['endpoint_east_north_km'])
    g = geometry_features(p, x, 0.)
    j = d['target']['candidate_index']
    k = d['target']['row_index']
    sl = p.slices[k]
    start = p.hardware.shape[1]+p.smooth.shape[1]
    phase = g['features'][sl, start+p.labels.index(j)]
    b0 = start+len(p.labels)+3*p.supported.index(j)
    b = g['features'][sl, b0:b0+3]
    return dict(position_east_north_km=x,
                phase_reference_s=p.reference[p.labels.index(j)],
                point_noise_median_hz=float(np.median(p.point_noise[sl])),
                **a.shape_projection(b, phase))


def run():
    out = a.HERE/'preparation01'
    sources = [a.HERE/'adapter.py', a.HERE/'test_adapter.py', Path(__file__),
               r.HERE/'recovery.py', r.HERE/'repair01.py', r.HERE/'eligibility02.py']
    sources += [r.REPO/'tools'/name for name in (
        'ds23_predictive_linear.py', 'ds23_frequency_events.py',
        'ds23_height_problem.py', 'dsx01_joint_marginal.py',
        'dsx01_hierarchical_bound.py', 'build_dsx01_orbit_modes.py',
        'probe_ds23_history_calibrated_phase.py', 'ds23_active_mode_support.py')]
    bindings, projections = {}, {}
    for case in a.CASES:
        d = a.load_context(case)
        graph_path = r.HERE/case/'graph/result.json'
        graph = r.read(graph_path)['trials'][d['saved_support']['source_graph_trial']]
        support = d['saved_support']
        target = d['target']; t = d['target_track']
        k = target['row_index']; sl = d['base'].slices[k]
        by_id = {o['observation_id']:o for o in d['observations']}
        physical = [by_id[i] for i in target['observation_ids']]
        bindings[case] = dict(target=target, parent_node=d['node'],
            original_mask=d['keep'], parent_predictive_entries=d['entries'],
            powers=d['powers'], causal_phase_means=d['means'], model=d['model'],
            target_times_s=t['times'], target_graph_values_hz=t['values'],
            target_alias_values_hz=np.asarray(t['values'])+target['alias']*a.PERIOD,
            target_native_observations=physical, target_original_point_noise_hz=d['base'].point_noise[sl],
            target_element=d['scan'].elements[str(target['norad'])],
            causal_cutoff_utc_ns=d['scan'].receipt['cutoff_utc_ns'],
            phase_prior_is_Student_with_declared_unit_marginal_variance=True,
            new_predictive_noise='original predictive sigma from fixed_window_noise, unseen Gamma E[1/tau]=2, no power or target Gamma fitting',
            target_constant_prior_sd_hz=300.,
            original_target_power=float(d['powers'][k]),
            source_hashes={str(path):r.sha(path) for path in (
                graph_path, r.HERE/'eligibility02'/case/'result.json',
                r.HERE/case/'parent.json', r.SOURCE/'family_cavity/position'/(case+'.json'),
                r.SOURCE/case/'observations.json', r.SOURCE/case/'tracks.json',
                a.STUDY/'audit'/(case+'_target_binding.json'))})
        projections[case] = {}
        for arm in a.ARMS:
            records = {}
            records['baseline_endpoint'] = project_original(d, arm, d['arms'][arm],
                d['node'], d['keep'], d['means'])
            records['invalid_full_shape_graph_endpoint'] = project_original(d, arm, graph['arms'][arm],
                graph['node'], graph['mask'], graph['means'])
            records['phase_only_support_endpoint'] = project_original(d, arm, support['arms'][arm],
                graph['node'], graph['mask'], graph['means'])
            projections[case][arm] = records
    r.write_new(out/'input_bindings.json', bindings)
    r.write_new(out/'deleted_prior_projections.json', projections)
    receipt = dict(status='preparation_only_first_order_phase_not_released',
        position_fits=0, no_GPS=True,
        coordinator_plan_sha256=r.sha(a.STUDY/'COORDINATOR_PLAN.md'),
        source_sha256={str(p):r.sha(p) for p in sources},
        input_sha256=r.sha(out/'input_bindings.json'),
        deleted_prior_projections_sha256=r.sha(out/'deleted_prior_projections.json'),
        first_order_phase_material_limitation=True,
        independent_phase_audit_sha256=r.sha(a.STUDY/'math_audit/phase_linearization.json'),
        fit_launch_authorized=False,
        target_association_gate='none newly calibrated; all endpoints remain unqualified diagnostics, saved baseline operational',
        parent_gates='all original curved/predictive/residual/visibility/support gates unchanged',
        next_requirement='versioned exact phase marginalization amendment and independent preflight')
    r.write_new(out/'preparation_seal.json', receipt)
    print(str(out/'preparation_seal.json'))


if __name__ == '__main__':
    run()
