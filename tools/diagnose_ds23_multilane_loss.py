"""Report-only loss decomposition at surveyed and RF-selected positions.

The evaluation coordinate is confined to this diagnostic. It is never passed
to candidate generation, production position inference or prior selection.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

import probe_ds23_multilane_position as predictive
import probe_ds23_joint_multilane_position as joint
from probe_ds23_multilane_confirmation import BULK as CONFIRMATION
from prototype_dsx01_continuous_position import CENTER, latlon
from report_algo02_ds23 import REFERENCE
from run_algo01_ds23_sample import ROOT, read, write

OUT = ROOT/'reports/2026_10_20_ds23_multilane_loss_diagnosis_v2'


def reference_xy():
    x = np.array([(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])), (REFERENCE[0]-CENTER[0])*111.])
    np.testing.assert_allclose(latlon(x), REFERENCE, rtol=0, atol=1e-12)
    return x


def fixed(d, arm, extra, position, reference):
    for _ in range(6):
        p = joint.make(d, arm, reference, extra, True)
        phase = np.clip(p.state(position)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase-reference))); reference = phase
    c = p.calculate(position)
    old_groups = p.noise_groups[p.keep]
    old_data = float(np.sum(d['powers'][old_groups]*c['noise_precision'][old_groups]*(c['conditional_residual_hz'][p.keep]/p.point_noise[p.keep])**2))
    new_data = 0.; curves = []
    for k, (entry, sl) in enumerate(zip(p.joint_secondary_entries, p.joint_secondary_slices, strict=True)):
        r = c['joint_secondary_fitted_residual_hz'][sl]
        cov = d['covariance'][entry['component']]; sigma = cov['conditional_sigma_hz']
        contribution = float(p.joint_conditional_powers[k]*c['joint_secondary_noise_precision'][k]*np.sum((r/sigma)**2))
        new_data += contribution
        curves.append(dict(component=entry['component'], norad=entry['norad'], weighted_data=contribution,
                           conditional_RMS_hz=float(np.sqrt(np.mean(r*r))), declared_sigma_hz=sigma))
    prior = float(np.sum(c['latent_coefficient']**2*c['coefficient_prior_precision']))
    calibration = p.curved_calculate(position) if p.linear_entries else c
    terms = dict(original_data=old_data, added_curved_data=new_data, coefficient_prior=prior,
                 logvolume=float(c['logvolume']), noise_Gamma=float(c['noise_gamma_cost']),
                 prior_Gamma=float(c['prior_gamma_cost']), calibration_normalization=float(calibration['normalization_constant']),
                 original_and_added_linear_prediction=float(c['negative_twice_elbo']-calibration['negative_twice_elbo']))
    reconstructed = sum(terms.values())
    if abs(reconstructed-c['negative_twice_elbo']) > 1e-5:
        raise ValueError('independent objective-component reconstruction failed')
    nb, ns, nf = p.hardware.shape[1], p.smooth.shape[1], len(p.labels)
    phase_begin = nb+ns; orbit_begin = phase_begin+nf; bias_begin = orbit_begin+3*len(p.supported)
    penalty = c['latent_coefficient']**2*c['coefficient_prior_precision']
    blocks = dict(receiver_offsets=float(penalty[:4].sum()), receiver_rates=float(penalty[4:8].sum()),
        fitted_c=float(penalty[8]) if nb == 9 else 0., receiver_smooth=float(penalty[nb:phase_begin].sum()),
        satellite_phase=float(penalty[phase_begin:orbit_begin].sum()),
        physical_orbit_modes=float(penalty[orbit_begin:bias_begin].sum()),
        original_fragment_bias=float(penalty[bias_begin:bias_begin+len(p.members)].sum()),
        added_fragment_bias=float(penalty[bias_begin+len(p.members):].sum()))
    if abs(sum(blocks.values())-prior) > 1e-8:
        raise ValueError('physical prior block decomposition failed')
    families = [dict(norad=int(p.scan.norads[j]), phase_penalty=float(penalty[phase_begin+k]),
                     orbit_penalty=float(penalty[orbit_begin+3*p.supported.index(j):orbit_begin+3*p.supported.index(j)+3].sum()) if j in p.supported else 0.)
                for k, j in enumerate(p.labels)]
    return dict(position=position, final_phase_change_s=change, loss=float(c['negative_twice_elbo']), terms=terms,
                prior_blocks=blocks, prior_families=families,
                curves=curves, phase_s=p.state(position)['phases'][p.labels],
                phase_prior_mean_s=d['means'], phase_prior_sigma_s=p.phase_sigma)


def run(case):
    bulk = predictive.BULK if case == 'DS23-0202' else CONFIRMATION
    predictive.BULK, predictive.OUT = bulk, bulk/'position'
    joint.PREVIOUS, joint.OUT = bulk/'position', bulk/'joint_position'
    d = predictive.prepare_inputs(case); saved = read(joint.OUT/(case+'.json'))
    extra = saved['extra_entries']; records = []
    for arm in ('c0', 'fitted_c'):
        fitted = saved['results']['joint_shared_all_lanes']['arms'][arm]
        initial_reference = np.asarray(fitted['phase_reference'])
        positions = [('surveyed_report_only', reference_xy()),
                     ('new_RF_mode', np.asarray(fitted['endpoint_east_north_km'])),
                     ('incumbent_RF_mode', np.asarray(d['signed']['policy_arms'][arm]['endpoint_east_north_km']))]
        local = {name: fixed(d, arm, extra, x, initial_reference.copy()) for name, x in positions}
        record = dict(case=case, arm=arm, positions=local,
                      truth_minus_new_mode_loss=local['surveyed_report_only']['loss']-local['new_RF_mode']['loss'],
                      incumbent_minus_new_mode_loss=local['incumbent_RF_mode']['loss']-local['new_RF_mode']['loss'])
        records.append(record)
    write(OUT/(case+'.json'), dict(rows=records, evaluation_coordinate_used_only_for_this_diagnostic=True,
          no_inference_or_prior_change=True, no_GPS_based_satellite_selection=True))
    return records


def main():
    OUT.mkdir(exist_ok=True); cases = ['DS23-0202', 'DS23-0293', 'DS23-0240', 'DS23-0112', 'DS23-0114']
    with ProcessPoolExecutor(max_workers=5) as pool:
        rows = [r for f in as_completed([pool.submit(run, c) for c in cases]) for r in f.result()]
    write(OUT/'evaluation.json', dict(rows=rows, report_only=True, not_a_position_algorithm=True))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    chosen = [r for r in rows if r['arm'] == 'fitted_c']
    for k, r in enumerate(sorted(chosen, key=lambda r: r['case'])):
        before = r['positions']['new_RF_mode']['terms']; after = r['positions']['surveyed_report_only']['terms']
        fields = ['original_data', 'added_curved_data', 'coefficient_prior', 'logvolume', 'noise_Gamma', 'prior_Gamma', 'original_and_added_linear_prediction']
        delta = np.array([after[f]-before[f] for f in fields])
        axes[0].plot(np.arange(len(fields)), delta, '.-', label=r['case'])
        axes[1].bar(k, r['truth_minus_new_mode_loss']); axes[1].text(k, r['truth_minus_new_mode_loss'], r['case'].split('-')[1], ha='center', va='bottom', fontsize=8)
    axes[0].set(xticks=np.arange(len(fields)), xticklabels=['Old data','New curved\ndata','Coefficient\nprior','Log-volume','Noise Gamma','Prior Gamma','Predictive\nblock'], ylabel='Loss at surveyed site minus new RF mode')
    axes[0].tick_params(axis='x', labelrotation=15); axes[0].legend(fontsize=7)
    axes[1].set(xticks=[], ylabel='Full loss: surveyed site minus new RF mode', title='Positive: model favors displaced RF mode')
    for a in axes:
        a.axhline(0, color='k', lw=.6); a.grid(axis='y', alpha=.2)
    fig.suptitle('Fixed-position diagnostic after nuisance/phase refresh · fitted c\nSurveyed coordinates used only here, never in inference; exact component sums checked in both c arms')
    fig.savefig(OUT/'loss_decomposition.png', dpi=160); plt.close(fig)
    print('FIXED_POSITION_DIAGNOSIS', [(r['case'], r['arm'], r['truth_minus_new_mode_loss'], r['incumbent_minus_new_mode_loss']) for r in rows], flush=True)


if __name__ == '__main__':
    main()
