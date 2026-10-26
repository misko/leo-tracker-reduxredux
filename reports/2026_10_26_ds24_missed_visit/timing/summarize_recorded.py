"""Offline paired natural diagnostics and candidate handoff; no inference runs."""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def save(fig,name):
    fig.savefig(HERE/(name+'.png'),dpi=170,bbox_inches='tight')
    fig.savefig(HERE/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
def passed(item,kind='admitted'):return bool(item and item['evaluation'][kind])


def counts(cells):
    return dict(n=len(cells),original=sum(c['original_pass'] for c in cells),
        point=sum(c['point_admitted'] for c in cells),search=sum(c['search_admitted'] for c in cells),
        point_pilot=sum(c['point_pilot'] for c in cells),search_pilot=sum(c['search_pilot'] for c in cells),
        search_new_original_absent=sum(c['search_admitted'] and not c['original_pass'] for c in cells),
        point_new_original_absent=sum(c['point_admitted'] and not c['original_pass'] for c in cells),
        search_gain_over_point=sum(c['search_admitted'] and not c['point_admitted'] for c in cells),
        search_loss_vs_point=sum(c['point_admitted'] and not c['search_admitted'] for c in cells),
        alternate_pilot=sum(c['search_pilot'] and not c['search_admitted'] for c in cells),
        no_donor=sum(c['status']=='no_donor' for c in cells))


def main():
    protocol=read(HERE/'protocol.json');all_rows=[];execution=[];failure_rows=[];files=[]
    for case in protocol['development']:
        path=HERE/'outcomes'/(case+'.json.gz');files.append(path)
        if not path.exists():raise ValueError('missing shard; retain denominator before finalization: '+case)
        value=read(path);all_rows.extend(value['rows'])
        execution.append(dict(case=case,seconds=value['seconds'],windows=len(value['rows']),
            complete_windows=sum(r['status']=='complete' for r in value['rows'])))
    cells=[];candidates=[];oracle_rows=[]
    for row in all_rows:
        if row['status']!='complete':failure_rows.append(dict(request_id=row['request_id'],error=row.get('error'),completed_cells=len(row['cells'])))
        for cell in row['cells']:
            r=cell['result'];packet=cell['packet'];original=cell['original_fullwindow'];primary=packet['modes'][0] if packet['modes'] else None
            original_pass=any(c['passed_fractional_margin_gate'] for c in original.get('candidates',[]))
            point=r.get('point');search=r.get('search');h=packet['header']
            c=dict(request_id=row['request_id'],prediction_id=cell['prediction_id'],case=row['case'],
                channel=row['channel'],receiver_id=cell['receiver_id'],owner_id=r['owner_id'],status=r['status'],
                original_pass=original_pass,point_admitted=passed(point),search_admitted=passed(search),
                point_pilot=passed(point,'pilot_confirmed'),search_pilot=passed(search,'pilot_confirmed'),
                modes=len(packet['modes']),exposure=len(r['exposure']),
                selected_mode=search['selected']['mode_index'] if search else '',
                selected_offset_samples=search['selected']['score']['offset_samples'] if search else '',
                point_cfo_hz=point['confirmation'].get('tracking_cfo_hz','') if point else '',
                search_cfo_hz=search['confirmation'].get('tracking_cfo_hz','') if search else '',
                point_margin=point['confirmation'].get('margin','') if point else '',
                search_margin=search['confirmation'].get('margin','') if search else '',
                nomination_margin=search['selected']['score'].get('margin','') if search else '',
                search_frames=search['selected']['score']['frames'] if search else '',
                confirmation_frames=search['confirmation']['frames'] if search else '',
                any_timing_width_capped=any(m['timing_half_width_samples']>256 for m in packet['modes']))
            c['capped_modes']=sum(m['timing_half_width_samples']>256 for m in packet['modes'])
            c['selected_timing_width_samples']=packet['modes'][search['selected']['mode_index']]['timing_half_width_samples'] if search else ''
            c['selected_CFO_half_width_hz']=packet['modes'][search['selected']['mode_index']]['cfo_half_width_hz'] if search else ''
            cells.append(c)
            if search:
                mode=packet['modes'][search['selected']['mode_index']]
                if c['search_pilot']:
                    candidates.append(dict(prediction_id=cell['prediction_id'],owner_id=r['owner_id'],
                        case=row['case'],channel=row['channel'],receiver_id=cell['receiver_id'],
                        visit_index=h['visit_index'],probe_index=h['probe_index'],actual_rf_hz=h['actual_rf_hz'],edge=h['edge'],
                        target_support=packet['target_support'],native_confirmation_blocks=search['native_confirmation_blocks'],
                        native_search_blocks=search['native_search_blocks'],
                        block_coordinate_system='native sample offsets relative to target_support.start_counter; interpolation guards included',
                        confirmation_native_support=[dict(start_counter=packet['target_support']['start_counter']+b['sample_start'],
                            stop_counter=packet['target_support']['start_counter']+b['sample_stop'],
                            generation=packet['target_support']['native_generation']) for b in search['native_confirmation_blocks']],
                        selected_mode=mode,selected_offset_samples=c['selected_offset_samples'],
                        nomination=search['selected']['score'],confirmation=search['confirmation'],
                        support_class='donor_continuity_compatible' if c['search_admitted'] else 'alternate_pilot_discovery',
                        original_pass=original_pass,action='alternative_on_existing_owner' if original_pass else 'newly_confirmed_native_owner',
                        selection_receipt_sha256=r['selection_receipt']['selection_sha256'],
                        no_automatic_replacement=True,provisional_only=True,uncertainty_weights_qualified=False,
                        donor_conditioning_is_not_new_data=True))
            oracle=cell['oracle']
            if oracle['status']=='complete':
                entry=dict(prediction_id=cell['prediction_id'],channel=row['channel'],receiver_id=cell['receiver_id'],
                    all_frame_parity=oracle['public_all_frame_parity'])
                for group,score in oracle['groups'].items():
                    entry[group+'_status']=score['status'];entry[group+'_frames']=score['frames']
                    entry[group+'_margin']=score.get('margin')
                    entry[group+'_pass']=score.get('margin') is not None and score['margin']>=.025
                oracle_rows.append(entry)
    if len(all_rows)!=288:raise ValueError('requested raw window denominator not preserved')
    observed_owners={c['owner_id'] for c in cells};requested=576
    by_channel={str(ch):counts([c for c in cells if c['channel']==ch]) for ch in [1,4,5,6,7,8]}
    by_channel_rx={f'CH{ch}/RX{rx}':counts([c for c in cells if c['channel']==ch and c['receiver_id']==rx]) for ch in [1,4,5,6,7,8] for rx in [0,1]}
    power=dict(n=len(oracle_rows),full_pass=sum(o['all_pass'] for o in oracle_rows),
        search_group_pass=sum(o['search_pass'] for o in oracle_rows),confirmation_group_pass=sum(o['confirmation_pass'] for o in oracle_rows),
        full_pass_confirmation_fail=sum(o['all_pass'] and not o['confirmation_pass'] for o in oracle_rows),
        confirmation_insufficient_frames=sum(o['confirmation_status']!='complete' for o in oracle_rows),
        every_public_full_parity=all(o['all_frame_parity'] for o in oracle_rows))
    total_seconds=sum(r['seconds'] for r in execution)
    parity_seconds=sum(r.get('public_source_parity',{}).get('parity_detector_seconds',0.) for r in all_rows)
    summary=dict(schema='missed-visit-development-timing-summary/v1',requested_windows=288,requested_cells=requested,
        observed_windows=len(all_rows),observed_cells=len(cells),missing_cells=requested-len(cells),
        unique_native_owners=len(observed_owners),counts=counts(cells),by_channel=by_channel,
        CH5_8=counts([c for c in cells if c['channel']>=5]),by_channel_receiver=by_channel_rx,
        oracle_power_control=power,failed_windows=failure_rows,execution=execution,
        full_native_source_parity=all(r.get('public_source_parity',{}).get('full_reader_exhausted',False) for r in all_rows if r['status']=='complete'),
        timing_width_capped_cells=sum(c['any_timing_width_capped'] for c in cells),
        timing_width_capped_modes=sum(c['capped_modes'] for c in cells),
        selected_mode_width_capped=sum(bool(c['selected_timing_width_samples']!='' and c['selected_timing_width_samples']>256) for c in cells),
        runtime_decomposition=dict(sum_independent_shard_seconds=total_seconds,
            measured_old_production_GLRT_parity_seconds=parity_seconds,
            remaining_combined_seconds=total_seconds-parity_seconds,
            native_read_verify_seconds=None,new_timing_scoring_seconds=None,
            note='Inherited parity timer includes detector, candidate comparison and background materialization; remaining time combines raw reading/verification, frozen-source checks, new scoring, oracle diagnostics, and checkpoint/output writes. Separate native/new-scoring timers were not recorded; no fabricated split.'),
        total_search_scores=sum(c['exposure'] for c in cells),mode_cap=8,timing_bank_half_width_samples=256,
        independent_added_Doppler_points=0,ready_for_coherence_review=True,ready_for_position=False,
        protocol_sha256=sha(HERE/'protocol.json'),source_hashes={f.name:sha(f) for f in files})
    write(HERE/'recorded_summary.json',summary)
    for name,rows in [('recorded_cells.csv',cells),('oracle_power.csv',oracle_rows)]:
        if not rows:continue
        with (HERE/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write(HERE/'candidate_manifest.json',dict(schema='timing-development-candidates/v1',
        candidates=candidates,provisional=True,ready_for_position=False,
        no_new_independent_points_admitted=True,source_protocol_sha256=sha(HERE/'protocol.json'),
        retained_native_owner_count=len(observed_owners),no_validation_outcomes=True))
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    controls=read(HERE/'control_summary.json');methods=['point','search'];colors=['#777777','#246b99']
    fig,axes=plt.subplots(1,3,figsize=(13,3.6))
    for j,db in enumerate([-12,-18,-24]):
        for k,m in enumerate(methods):
            stats=controls['by_strength'][str(db)][m]
            axes[0].bar(j+(k-.5)*.3,stats['admitted'],width=.28,color=colors[k],label=m if j==0 else None)
    axes[0].set_xticks(range(3),['-12dB','-18dB','-24dB']);axes[0].set(ylabel='Admitted /80 per strength',ylim=(0,85),title='Known-truth timing controls');axes[0].legend()
    offsets=sorted(set(c['timing_offset_samples'] for c in read(HERE/'outcomes/signal.json.gz')['rows']))
    for k,m in enumerate(methods):
        sr=read(HERE/'outcomes/signal.json.gz')['rows'];rates=[]
        for offset in offsets:
            sub=[r for r in sr if r['db']==-12 and r['timing_offset_samples']==offset]
            rates.append(sum(r['evaluation'][m].get('accurate500',False) for r in sub)/len(sub))
        axes[1].plot(offsets,rates,'o-',label=m,color=colors[k])
    axes[1].set(xlabel='Initial timing error (native samples)',ylabel='Strong CFO within500Hz fraction',ylim=(-.03,1.05),title='Offset and frozen bank boundary');axes[1].legend()
    nullstrata=controls['null_strata'];axes[2].bar(range(4),[100*x['methods']['search']['confirmed_upper95'] for x in nullstrata],color='#8a77a7')
    axes[2].set_xticks(range(4),[f"{x['edge']}\n{x['modes']} mode" for x in nullstrata]);axes[2].set(ylabel='One-sided95% conditional FAR bound (%)',title='Full search selection,32draws per stratum')
    fig.tight_layout();save(fig,'known_controls_and_nulls')

    fig,axes=plt.subplots(1,2,figsize=(12,4))
    channels=[1,4,5,6,7,8];colors3=['#a34e45','#777777','#246b99']
    for j,m in enumerate(['original','point','search']):
        axes[0].bar(np.arange(6)+(j-1)*.23,[by_channel[str(ch)][m] for ch in channels],width=.22,color=colors3[j],label=m)
    axes[0].set_xticks(range(6),[f'CH{ch}' for ch in channels]);axes[0].set(ylabel='Native receiver-window marks /96 per channel',title='Same physical target panel; original uses full20ms');axes[0].legend()
    gains=[by_channel[str(ch)]['search_gain_over_point'] for ch in channels];losses=[by_channel[str(ch)]['search_loss_vs_point'] for ch in channels]
    axes[1].bar(np.arange(6)-.16,gains,width=.3,color='#246b99',label='Search gains over point')
    axes[1].bar(np.arange(6)+.16,losses,width=.3,color='#a34e45',label='Search losses vs point')
    axes[1].set_xticks(range(6),[f'CH{ch}' for ch in channels]);axes[1].set(ylabel='Paired target transitions',title='Matched earlier modes and confirmation partition');axes[1].legend()
    fig.tight_layout();save(fig,'natural_paired_channel_results')

    fig,axes=plt.subplots(1,3,figsize=(13,3.8))
    axes[0].bar(range(3),[power['full_pass'],power['search_group_pass'],power['confirmation_group_pass']],color=colors3)
    axes[0].set_xticks(range(3),['Full20ms','Search frames','Confirm frames'],rotation=15)
    axes[0].set(ylabel='Archived-anchor positive controls',title=f"Evaluation-only timing, n={power['n']}")
    complete=[o for o in oracle_rows if o['confirmation_margin'] is not None and o['all_margin'] is not None]
    axes[1].scatter([o['all_margin'] for o in complete],[o['confirmation_margin'] for o in complete],s=12,alpha=.5)
    axes[1].axhline(.025,color='#a34e45',ls='--');axes[1].axvline(.025,color='#a34e45',ls='--')
    axes[1].set(xlabel='Full20ms archived-anchor margin',ylabel='Confirmation-group margin',title='Separate split power from timing failure')
    selected=[c['selected_offset_samples'] for c in cells if c['search_admitted']]
    axes[2].hist(selected,bins=np.arange(-264,265,16),color='#246b99')
    axes[2].axvline(-256,color='#a34e45',ls='--');axes[2].axvline(256,color='#a34e45',ls='--')
    axes[2].set(xlabel='Selected timing correction (samples)',ylabel='Continuity-compatible confirmations',title='Frozen +/-256domain; every boundary retained')
    fig.tight_layout();save(fig,'oracle_power_and_timing_domain')
    print(json.dumps(dict(counts=summary['counts'],CH5_8=summary['CH5_8'],oracle=power,
        failures=len(failure_rows),seconds=[x['seconds'] for x in execution]),indent=2),flush=True)


if __name__=='__main__':main()
