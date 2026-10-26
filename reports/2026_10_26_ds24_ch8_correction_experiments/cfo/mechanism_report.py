"""RF-only saved-outcome diagnostics for continuous-CFO and channel attribution."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prepare import HERE,load,sha,write


def main():
    for seal in ('RF_seal.json','position/RF_seal.json','channel_RF_seal.json'):
        for path,digest in load(HERE/seal)['files'].items():
            assert sha(path)==digest,'sealed artifact changed '+path
    out=HERE/'mechanism';out.mkdir(exist_ok=True)
    owners=load(HERE/'nomination_manifest.json')['owners'];packets=load(HERE/'position/packets.json')
    primary=[row for case in load(HERE/'position/execution.json')['results'] for row in case['rows']]
    channel=[row for case in load(HERE/'channel_execution.json')['results'] for row in case['rows']]
    rows=primary+channel;contrasts=[];precisions=[]
    for b in rows:
        if b['method']=='original':
            continue
        a=next(r for r in primary if r['case']==b['case'] and r['kind']==b['kind'] and r['arm']==b['arm'] and r['method']=='original')
        if a['status']!='complete' or b['status']!='complete':
            contrasts.append(dict(case=b['case'],arm=b['arm'],kind=b['kind'],method=b['method'],status='failed'));continue
        delta=np.asarray(b['endpoint_east_north_km'])-a['endpoint_east_north_km']
        record=dict(case=b['case'],arm=b['arm'],kind=b['kind'],method=b['method'],status='complete',
            endpoint_movement_east_north_m=(delta*1000).tolist(),endpoint_movement_m=float(np.linalg.norm(delta)*1000),
            objective_difference=b['objective']-a['objective'],conditional_RMS_difference_hz=b['conditional_RMS_hz']-a['conditional_RMS_hz'],
            fitted_likelihood_and_residual_gates_pass=b['single_arm_valid'],Gamma_converged=b['Gamma_converged'],
            postfit_only_IDs_lost=b['postfit_IDs_lost'],fixed_likelihood_IDs_unchanged=True,
            final_phase_change_s=b['final_phase_change_s'],maximum_unclipped_phase_s=b['maximum_unclipped_phase_s'])
        contrasts.append(record)
        old=load(HERE/'position'/a['case']/a['kind']/a['method']/a['arm']/'raw_endpoint.json')
        new=load(HERE/'position'/b['case']/b['kind']/b['method']/b['arm']/'raw_endpoint.json')
        aa=np.array(old['noise_precision']);bb=np.array(new['noise_precision']);mask=aa>0
        record['Gamma_precision_ratio_min_median_max']=[float(np.min(bb[mask]/aa[mask])),float(np.median(bb[mask]/aa[mask])),float(np.max(bb[mask]/aa[mask]))]
        if b['method']=='refined':
            members=packets[b['case']+'_'+b['arm']]['layout']['members']
            for owner in (o for o in owners if o['case']==b['case']):
                index=members.index(owner['track_index'])
                precisions.append(dict(case=b['case'],arm=b['arm'],kind=b['kind'],owner=owner['owner'],
                    noise_precision_original=float(aa[index]),noise_precision_refined=float(bb[index]),ratio=float(bb[index]/aa[index])))
    records={}
    for path in sorted(HERE.glob('*_worker*.jsonl')):
        for line in path.read_text().splitlines():
            try:
                value=json.loads(line)
            except json.JSONDecodeError:
                continue
            for row in value.get('records',[]):
                records[row['request_id']]=row
    requests={r['request_id']:r for r in load(HERE/'requests.json')};score=[]
    for channel in (7,8):
        rr=[r['refinement'] for rid,r in records.items() if requests[rid]['probe']['channel']==channel]
        improvements=np.array([r['exact']['score_improvement'] for r in rr]);margin=np.array([r['refinement']['corrected_margin']-requests[rid]['original_candidate']['fractional_margin'] for rid,r in records.items() if requests[rid]['probe']['channel']==channel])
        score.append(dict(channel=channel,points=len(rr),exact_score_improvement_min_mean_max=list(map(float,[improvements.min(),improvements.mean(),improvements.max()])),
            margin_change_min_mean_max=list(map(float,[margin.min(),margin.mean(),margin.max()])),
            numerical_margin_unqualified=sum(not r['numerical_margin_qualified'] for r in rr),
            original_residual_CFO_zero_count=sum(r['old_residual_cfo_hz']==0 for r in rr),
            corrected_margin_below_original_gate_count=sum(r['corrected_margin']<.025 for r in rr),original_gate_always_preserved=True))
    summary=dict(contrasts=contrasts,selected_owner_precisions=precisions,score=score,GPS_used=False,
        objective_changes_compare_different_observed_data_not_Bayes_factors=True,
        fixed_packet_vs_VI_difference_includes_precision_feedback_and_model_objective_difference=True,
        global_regional_search=False,ordinary_original_endpoint_replays_exact=all(r.get('original_endpoint_difference_km')==0 for r in primary if r['method']=='original' and r['kind']=='ordinary_VI'),
        fits=24,primary_worker_seconds=load(HERE/'position/execution.json')['cumulative_worker_seconds'],channel_worker_seconds=load(HERE/'channel_execution.json')['cumulative_worker_seconds'])
    write(out/'summary.json',summary)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    for case,marker in [('DS24-0010','o'),('DS24-0011','s')]:
        for arm,color in [('c0','#176b8b'),('fitted_c','#b76b25')]:
            for c in contrasts:
                if c['case']!=case or c['arm']!=arm or c['kind']!='ordinary_VI' or c['status']!='complete':
                    continue
                x,y=c['endpoint_movement_east_north_m'];axes[0].scatter(x,y,marker=marker,color=color)
                axes[0].annotate(case[-4:]+' '+arm+' '+c['method'],(x,y),fontsize=7,xytext=(3,3),textcoords='offset points')
    axes[0].axhline(0,color='.7',lw=.7);axes[0].axvline(0,color='.7',lw=.7);axes[0].set_xlabel('Endpoint movement east (m)');axes[0].set_ylabel('Endpoint movement north (m)');axes[0].set_title('Ordinary VI; movement is not accuracy')
    oo=[p for p in precisions if p['kind']=='ordinary_VI']
    for arm,color in [('c0','#176b8b'),('fitted_c','#b76b25')]:
        pp=[p for p in oo if p['arm']==arm];axes[1].plot([p['ratio'] for p in pp],range(len(pp)),'.',color=color,label=arm)
    pp=[p for p in oo if p['arm']=='c0'];axes[1].set_yticks(range(len(pp)),[p['owner'].replace('DS24-','').split('-RF')[0] for p in pp],fontsize=8);axes[1].axvline(1,color='.6',lw=.8);axes[1].set_xlabel('Refined / original Gamma noise precision');axes[1].legend();axes[1].set_title('Selected complete owners; full delta vector')
    fig.savefig(out/'RF_mechanism.png',dpi=180);plt.close(fig)
    paths=[Path(__file__),out/'summary.json',out/'RF_mechanism.png']
    write(out/'seal.json',dict(files={str(p):sha(p) for p in paths},GPS_used=False))
    print(json.dumps(dict(score=score,primary_worker_seconds=summary['primary_worker_seconds'],channel_worker_seconds=summary['channel_worker_seconds']),indent=2))


if __name__=='__main__':
    main()
