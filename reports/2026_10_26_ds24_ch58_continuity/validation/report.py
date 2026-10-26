"""Compact publication summary and static scientific figure; no geographic truth."""

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE/name).read_text())


def main():
    base=read('baseline_audit.json');natural=read('revisit_audit.json')
    frequency=read('frequency_audit.json');extra=read('supplemental_audit.json')
    decision=read('qualification.json')
    # Fixed-endpoint replay has no geographic result; show frequency fit separately.
    fig,axes=plt.subplots(1,3,figsize=(13,4.1),layout='constrained')
    ax=axes[0];labels=['Requested\ncells','Usable\nhistory','Two-half\nsupport','Admitted\npoints']
    ax.bar(labels,[96,natural['eligible_cells'],0,0],color=['.65','#4c78a8','#e45756','#e45756'])
    ax.set_ylim(0,105);ax.set_ylabel('Receiver cells / native points')
    ax.set_title('Natural RF prerequisite')
    for i,v in enumerate([96,natural['eligible_cells'],0,0]):
        ax.text(i,v+2,str(v),ha='center',fontsize=10)
    ax=axes[1];x=np.arange(4)
    for shift,arm,label,color in [(-.15,'c0','c = 0','#4c78a8'),(.15,'fitted_c','Fitted c','#f58518')]:
        ax.bar(x+shift,[r['arms'][arm]['RMS_hz'] for r in base['rows']],width=.3,label=label,color=color)
    ax.set_xticks(x,[r['case'][-4:] for r in base['rows']]);ax.set_xlabel('DS24 scan')
    ax.set_ylabel('Curved frequency RMS (Hz)');ax.set_title('Unchanged baseline endpoint replay')
    ax.set_ylim(0,105);ax.legend(frameon=False,fontsize=9)
    ax=axes[2];methods=frequency['strong_unbiased_nonzero_evolution']['methods']
    labels=['Final bin','Donor carry','Proposal']
    values=[methods[m]['median_absolute_error_hz'] for m in ('unchanged','carry','proposal')]
    ax.bar(labels,values,color=['.65','#f58518','#4c78a8'])
    ax.set_ylabel('Median absolute CFO error (Hz)')
    ax.set_title('Strong synthetic evolution control')
    for i,v in enumerate(values):
        ax.text(i,v+12,f'{v:.0f}',ha='center',fontsize=10)
    ax.set_ylim(0,820)
    fig.suptitle('No natural candidate qualifies for position propagation',fontsize=13)
    fig.text(.5,-.10,'Synthetic control: 16 independent targets, unbiased donor, zero-rate forecast, ±2000 Hz/s evolution.\n'
        'Baseline plots show archived-model replay, with no new regional inference or geographic accuracy result.',
        ha='center',fontsize=9)
    for ext in ('png','pdf'):
        fig.savefig(HERE/f'validation_summary.{ext}',dpi=180,bbox_inches='tight')
    plt.close(fig)
    summary=dict(decision=decision['decision'],protocol_sha256=decision['protocol_sha256'],
        baseline_algorithm='ALGO02-v1 + qualified causal signed phase prior + equal-prior family cavity',
        baseline_cases=4,replayed_c_arms=8,objective_replay_differences=[
            r['arms'][a]['objective_replay_difference'] for r in base['rows'] for a in ('c0','fitted_c')],
        new_regional_inference=False,geographic_accuracy_evaluated=False,
        matched_c_inputs=True,natural_requested_cells=96,natural_eligible_cells=natural['eligible_cells'],
        natural_supported_modes=natural['supported_modes_by_variant'],
        admitted_corrections=0,admitted_new_native_detections=0,
        target_role_counts={a:{role:sum(t['baseline_roles'][a]==role for t in natural['target_bindings'])
            for role in ('curved','predictive','postfit_only','unowned_existing','no_existing_winner')}
            for a in ('c0','fitted_c')},
        eligible_targets_all_have_no_existing_winner=all(not t['existing_baseline_winner']
            for t in natural['target_bindings'] if t['has_three_visit_forecast']),
        natural_packet_mapping_checks=extra['natural_packets_checked'],
        synthetic_stratum=dict(definition='strong, donor error 0, zero-rate forecast, nonzero evolution',
            independent_targets=16,accurate_proposals_100hz=14,
            slope_definition='through-origin regression of proposal-minus-carry against truth-minus-carry including within-window midpoint evolution',
            slope=frequency['evolution_slope'],methods=frequency['strong_unbiased_nonzero_evolution']['methods']),
        interval_reporting_sensitivity=extra['intervals'],
        uncertainty_qualified=False,null_exposure=frequency['conditional_synthetic_nulls'],
        blockers=decision['blockers'],limits=decision['limits'],
        local_only_large_packets={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
            for name in [f'DS24-{i:04d}_baseline.json' for i in range(10,14)]})
    if (HERE/'summary.json').exists():
        if read('summary.json')!=summary:
            raise ValueError('refuse to replace different scientific summary')
    else:
        with (HERE/'summary.json').open('x') as stream:
            json.dump(summary,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(decision=summary['decision'],figures=['validation_summary.png','validation_summary.pdf'])))


if __name__=='__main__':
    main()
