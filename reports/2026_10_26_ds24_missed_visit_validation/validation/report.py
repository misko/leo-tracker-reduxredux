"""Independent final-prototype development figure and compact evidence summary."""
import collections
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def read(name):return json.loads((HERE/name).read_text())


def main():
    recorded=read('recorded_audit.json');manifest=read('candidate_manifest.json');graph=read('graph_audit.json')
    candidates=manifest['candidates'];graph_ids={oid for r in graph['cases'] for oid in r['new_curved_ids']}
    donor_counts=dict(collections.Counter(str(len(c['donors'])) for c in candidates))
    identities=[dict(prediction_id=c['prediction_id'],native_observation_id=c['target_observation_id'],
        channel=c['native']['channel'],receiver=c['native']['native_receiver_id'],
        donor_count=len(c['donors']),innovation_hz=c['frequency_innovation_hz'],
        new_curved_graph=c['target_observation_id'] in graph_ids) for c in candidates]
    summary=dict(schema='round2-independent-development-summary-v1',requested_receiver_cells=576,
        counts=recorded['counts'],by_prediction_status=recorded['by_prediction_status'],
        new_native=len(candidates),new_zero_bin=sum(c['frequency_innovation_hz']==0 for c in candidates),
        new_donor_count_distribution=donor_counts,new_curved_graph=graph['new_curved'],
        new_CH58=sum(c['native']['channel']>=5 for c in candidates),
        new_CH58_curved=sum(c['native']['channel']>=5 and c['target_observation_id'] in graph_ids for c in candidates),
        new_CH58_curved_with_nonzero_innovation=sum(c['native']['channel']>=5 and c['target_observation_id'] in graph_ids and c['frequency_innovation_hz']!=0 for c in candidates),
        identities=identities,new_position_runs=0,held_validation_outcomes_opened=False,geographic_claim=False,
        primary_method='single quadratic/fallback full-window point',companion_union_used=False,
        frequency_precision_qualified=False,reader_seconds=recorded['reader_seconds'],scoring_seconds=recorded['scoring_seconds'])
    with (HERE/'summary.json').open('x') as stream:json.dump(summary,stream,indent=2,allow_nan=False);stream.write('\n')
    fig,axes=plt.subplots(1,3,figsize=(13,4.1),layout='constrained')
    labels=['Consistent\nlinear','Quadratic /\nfallback','Legacy adapter\ncontrol'];prefixes=['linear','quadratic_or_fallback','legacy_adapter_linear'];x=np.arange(3)
    axes[0].bar(x,[recorded['counts'][m+'_admitted'] for m in prefixes],color=['.65','#4c78a8','.8'])
    axes[0].set_xticks(x,labels);axes[0].set_ylabel('Admitted native target owners / 576');axes[0].set_title('Curvature restores primary pilot support')
    for i,m in enumerate(prefixes):axes[0].text(i,recorded['counts'][m+'_admitted']+3,str(recorded['counts'][m+'_admitted']),ha='center')
    axes[0].set_ylim(0,160)
    axes[1].bar(['New native','New curved\ngraph','CH5–8curved','CH5–8curved\nwith innovation'],
        [9,graph['new_curved'],summary['new_CH58_curved'],summary['new_CH58_curved_with_nonzero_innovation']],color=['#f58518','#4c78a8','#4c78a8','#e45756'])
    axes[1].set_ylabel('Distinct newly present owners');axes[1].set_title('New frequency evidence remains limited')
    axes[1].set_ylim(0,10)
    axes[2].bar(['All admitted','NEW owners'],[recorded['counts']['quadratic_or_fallback_zero_bin_admitted']/recorded['counts']['quadratic_or_fallback_admitted'],summary['new_zero_bin']/9],color=['#4c78a8','#f58518'])
    axes[2].set_ylim(0,1);axes[2].set_ylabel('Fraction with zero residual FFT bin');axes[2].set_title('Donor-centered grid origin still matters')
    axes[2].text(0,.93,'125/141',ha='center');axes[2].text(1,.82,'7/9',ha='center')
    fig.suptitle('Final timing prototype: more support, sparse new Doppler information')
    fig.text(.5,-.085,'Same primary donors/CFO, one full-window point per method. Legacy reference is descriptive; no target-selected union.\n'
        'Zero-bin output supports a conditional frequency interval; it does not establish independent fine precision or position gain.',ha='center',fontsize=9)
    for ext in ('png','pdf'):fig.savefig(HERE/f'validation_summary.{ext}',dpi=180,bbox_inches='tight')
    plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
