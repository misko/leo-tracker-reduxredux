"""All-ID descriptive report from terminal correction/replay arrays only."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
PRIOR=Path('/srv/bulk/leo/research/ds24-detector-response-r01')
OUT=HERE/'report'


def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def table(p,rows):
    with Path(p).open('w',newline='')as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    if OUT.exists():raise FileExistsError('preserve original report')
    for p,h in load(HERE/'RF_seal.json')['files'].items():assert sha(p)==h,p
    OUT.mkdir()
    result=load(HERE/'corrections.json');requests={r['native_observation_id']:r for r in load(HERE/'requests.json')}
    records={r['request_id']:r for i in range(2)for r in load(HERE/f'worker{i}.json').get('records',[])}
    previous={r['request_id']:r for r in load(PRIOR/'recorded/results.json')['records']}
    rows=[];parity=[]
    for r in result['rows']:
        q=requests[r['native_observation_id']]
        record=previous[q['reused_prior_request_id']]if q['reused_prior_request_id']else records.get(q['request_id'],{})
        f=record.get('refinement',{})
        row=dict(r,receiver=q['probe']['receiver_id']+1,channel=q['probe']['channel'],
            old_acquired_cfo_hz=f.get('acquired_cfo_hz'),old_residual_cfo_hz=f.get('old_residual_cfo_hz'),
            exact_boundary=f.get('exact',{}).get('boundary'),control_boundary=f.get('control',{}).get('boundary'),
            old_exact_score=f.get('old_exact_score'),new_exact_score=f.get('corrected_exact_score'),
            old_control_score=f.get('old_control_score'),new_control_score=f.get('corrected_control_score'),
            old_margin=(f['old_exact_score']-f['old_control_score'])if f else None,new_margin=f.get('corrected_margin'),
            exact_reference_difference_hz=f.get('exact',{}).get('reference_frequency_difference_hz'),
            control_reference_difference_hz=f.get('control',{}).get('reference_frequency_difference_hz'))
        rows.append(row)
        p=record.get('candidate_parity',{})
        checked=sum(c['field']=='candidate_rank'for rx in p.values()for c in rx['checks'])
        returned=sum(len(rx['candidates'])for rx in record.get('full_original_replay_result',{}).get('receivers',[]))
        parity.append(dict(native_id=r['native_observation_id'],status=r['status'],reused=r['reused_prior_result'],
            returned_records=returned,archived_complete_fractional_rows_checked=checked,
            compared_float_max_error=max((c.get('error',0)for rx in p.values()for c in rx['checks']),default=None),
            every_archived_candidate_passes=bool(p)and all(rx['all_passed']for rx in p.values())))
    table(OUT/'all159_slots.csv',rows);table(OUT/'candidate_parity.csv',parity)
    owners=[];temporal=[]
    order=list(dict.fromkeys(r['complete_owner']for r in result['rows']))
    for owner in order:
        rr=sorted([r for r in rows if r['complete_owner']==owner],key=lambda r:(r['time_s'],r['native_observation_id']))
        t=np.array([r['time_s']for r in rr]);z=2*(t-t.min())/np.ptp(t)-1
        design=np.polynomial.legendre.legvander(z,2)
        old=np.array([r['original_cfo_hz']for r in rr]);new=np.array([r['corrected_cfo_hz']for r in rr]);delta=new-old
        before=old-design@np.linalg.lstsq(design,old,rcond=None)[0]
        after=new-design@np.linalg.lstsq(design,new,rcond=None)[0]
        dshape=delta-design@np.linalg.lstsq(design,delta,rcond=None)[0]
        owners.append(dict(case=rr[0]['case'],role=rr[0]['role'],owner=owner,points=len(rr),receiver=rr[0]['receiver'],channel=rr[0]['channel'],
            complete_input=all(r['payload_and_parity_complete']for r in rr),qualified_points=sum(r['numerical_frequency_qualified']for r in rr),
            reused=sum(r['reused_prior_result']for r in rr),fallbacks=sum(r['fallback_to_original']for r in rr),
            delta_min_hz=float(delta.min()),delta_max_hz=float(delta.max()),delta_mean_hz=float(delta.mean()),delta_RMS_hz=float(np.sqrt(np.mean(delta**2))),
            old_quadratic_residual_RMS_hz=float(np.sqrt(np.mean(before**2))),new_quadratic_residual_RMS_hz=float(np.sqrt(np.mean(after**2))),
            delta_after_quadratic_RMS_hz=float(np.sqrt(np.mean(dshape**2)))))
        for i,r in enumerate(rr):temporal.append(dict(native_id=r['native_observation_id'],owner=owner,time_s=r['time_s'],
            old_degree2_descriptive_residual_hz=float(before[i]),new_degree2_descriptive_residual_hz=float(after[i]),delta_hz=float(delta[i])))
    table(OUT/'owner_summary.csv',owners);table(OUT/'temporal_descriptive.csv',temporal)
    summary=dict(total_slots=len(rows),coverage_complete=result['coverage_complete'],all_frequency_qualified=result['all_frequency_qualified'],
        original_eight_reused=sum(r['reused_prior_result']for r in rows),new_complete=sum(r['payload_and_parity_complete']and not r['reused_prior_result']for r in rows),
        completed_input=sum(r['payload_and_parity_complete']for r in rows),fallbacks=sum(r['fallback_to_original']for r in rows),
        numerical_frequency_qualified=sum(r['numerical_frequency_qualified']for r in rows),numerical_margin_qualified=sum(r['numerical_margin_qualified']for r in rows),
        new_paired_detector_calls=sum(w.get('paired_detector_calls')or 0 for w in result['workers']),
        cumulative_worker_seconds=result['cumulative_worker_seconds'],returned_records=sum(r['returned_records']for r in parity),
        archived_complete_fractional_rows_checked=sum(r['archived_complete_fractional_rows_checked']for r in parity),
        max_parity_float_error=max((r['compared_float_max_error']or 0 for r in parity),default=None),
        boundary_count=sum(bool(r['exact_boundary']or r['control_boundary'])for r in rows),
        original_residual_zero_count=sum(r['old_residual_cfo_hz']==0 for r in rows),owners=owners,
        descriptive_degree=2,recorded_frequency_truth=False,no_graph_or_position_fit=True)
    dump(OUT/'summary.json',summary)
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    for ax,o in zip(axes.flat,owners):
        rr=sorted([r for r in rows if r['complete_owner']==o['owner']],key=lambda r:r['time_s'])
        fresh=[r for r in rr if not r['reused_prior_result']];reuse=[r for r in rr if r['reused_prior_result']]
        ax.axhline(0,color='.4',lw=.8)
        ax.scatter([r['time_s']for r in fresh],[r['correction_delta_hz']for r in fresh],s=20,color='#D55E00'if o['role']=='target'else'#0072B2',label='New complete-owner replay')
        ax.scatter([r['time_s']for r in reuse],[r['correction_delta_hz']for r in reuse],s=70,marker='*',color='k',label='Exact prior reuse')
        bad=[r for r in rr if r['fallback_to_original']]
        if bad:ax.scatter([r['time_s']for r in bad],[0]*len(bad),marker='x',s=60,color='r',label='Original CFO fallback')
        ax.set(title=f"{o['case']} {o['role']}: RX{o['receiver']} CH{o['channel']}, n={o['points']}",xlabel='Original scan midpoint time (s)',ylabel='Applied native CFO change (Hz)')
        ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Complete fixed accepted owners: local continuous CFO changes\nNo frequency truth, graph refit, alias change or position evaluation in this branch',fontsize=12)
    fig.savefig(OUT/'complete_owner_changes.png',dpi=170);fig.savefig(OUT/'complete_owner_changes.pdf');plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    for ax,o in zip(axes.flat,owners):
        rr=sorted([r for r in temporal if r['owner']==o['owner']],key=lambda r:r['time_s'])
        ax.scatter([r['time_s']for r in rr],[r['old_degree2_descriptive_residual_hz']for r in rr],s=25,color='.5',label='Original CFO')
        ax.scatter([r['time_s']for r in rr],[r['new_degree2_descriptive_residual_hz']for r in rr],s=18,color='#D55E00'if o['role']=='target'else'#0072B2',label='Refined/fallback CFO')
        ax.set(title=f"{o['case']} {o['role']}: RMS {o['old_quadratic_residual_RMS_hz']:.1f} → {o['new_quadratic_residual_RMS_hz']:.1f} Hz",xlabel='Original scan midpoint time (s)',ylabel='Descriptive quadratic residual (Hz)')
        ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('All-point degree-2 descriptions before and after refinement\nSeparate unweighted fits on the same native IDs; smaller RMS is not physical accuracy',fontsize=12)
    fig.savefig(OUT/'descriptive_structure.png',dpi=170);fig.savefig(OUT/'descriptive_structure.pdf');plt.close(fig)
    dump(OUT/'seal.json',dict(source_sha256=sha(__file__),RF_seal_sha256=sha(HERE/'RF_seal.json'),
        files={str(p.relative_to(HERE)):sha(p)for p in sorted(OUT.iterdir())if p.is_file()}))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
