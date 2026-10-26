"""Saved-artifact reporting only; no path refit, detector or RF analysis."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
OUT=HERE/'report'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def write(p,rows):
    with Path(p).open('w',newline='') as s:
        w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    if OUT.exists():raise FileExistsError('preserve prior report')
    for path,h in load(HERE/'RF_seal.json')['files'].items():
        assert sha(path)==h,path
    OUT.mkdir();summary=load(HERE/'summary.json');owners=load(HERE/'owners.json')
    with (HERE/'all_candidate_rows.csv').open() as s:
        rows=list(csv.DictReader(s))
    dedup=[r for r in rows if r['dedup_retained']=='True']
    write(OUT/'deduplicated_candidates.csv',dedup)
    near=[r for r in dedup if r['nearby_alternative']=='True']
    owner_rows=[]
    for owner in owners:
        times=sorted({float(r['time_s']) for r in near if r['original_owner']==owner['owner']})
        runs=[];current=[]
        for t in times:
            if current and t-current[-1]>2:runs.append(current);current=[]
            current.append(t)
        if current:runs.append(current)
        support=any(len(run)>=5 and run[-1]-run[0]>=3 for run in runs)
        category='insufficient_flagged_windows' if len(times)<5 else 'no_time_supported_five_window_run' if not support else 'paired_linear_rule_not_satisfied'
        r={k:owner[k] for k in ('owner','receiver','channel','start_s','end_s','original_points','quality_status','pointwise_flagged_windows','nearby_alternative_rows','status','persistent','control_eligible')}
        r.update(maximum_time_connected_flagged_windows=max(map(len,runs),default=0),
            time_supported_five_window_run=support,limiting_category=category)
        owner_rows.append(r)
    write(OUT/'owner_support.csv',owner_rows)
    counts={key:sum(r['limiting_category']==key for r in owner_rows) for key in ('insufficient_flagged_windows','no_time_supported_five_window_run','paired_linear_rule_not_satisfied')}
    details=dict(summary,necessary_support_counts=counts,
        necessary_time_support_passing_owners=sum(r['time_supported_five_window_run'] for r in owner_rows),
        paired_rule_not_satisfied_is_not_physical_adequacy_test=True,
        all_gatepassing_deduplicated_rows=len(dedup),not_searched_for_paths_outside_previous_nearby_class=True,
        public_complete_deduplicated_row_port='deduplicated_candidates.csv')
    dump(OUT/'summary.json',details)
    counts_image=np.zeros((2,8),int);total_image=np.zeros((2,8),int)
    for r in owner_rows:
        counts_image[r['receiver']-1,r['channel']-1]+=r['pointwise_flagged_windows']
        total_image[r['receiver']-1,r['channel']-1]+=r['original_points']
    fig,axes=plt.subplots(2,1,figsize=(11.5,7),gridspec_kw={'height_ratios':[1,1.5]},constrained_layout=True)
    im=axes[0].imshow(np.divide(counts_image,total_image,out=np.zeros_like(counts_image,dtype=float),where=total_image>0)*100,
        aspect='auto',cmap='Blues',vmin=0,vmax=100)
    for rx in range(2):
        for ch in range(8):axes[0].text(ch,rx,f'{counts_image[rx,ch]}/{total_image[rx,ch]}',ha='center',va='center',fontsize=9)
    axes[0].set_yticks([0,1],['RX1','RX2']);axes[0].set_xticks(range(8),[f'CH{i+1}' for i in range(8)])
    axes[0].set_title('Nearby flags / native winners owned by original graph tracks')
    fig.colorbar(im,ax=axes[0],label='Flagged (%)',pad=.02)
    labels=['Fewer than 5\nflagged windows','No qualifying\ntime-connected run','Time support passes;\npaired line rule fails']
    vals=list(counts.values());axes[1].barh(labels,vals,color=['#999999','#E69F00','#0072B2'])
    for i,v in enumerate(vals):axes[1].text(v+.5,i,str(v),va='center')
    axes[1].set_xlim(0,max(vals)+10);axes[1].set_xlabel('Original graph owners (all 117 retained)');axes[1].invert_yaxis();axes[1].grid(axis='x',alpha=.2)
    axes[1].set_title('Necessary support and final frozen-rule outcomes; no threshold scan')
    fig.suptitle('Pointwise alternatives do not establish persistent branches\nZero of 117 owners pass this frozen nearby-alternative rule',fontsize=13)
    fig.savefig(OUT/'persistence_inventory.png',dpi=170);fig.savefig(OUT/'persistence_inventory.pdf');plt.close(fig)

    selected=load(HERE/'control_port.json');windows=selected['windows'];fs=selected['sample_rate_hz'];period=fs/750
    fig,axes=plt.subplots(3,1,figsize=(11,8),constrained_layout=True)
    for w in windows:
        for r in w['candidates']:
            color='#0072B2' if r['original_winner'] else '#D55E00'
            axes[0].scatter(w['time_s'],r['cfo_hz'],s=20,color=color)
            axes[1].scatter(w['time_s'],r['global_epoch_samples'],s=20,color=color)
            axes[2].scatter(w['time_s'],r['local_epoch_samples'],s=20,color=color)
    axes[0].set_ylabel('Raw fractional CFO (Hz)');axes[1].set_ylabel('Counter-corrected phase\n(samples modulo fs/750)');axes[2].set_ylabel('Local epoch (samples)')
    for ax in axes:ax.grid(alpha=.2)
    axes[1].set_ylim(0,period);axes[2].set_ylim(0,period);axes[2].set_xlabel('Scan midpoint time (s)')
    axes[0].set_title('Blue: original maximum-margin winner; orange: other gated deduplicated candidate')
    fig.suptitle('Frozen unflagged control: DS24-0011 RX2 CH5 T003\nComplete original owner; no positive branch substituted',fontsize=13)
    fig.savefig(OUT/'unflagged_control.png',dpi=170);fig.savefig(OUT/'unflagged_control.pdf');plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(11,4.2),constrained_layout=True)
    axes[0].hist([abs(float(r['winner_CFO_gap_Hz'])) for r in near],bins=30,color='#0072B2')
    axes[0].set_xlabel('Absolute circular CFO gap from winner (Hz)');axes[0].set_ylabel('Exported nearby alternatives');axes[0].axvline(250,color='.4',ls='--',label='Frozen dedup/proximity boundary');axes[0].legend(fontsize=8)
    axes[1].hist([float(r['winner_epoch_gap_samples']) for r in near],bins=30,color='#D55E00')
    axes[1].set_xlabel('Same-window circular epoch gap (samples)');axes[1].set_ylabel('Exported nearby alternatives')
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle('All 501 nearby proposals remain detector hypotheses\nClose refinements may describe one signal; no independent-emitter claim',fontsize=12)
    fig.savefig(OUT/'nearby_candidate_gaps.png',dpi=170);fig.savefig(OUT/'nearby_candidate_gaps.pdf');plt.close(fig)
    dump(OUT/'seal.json',dict(source_sha256=sha(Path(__file__)),RF_seal_sha256=sha(HERE/'RF_seal.json'),
        saved_metadata_reporting_only=True,no_new_path_search=True,files={str(q.relative_to(HERE)):sha(q) for q in sorted(OUT.iterdir()) if q.is_file()}))
    print(json.dumps(dict(support_counts=counts,necessary_support_passing=details['necessary_time_support_passing_owners'],public_dedup_rows=len(dedup))))


if __name__=='__main__':main()
