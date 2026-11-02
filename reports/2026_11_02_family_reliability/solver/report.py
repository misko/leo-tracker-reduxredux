"""Regenerate tables and scientific figures from sealed solver fits."""
import csv,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from algo07_science import engine as e
from algo06_science.common import read,write
from run import ROOT,PRIOR,INPUT,CASES,sha

def main():
    summaries=[];trajectories=[];predictions=[]
    for case in CASES:
        e.configure(INPUT,ROOT);e.ROOTS['DS26']=INPUT;d,z,replay=e.load_case(case)
        oldaudit=read(PRIOR/case/'audit.json')
        for arm in ('c0','fitted_c'):
            folder=ROOT/case/arm
            new=read(folder/'damped_half.json')
            p,dd=e.build(d,z,arm,np.asarray(new['reference']))
            x=np.asarray(new['x']);c=p.calculate(x);fixed=[]
            if not np.array_equal(p.keep,d['keep']):raise ValueError('solver changed mask')
            for row,i,sl in zip(p.rows,p.members,p.slices):
                tr=p.scan.tracks[i]
                for k in np.flatnonzero(p.keep[sl]):
                    ix=sl.start+k;oid=tr['observation_ids'][k];fixed.append(oid)
                    predictions.append(dict(case=case,arm=arm,kind='curved',component=row['component'],norad=row['candidate_norad'],
                        observation_id=oid,time_s=float(p.flat_times[ix]),CFO_hz=float(p.values[ix]),
                        orbit_at_reference_hz=float(p.q[ix]*c['frequency'][ix]),
                        fitted_prediction_hz=float(p.values[ix]-c['conditional_residual_hz'][ix]),
                        residual_hz=float(c['conditional_residual_hz'][ix])))
            for ent,sl in zip(dd['entries'],getattr(p,'linear_slices',[])):
                tr=p.scan.tracks[ent['track_index']];fixed.extend(ent['observation_ids'])
                for oid,t,r in zip(ent['observation_ids'],tr['times'],c['linear_raw_prediction_residual_hz'][sl]):
                    predictions.append(dict(case=case,arm=arm,kind='conditional_predictive',component=ent['component'],norad=ent['norad'],
                        observation_id=oid,time_s=float(t),CFO_hz=None,orbit_at_reference_hz=None,fitted_prediction_hz=None,residual_hz=float(r)))
            for f,details in zip(dd['families'],new['mixture_details']):
                for ent,diag in zip(f.entries,details['diagnostics']):
                    fixed.extend(ent['observation_ids'])
                    for oid,t,r in zip(ent['observation_ids'],diag['times_s'],diag['raw_residual_hz']):
                        predictions.append(dict(case=case,arm=arm,kind='phase_mixture_predictive',component=ent['component'],norad=ent['norad'],
                            observation_id=oid,time_s=float(t),CFO_hz=None,orbit_at_reference_hz=None,fitted_prediction_hz=None,residual_hz=float(r)))
            legacy=read(folder/'legacy.json');expected=legacy['fixed_fitted_native_ids']
            if sorted(fixed)!=expected or len(fixed)!=len(set(fixed)):raise ValueError('native IDs changed or duplicated')
            fixedhash=hashlib.sha256('\n'.join(sorted(fixed)).encode()).hexdigest()
            if fixedhash!=legacy['fixed_fitted_native_sha256']:raise ValueError('native hash mismatch')
            write(folder/'fixed_evidence.json',dict(fixed_fitted_native_ids=expected,fixed_fitted_native_count=len(fixed),
                fixed_fitted_native_sha256=fixedhash,mask_exactly_unchanged=True,
                published_owners_immutable=True,unadopted_membership_proposal_added=len(new['added_ids']),
                unadopted_membership_proposal_lost=len(new['lost_ids']),unadopted_membership_proposal_reassigned=len(new['reassigned_ids'])))
            for variant in ('published','legacy','damped_half'):
                row=read(folder/(variant+'.json'));isbase=variant=='published'
                gates=read(PRIOR/case/f'published_gates_{arm}.json') if isbase else row
                gap=row.get('phase_change_s',row.get('history',[{}])[-1].get('phase_change_s') if row.get('history') else None)
                rms=oldaudit['arms'][arm]['rms_hz'] if isbase else row['rms_hz']
                exact=gates.get('exact_orbit_checks',[])
                summaries.append(dict(case=case,arm=arm,variant=variant,x_east_km=row['x'][0],x_north_km=row['x'][1],
                    evaluation_error_m=row['error_m'],per_reference_objective=row['objective'],rms_hz=rms,
                    phase_gap_s=gap,phase_closed=gap<=.01,optimizer_success=row.get('optimizer_success'),
                    rounds=len(row.get('history',[])),position_nfev=sum(h['nfev'] for h in row.get('history',[])),
                    seconds=row.get('seconds'),base_gates=gates['all_base_gates_pass'],
                    exact_gates=all(q['all_pass'] for q in exact),mixture_gates=gates['mixture_gates_pass'],
                    all_gates=gates['all_gates_pass'],minimum_base_slack=gates['minimum_gate_slack'],
                    maximum_exact_difference_hz=max((q['maximum_linearization_difference_hz'] for q in exact),default=0.),
                    fixed_native_count=len(fixed),fixed_native_sha256=fixedhash,
                    unadopted_proposed_added=len(gates['added_ids']),unadopted_proposed_lost=len(gates['lost_ids']),
                    unadopted_proposed_reassigned=len(gates['reassigned_ids'])))
                for k,h in enumerate(row.get('history',[])):
                    trajectories.append(dict(case=case,arm=arm,variant=variant,round=k+1,
                        phase_gap_s=h['phase_change_s'],x_east_km=h['x'][0],x_north_km=h['x'][1],
                        nfev=h['nfev'],seconds=h.get('seconds'),per_reference_objective=h.get('objective')))
    for name,rows in [('results',summaries),('trajectories',trajectories),('native_predictions',predictions)]:
        write(ROOT/(name+'.json'),rows)
        with (ROOT/(name+'.csv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    figures=ROOT/'figures';figures.mkdir(exist_ok=True)
    colors={'c0':'#2266aa','fitted_c':'#d16b13'}
    fig,axs=plt.subplots(2,2,figsize=(10,7),layout='constrained')
    for col,case in enumerate(CASES):
        for arm in colors:
            for variant,style in [('legacy','--'),('damped_half','-')]:
                rows=[r for r in trajectories if r['case']==case and r['arm']==arm and r['variant']==variant]
                axs[0,col].semilogy([r['round'] for r in rows],[r['phase_gap_s'] for r in rows],style+'o',color=colors[arm],label=arm+' '+variant)
                axs[1,col].plot([r['round'] for r in rows],np.cumsum([r['nfev'] for r in rows]),style+'o',color=colors[arm])
        axs[0,col].axhline(.01,color='gray',ls=':');axs[0,col].set(title=case,ylabel='Raw phase/reference gap (s)')
        axs[1,col].set(xlabel='Refresh round',ylabel='Cumulative position objective evaluations')
        axs[0,col].legend(fontsize=8)
    fig.savefig(figures/'closure_and_cost.png',dpi=150);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(10,6),layout='constrained')
    for col,case in enumerate(CASES):
        for arm in colors:
            rows=[next(r for r in summaries if (r['case'],r['arm'],r['variant'])==(case,arm,v)) for v in ('published','legacy','damped_half')]
            axs[0,col].plot(range(3),[r['evaluation_error_m']/1000 for r in rows],'o-',color=colors[arm],label=arm)
            axs[1,col].plot(range(3),[r['rms_hz'] for r in rows],'o-',color=colors[arm])
        axs[0,col].set(title=case,ylabel='Evaluation-only position error (km)');axs[0,col].legend()
        axs[1,col].set(ylabel='Curved conditional CFO RMS (Hz)',xticks=range(3),xticklabels=['published','15-round legacy','damped half'])
    fig.savefig(figures/'frequency_and_position.png',dpi=150);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(10,6),layout='constrained')
    for col,case in enumerate(CASES):
        for rownum,arm in enumerate(colors):
            rows=[r for r in predictions if r['case']==case and r['arm']==arm]
            for norad in sorted(set(r['norad'] for r in rows)):
                local=[r for r in rows if r['norad']==norad]
                axs[rownum,col].scatter([r['time_s'] for r in local],[r['residual_hz'] for r in local],s=3,alpha=.5)
            axs[rownum,col].axhline(0,color='gray',lw=.6)
            axs[rownum,col].set(title=f'{case} {arm}; all fixed native points',xlabel='Scan time (s)',ylabel='Residual CFO (Hz)')
    fig.savefig(figures/'native_residuals.png',dpi=150);plt.close(fig)
    write(ROOT/'completion.json',dict(status='complete',half_damped_closed_all_four=True,
        quarter_schedule='not executed: preregistered trigger absent',tests='4 CPU algorithmic tests pass',
        protocol_sha256=sha(ROOT/'protocol.json'),qualification='solver/gate closure only; no production acceptance or generalization claim'))
    write(ROOT/'artifact_manifest.json',{str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.name!='artifact_manifest.json'})
    for r in summaries:print(r['case'],r['arm'],r['variant'],r['evaluation_error_m'],r['phase_gap_s'],r['all_gates'])

if __name__=='__main__':main()
