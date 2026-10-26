"""Compact independent round1 summary/figures and additions-only manifest."""

import collections
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from baseline_scope import sha

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as stream:return json.load(stream)


def write(name,value):
    with (HERE/name).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def main():
    cases=read(ROOT/'split.json')['development'];totals=collections.Counter();by_channel=collections.defaultdict(collections.Counter)
    rows=[];admissions=[];source={};oracle=collections.Counter();curved_owners=set()
    for case in cases:
        ledger_path=HERE/(case+'_additions.json');ledger=read(ledger_path);source[str(ledger_path)]=sha(ledger_path)
        totals.update(ledger['counts']);totals['missing_receiver_cells']+=ledger['missing_receiver_cells']
        admissions.extend(dict(a,case=case) for a in ledger['staged'])
        graph_path=HERE/(case+'-additions-r01')/'graph_audit.json'
        graph=read(graph_path) if graph_path.exists() else None
        if graph:
            source[str(graph_path)]=sha(graph_path)
            curved=set(graph['graph']['curved_observation_ids'])
            curved_owners|={a['target_observation_id'] for a in ledger['staged'] if a['target_observation_id'] in curved}
        else:curved=set()
        for target in ledger['all_target_outcomes']:
            if 'channel' not in target:continue
            ch=str(target['channel']);by_channel[ch]['requested']+=1
            by_channel[ch]['pilot_confirmed']+=target.get('pilot_confirmed',False)
            by_channel[ch]['admitted']+=target.get('admitted',False)
            by_channel[ch]['new_native']+=target['status']=='new_native_exploratory_addition'
            by_channel[ch]['new_curved_graph']+=target['status']=='new_native_exploratory_addition' and target['target_observation_id'] in curved
        raw_path=ROOT/'timing/outcomes'/(case+'.json.gz');source[str(raw_path)]=sha(raw_path)
        for window in read(raw_path)['rows']:
            for cell in window['cells']:
                o=cell['oracle'];oracle['cells']+=1;oracle[o['status']]+=1
                if o['status']=='complete':
                    oracle['full_public_parity']+=o['public_all_frame_parity']
                    for group in ('all','search','confirmation'):
                        oracle[group+'_passed']+=o['groups'][group]['status']=='complete' and o['groups'][group]['margin']>=.025
                    oracle['full_pass_split_confirmation_fail']+=o['groups']['all']['margin']>=.025 and not(
                        o['groups']['confirmation']['status']=='complete' and o['groups']['confirmation']['margin']>=.025)
        rows.append(dict(case=case,new_native=ledger['new_native_detections'],
            point_admitted=ledger['counts'].get('point_admitted',0),search_admitted=ledger['counts'].get('search_admitted',0),
            new_graph_points=graph['new_in_graph'] if graph else 0,new_curved_graph=graph['new_in_curved_graph'] if graph else 0,
            new_unassociated=graph['new_unassociated'] if graph else 0,
            bank_reuse_allowed=graph['bank_support']['reuse_allowed'] if graph else None,
            incumbent_noise_sigma_shift_range_hz=graph['incumbent_noise_sigma_shift_range_hz'] if graph else [0.,0.],
            original_rows_preserved=ledger['original_measurements_and_margins_exactly_preserved']))
    assert len(rows)==12 and totals['receiver_cells_seen']==576
    assert len(admissions)==len({a['target_observation_id'] for a in admissions})==30
    info=read(HERE/'frequency_information_12cases.json')
    assert info['natural_new_native']==30
    summary=dict(schema='missed-visit-round1-independent-summary-v1',development_cases=12,
        requested_paired_windows=288,requested_receiver_cells=576,counts=dict(totals),
        new_native_owners=len(admissions),new_curved_graph_owners=len(curved_owners),
        new_CH58_native=sum(a['channel']>=5 for a in admissions),
        new_CH58_curved_graph=sum(a['channel']>=5 and a['target_observation_id'] in curved_owners for a in admissions),
        new_control_native=sum(a['channel'] in (1,4) for a in admissions),
        by_channel={k:dict(v) for k,v in by_channel.items()},by_case=rows,oracle=dict(oracle),
        natural_zero_residual_bins=info['natural_zero_bins'],FFT_bin_spacing_hz=info['FFT_bin_spacing_hz'],
        strong_frequency_information=info['strong_by_forecast'],
        corrections=0,all_existing_rows_and_margins_preserved=True,
        new_causal_association_runs=0,new_regional_position_runs=0,geographic_accuracy_claim=False,
        held_validation_target_outcomes_opened=False,qualified_promotion=False,
        exploratory_regional_proposal='POSITION_EXECUTION_PROPOSAL.md',
        bottlenecks=['Only a sparse fraction of new pilots enter curved graph evidence.',
            'Donor-centered443.89Hzbin selection does not establish independent fine frequency errors.',
            'Causal catalogue association and matched fresh regional sensitivity have not yet run.'],
        source_hashes=source)
    write('round1_summary.json',summary)
    write('candidate_manifest.json',dict(schema='missed-visit-round1-exploratory-additions-v1',
        candidates=admissions,new_native_owners=len(admissions),new_curved_graph_owners=len(curved_owners),
        corrected_existing=0,owner_IDs_unique=True,original_rows_preserved=True,
        ordering_evidence='audited immutable source order and durable callback, not invented wall-clock events',
        regionally_qualified=False,position_execution_authorized=False,promotion_authorized=False,
        summary_sha256=sha(HERE/'round1_summary.json')))
    fig,axes=plt.subplots(1,3,figsize=(13.5,4.2),layout='constrained')
    labels=['Forecast','Pilot','Admitted','New','Curved']
    values=[453,totals['search_pilot_confirmed'],totals['search_admitted'],len(admissions),len(curved_owners)]
    axes[0].bar(labels,values,color=['.65','#4c78a8','#4c78a8','#f58518','#e45756'])
    axes[0].set_title('New raw support reaches sparse curvature');axes[0].set_ylabel('Native receiver-cell owners / 576')
    for i,v in enumerate(values):axes[0].text(i,v+8,str(v),ha='center',fontsize=9)
    axes[0].set_ylim(0,510)
    x=np.arange(12)
    axes[1].bar(x,[r['new_native'] for r in rows],label='New native',color='#f58518')
    axes[1].bar(x,[r['new_curved_graph'] for r in rows],label='New in curved graph',color='#4c78a8')
    axes[1].set_xticks(x,[r['case'][-4:] for r in rows],rotation=60)
    axes[1].set_ylabel('Distinct additions');axes[1].set_title('Twelve development recordings');axes[1].legend(frameon=False,fontsize=8)
    x=np.arange(2)
    for offset,key,color in [(-.18,'before_mean_absolute_error_hz','.65'),(.18,'after_mean_absolute_error_hz','#4c78a8')]:
        axes[2].bar(x+offset,[info['strong_by_forecast'][f][key] for f in ('zero_rate_fallback','rate_propagated')],width=.35,
            color=color,label='Earlier prediction' if offset<0 else 'Later FFT output')
    axes[2].set_xticks(x,['Unpredicted\nevolution','Correct-rate\nmechanism'])
    axes[2].set_ylabel('Strong mean absolute CFO error (Hz)');axes[2].set_title('Frequency information differs by prior');axes[2].legend(frameon=False,fontsize=8)
    fig.suptitle('Round1: 30 new native pilot detections, limited new position evidence')
    fig.text(.5,-.085,'Original measurements preserved. Curved graph membership is not causal satellite association.\n'
        '443.89Hzdonor-centered FFT bins and correlated donor information require explicit position-weight sensitivity.',ha='center',fontsize=9)
    for ext in ('png','pdf'):fig.savefig(HERE/f'round1_summary.{ext}',dpi=180,bbox_inches='tight')
    plt.close(fig)
    print(json.dumps({k:summary[k] for k in ('new_native_owners','new_curved_graph_owners','new_CH58_native',
        'new_CH58_curved_graph','new_control_native','natural_zero_residual_bins','oracle')},indent=2))


if __name__=='__main__':main()
