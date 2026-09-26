"""Summarize real pilot evidence and conditional tracking transfer."""
from pathlib import Path
from collections import defaultdict
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from phase_factor import predictive_evidence,update_candidates

HERE=Path(__file__).resolve().parent
def wrap(x):return np.angle(np.exp(1j*np.asarray(x)))
def mean_phase(y):return float(np.angle(np.mean(np.exp(1j*np.asarray(y)))))
def rms(y):return float(np.degrees(np.sqrt(np.mean(wrap(y)**2))))

def main():
    plan=json.loads((HERE/'plan.json').read_text());summaries=[];transfer=[];returns=[];allrows=[]
    fig,axes=plt.subplots(3,3,figsize=(14,10),constrained_layout=True)
    for scan_index,scan in enumerate(plan['scans']):
        sid=scan['session_id'];data=json.loads((HERE/(sid+'.json')).read_text());rows=data['rows'];allrows.extend(rows)
        errors=[wrap(r['coefficients']['held']['phase_rad']-r['coefficients']['train']['phase_rad']) for r in rows]
        nullerrors=[wrap(r['controls']['held']['phase_rad']-r['controls']['train']['phase_rad']) for r in rows]
        ratios=[min(r['held_exact_control_ratios']) for r in rows]
        groups=defaultdict(dict)
        for r in rows:groups[r['visit'],r['start_ms']][r['mode']]=r
        dv=defaultdict(list)
        for (visit,start),pair in groups.items():
            if len(pair)==2:dv[visit].append(pair)
        for visit,pairs in dv.items():
            pairs.sort(key=lambda p:p[0]['start_ms']);n=len(pairs)
            if n!=6:continue
            rng=np.random.default_rng(plan['seed']+visit+scan_index*10000)
            train=np.zeros(n,bool);train[rng.choice(n,3,replace=False)]=True
            a=np.array([p[0]['coefficients']['full']['phase_rad'] for p in pairs]);b=np.array([p[1]['coefficients']['full']['phase_rad'] for p in pairs])
            for donor,target in ((a,b),(b,a)):
                dd=wrap(target-donor);offset=mean_phase(dd[train]);prediction=donor+offset
                baseline=mean_phase(target[train]);wrong=np.roll(donor,1);wrong+=mean_phase(wrap(target-wrong)[train])
                predicted=np.stack([donor,np.zeros(n),np.roll(donor,1)])
                evidence=predictive_evidence(target,predicted,np.ones(n),train)
                posterior=update_candidates(np.log(np.full(3,1/3)),evidence)
                transfer.append(dict(session_id=sid,visit=visit,donor='mode0' if donor is a else 'mode1',held_window_starts_ms=[pairs[i][0]['start_ms'] for i in np.flatnonzero(~train)],matched_rmse_deg=rms(target[~train]-prediction[~train]),target_constant_rmse_deg=rms(target[~train]-baseline),wrong_time_rmse_deg=rms(target[~train]-wrong[~train]),held_log_evidence=evidence.tolist(),equal_prior_conditional_hypothesis_probabilities=posterior.tolist()))
        recurrent=defaultdict(list)
        for visit,pairs in dv.items():
            if pairs[0][0]['partition'] not in ('train','held'):continue
            a=np.array([p[0]['coefficients']['full']['phase_rad'] for p in pairs]);b=np.array([p[1]['coefficients']['full']['phase_rad'] for p in pairs])
            recurrent[pairs[0][0]['group']].append(dict(visit=visit,partition=pairs[0][0]['partition'],dd_phase=mean_phase(wrap(b-a)),dd_R=float(abs(np.mean(np.exp(1j*(b-a)))))))
        for group,visits in recurrent.items():
            train=[r['dd_phase'] for r in visits if r['partition']=='train'];held=[r['dd_phase'] for r in visits if r['partition']=='held']
            if train and held:returns.append(dict(session_id=sid,group=group,visits=visits,held_constant_dd_rms_deg=rms(np.array(held)-mean_phase(train)),interpretation='constant-DD diagnostic across retunes; real geometry may change, so not satellite identity truth'))
        tr=[r for r in transfer if r['session_id']==sid]
        summary=dict(session_id=sid,time_utc=scan['metadata']['capture_start_utc'],selected_visits=len(scan['selected']),phase_rows=len(rows),errors=data['errors'],joint_eligible_visits=scan['eligible_joint_visits'],two_mode_eligible_visits=scan['eligible_two_mode_visits'],selected_two_mode_visits=len(dv),median_R=float(np.median([r['coefficients']['full']['R'] for r in rows])),median_absolute_support_disagreement_deg=float(np.degrees(np.median(abs(np.array(errors))))),support_disagreement_rms_deg=rms(errors),rolled_control_support_rms_deg=rms(nullerrors),median_min_rx_exact_control_ratio=float(np.median(ratios)),both_rx_held_exact_control_gt2=sum(r>2 for r in ratios),median_matched_transfer_rms_deg=float(np.median([r['matched_rmse_deg'] for r in tr])),median_target_constant_rms_deg=float(np.median([r['target_constant_rmse_deg'] for r in tr])),median_wrong_time_rms_deg=float(np.median([r['wrong_time_rmse_deg'] for r in tr])),matched_better_than_constant=sum(r['matched_rmse_deg']<r['target_constant_rmse_deg'] for r in tr),matched_better_than_wrong_time=sum(r['matched_rmse_deg']<r['wrong_time_rmse_deg'] for r in tr),transfer_directions=len(tr),receiver_offset_hz_range=[min(r['rx1_cfo_hz']-r['rx0_cfo_hz'] for r in rows),max(r['rx1_cfo_hz']-r['rx0_cfo_hz'] for r in rows)])
        summaries.append(summary)
        time=np.array([(r['utc_ns']-rows[0]['utc_ns'])/1e9 for r in rows])
        for channel in sorted({r['channel'] for r in rows}):
            inds=[i for i,r in enumerate(rows) if r['channel']==channel]
            color={1:'tab:blue',2:'tab:orange',3:'tab:green',4:'tab:red'}[channel]
            axes[scan_index,0].scatter(time[inds],[rows[i]['coefficients']['full']['R'] for i in inds],s=12,label=f'CH{channel}',color=color)
            axes[scan_index,1].scatter(time[inds],[np.degrees(rows[i]['coefficients']['full']['phase_rad']) for i in inds],s=12,color=color)
        axes[scan_index,0].legend(fontsize=7);axes[scan_index,0].set_ylabel(scan['metadata']['capture_start_utc'][11:16]+' UTC\ncoherence R')
        axes[scan_index,2].boxplot([[r['matched_rmse_deg'] for r in tr],[r['target_constant_rmse_deg'] for r in tr],[r['wrong_time_rmse_deg'] for r in tr]],tick_labels=['Shared donor','Target only','Wrong time'])
        axes[scan_index,2].set_ylabel('Held-window wrapped RMS (deg)')
        for ax in axes[scan_index,:2]:ax.set_xlabel('Time from first selected midpoint (s)')
        for ax in axes[scan_index]:ax.grid(alpha=.2)
    axes[0,0].set_title('Real pilot coherence, colored by channel');axes[0,1].set_title('Wrapped RX1−RX0 phase (deg)');axes[0,2].set_title('Within-dwell transfer diagnostic')
    fig.suptitle('DS5: three additional scans · bounded phase replay',fontsize=16)
    fig.savefig(HERE/'overview.png',dpi=170);plt.close(fig)
    payload=dict(schema='ds5-phase-integration-summary/v1',scans=summaries,conditional_tracking_transfer=transfer,retuned_pair_returns=returns,interpretation='All comparisons are retrospective signal consistency, not satellite identity truth. kappa=1 is an illustrative fixed phase-factor scale, not calibrated.')
    (HERE/'summary.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(summaries,indent=2))

if __name__=='__main__':main()
