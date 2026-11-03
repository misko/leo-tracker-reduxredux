"""Post-hoc localization influence, not a satellite-identity test.

Gradient sums partition the full likelihood by frozen observation owner. Fisher
Schur complements are local geometry proxies (not posterior covariances), with
free nuisance variables projected out and timing priors retained. Scores are
compared only within an identical data set and candidate bank.
"""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from leave_one_satellite_out import OUT as OLD,ARMS,load,delete_satellite,digest
from subset_positions import enable_research_model
from convergence_fisher import fit
enable_research_model()
from rf_calibration_diagnostic import CalibrationObjective
from position_direct import coordinate_jacobian
from track_diagnostics import residual_statistics

OUT=OLD.with_name(OLD.name+'-4km')
COLORS={'fitted-c':'#0072B2','zero-c':'#D55E00'}


def objective(data,meta,arm):
    obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,100.)
    obj.center=meta['rf_center_hz'];obj.features=((data.rf-obj.center)/1e9)[:,None]
    obj.likelihood.features=obj.features
    obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
    obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
    if arm=='zero-c':obj.bounds[-1]=(0.,0.)
    obj.base.deadline=float('inf')
    return obj


def profiled_information(hessian,free):
    """Schur complement of a scaled Fisher matrix; exclude exactly fixed terms."""
    nuis=np.flatnonzero(free & (np.arange(len(free))>=2))
    cross=hessian[np.ix_([0,1],nuis)]
    schur=hessian[:2,:2]-cross@np.linalg.pinv(hessian[np.ix_(nuis,nuis)],rcond=1e-12)@cross.T
    schur=(schur+schur.T)/2
    eigen=np.linalg.eigvalsh(schur)
    assert eigen[0]>=-1e-6
    return schur,eigen


def snapshot(obj,data,record):
    vector=np.array(record['vector']);score,grad=obj.evaluate(vector)
    assert abs(score-record['objective'])<1e-7
    like=obj.likelihood.last_result
    pred,visible,jac=obj.base.predict(vector[:obj.size],with_jacobian=True)
    pred=pred+(obj.features@vector[obj.size:])[:,None]
    alias=obj.likelihood.alias_hz
    residual=(data.measured[:,None]-pred+alias/2)%alias-alias/2
    cj=coordinate_jacobian(record['point_km'])
    gradient=cj.T@grad[:2]
    order=np.argsort(data.group)
    assert len(np.unique(data.group))==len(data.group)
    assert np.array_equal(like['group_values'],data.group[order])
    losses=np.zeros(len(data.times));losses[order]=-like['log_likelihood']
    prior=obj.base.last['prior_objective']
    assert abs(losses.sum()+prior-score)<1e-7
    parts={}
    for j,n in enumerate(data.numbers):
        mask=data.owners==n
        weighted=np.zeros_like(like['prediction_gradient'])
        weighted[mask]=-like['prediction_gradient'][mask]
        owned=cj.T@jac.transpose_multiply(weighted.ravel())[:2]
        stats=residual_statistics(data.times[mask],residual[mask,j],data.receiver[mask]*10+data.channel[mask])
        parts[int(n)]=dict(owned_gradient_per_km=owned.tolist(),owned_nll=float(losses[mask].sum()),
                           effective_owner_probability=float(like['row_association_probability'][mask,j].mean()),
                           total_timing_s=float(record['parameters'][6+j]),stats=stats)
    assert np.allclose(np.sum([v['owned_gradient_per_km'] for v in parts.values()],axis=0),gradient,atol=1e-7)
    transform=np.diag(obj.scale);transform[:2,:2]=cj
    hessian=transform.T@obj.curvature(vector)@transform
    free=np.array([lo!=hi or lo is None for lo,hi in obj.bounds])
    schur,eigen=profiled_information(hessian,free)
    active=[i for i,(lo,hi) in enumerate(obj.bounds) if lo!=hi and
            ((lo is not None and abs(vector[i]-lo)<1e-6) or (hi is not None and abs(vector[i]-hi)<1e-6))]
    return dict(score=float(score),prior=float(prior),gradient_per_km=gradient.tolist(),
                fisher_profile_schur=schur.tolist(),fisher_profile_eigenvalues=eigen.tolist(),
                active_box_indices=active,parts=parts,roof_or_joint_success=record['success']),residual,losses


def csv_file(name,rows):
    with (OUT/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    allrows=[];receipts={};snapshots={};selected={};cross=[]
    orientation_path=OLD.parent/'east-west-sanity/satellites.csv'
    with orientation_path.open() as f:
        orientation={(r['scan'],int(r['satellite'])):r for r in csv.DictReader(f)}
    for scan in ('N12','N15'):
        full,meta,_=load(scan)
        cases=[json.loads(p.read_text()) for p in sorted((OUT/scan).glob('*.json'))]
        assert len(cases)==len(full.numbers)+1
        baseline=next(d for d in cases if d['removed_satellite'] is None)
        receipts[scan]=dict(baseline={},deletions={},source_hashes={str(p):digest(p) for p in (OUT/scan).glob('*.json')})
        selected[scan]=set()
        for arm in ARMS:
            ranked=sorted([d for d in cases if d['removed_satellite'] is not None],key=lambda d:d['arms'][arm]['distance_m'])
            selected[scan].update(d['removed_satellite'] for d in ranked[:2]+ranked[-1:])
            obj=objective(full,meta,arm)
            roof,roofres,_=snapshot(obj,full,baseline['arms'][arm]['roof'])
            best,bestres,bestloss=snapshot(obj,full,baseline['arms'][arm]['best'])
            receipts[scan]['baseline'][arm]=dict(roof=roof,best=best)
            snapshots[(scan,arm)]=(roofres,bestres,bestloss)
            for case in cases:
                n=case['removed_satellite']
                if n is None:continue
                data,_,_=delete_satellite(full,n)
                reduced=objective(data,meta,arm)
                r,_,_=snapshot(reduced,data,case['arms'][arm]['roof'])
                receipts[scan]['deletions'].setdefault(n,{})[arm]=dict(roof=r)
                p=roof['parts'][n];q=best['parts'][n]
                g=np.array(p['owned_gradient_per_km'])
                basepoint=np.array(baseline['arms'][arm]['best']['point_km'])
                dot=float(g@basepoint/max(np.linalg.norm(basepoint),1e-12))
                old=json.loads((OLD/scan/f'drop-{n}.json').read_text())['arms'][arm]
                row=dict(scan=scan,arm=arm,satellite=n,removed_windows=case['removed_windows'],
                         rx0_windows=case['removed_rx0_windows'],rx1_windows=case['removed_rx1_windows'],
                         span_s=float(np.ptp(full.times[full.owners==n])),
                         baseline_error_m=baseline['arms'][arm]['distance_m'],error_without_m=case['arms'][arm]['distance_m'],
                         improvement_m=baseline['arms'][arm]['distance_m']-case['arms'][arm]['distance_m'],
                         old_2km_error_m=old['distance_m'],boundary=case['arms'][arm]['boundary'],converged=case['arms'][arm]['converged'],
                         baseline_roof_nuisance_converged=roof['roof_or_joint_success'],
                         deletion_roof_nuisance_converged=r['roof_or_joint_success'],
                         east_shift_m=1000*(case['arms'][arm]['best']['point_km'][0]-basepoint[0]),
                         north_shift_m=1000*(case['arms'][arm]['best']['point_km'][1]-basepoint[1]),
                         owned_east_gradient_per_100m=g[0]/10,owned_north_gradient_per_100m=g[1]/10,
                         owned_derivative_toward_baseline_per_100m=dot/10,
                         owned_nll_best_minus_roof=q['owned_nll']-p['owned_nll'],
                         roof_rms_hz=p['stats']['rms_hz'],best_rms_hz=q['stats']['rms_hz'],
                         roof_linear_quad_ratio=p['stats']['curvature_ratio'],
                         roof_channel_controlled_ratio=p['stats']['channel_controlled_curvature_ratio'],
                         roof_slope_hz_s=p['stats']['pooled_slope_hz_s'],
                         roof_owner_probability=p['effective_owner_probability'],
                         baseline_weak_fisher=roof['fisher_profile_eigenvalues'][0],
                         without_weak_fisher=r['fisher_profile_eigenvalues'][0],
                         weak_fisher_fraction=r['fisher_profile_eigenvalues'][0]/roof['fisher_profile_eigenvalues'][0],
                         gradient_change_per_100m=float(np.linalg.norm(np.array(r['gradient_per_km'])-roof['gradient_per_km']))/10,
                         rf_coefficient_change=case['arms'][arm]['best']['coefficient']-baseline['arms'][arm]['best']['coefficient'])
                original_params=np.array(baseline['arms'][arm]['best']['parameters'])
                dropped_params=np.array(case['arms'][arm]['best']['parameters'])
                row.update(rx0_offset_change_hz=float(dropped_params[2]-original_params[2]),
                           rx0_drift_change_hz_s=float(dropped_params[3]-original_params[3]),
                           rx1_offset_change_hz=float(dropped_params[4]-original_params[4]),
                           rx1_drift_change_hz_s=float(dropped_params[5]-original_params[5]),
                           surviving_timing_change_rms_s=float(np.sqrt(np.mean((dropped_params[6:]-original_params[6:][full.numbers!=n])**2))))
                sky=orientation[(scan,n)]
                for key in ('observed_span_path','receiver_pattern','wrong_fraction','far_wrong_fraction','crossing_median_order'):
                    row['saved_orientation_'+key]=sky[key]
                allrows.append(row)
        # Evaluate the FULL data/bank at the selected deletion locations, profiling
        # full nuisance afresh. This is the valid apples-to-apples score tradeoff.
        for n in sorted(selected[scan]):
            case=next(c for c in cases if c['removed_satellite']==n)
            for arm in ARMS:
                obj=objective(full,meta,arm)
                base=baseline['arms'][arm]['best'];drop=case['arms'][arm]['best']
                record=fit(obj,base['vector'],drop['point_km'],6.,True,radius_km=4.)
                snap,res,loss=snapshot(obj,full,record)
                _,_,base_losses=snapshots[(scan,arm)]
                mask=full.owners==n
                base_snap=receipts[scan]['baseline'][arm]['best']
                missing=float(np.sum((loss-base_losses)[mask]));others=float(np.sum((loss-base_losses)[~mask]))
                prior=snap['prior']-base_snap['prior'];total=record['objective']-base['objective']
                assert abs(missing+others+prior-total)<1e-7
                receipts[scan]['deletions'][n][arm]['full_model_at_deleted_position']=dict(record=record,snapshot=snap)
                cross.append(dict(scan=scan,satellite=n,arm=arm,full_model_profile_converged=record['success'],
                                  full_model_score_change=total,removed_windows_nll_change=missing,
                                  other_windows_nll_change=others,timing_prior_change=prior,
                                  full_model_owned_rms_at_deleted_position=snap['parts'][n]['stats']['rms_hz']))
        print('Characterized',scan,'selected',sorted(selected[scan]),flush=True)
    csv_file('satellite-role-diagnostics.csv',allrows);csv_file('same-model-score-tradeoffs.csv',cross)
    (OUT/'role-diagnostics.json').write_text(json.dumps(dict(scope=__doc__,selected={k:sorted(v) for k,v in selected.items()},receipts=receipts,
        saved_orientation_source=str(orientation_path),saved_orientation_sha256=digest(orientation_path),
        orientation_note='Previously audited roof geometry at saved association timing; nominal pointing, not a measured beam mask.'),indent=2))
    render(allrows,cross,selected,receipts,snapshots)


def render(rows,cross,selected,receipts,snapshots):
    fig,axes=plt.subplots(2,2,figsize=(13,12),sharex=True,sharey=True)
    for i,scan in enumerate(('N12','N15')):
        baseline=json.loads((OUT/scan/'baseline.json').read_text())
        for j,arm in enumerate(ARMS):
            ax=axes[i,j];b=np.array(baseline['arms'][arm]['best']['point_km'])
            for radius,ls in [(2.,':'),(4.,'--')]:ax.add_patch(plt.Circle((0,0),radius,fill=False,color='.6',ls=ls,lw=1))
            ax.plot(0,0,'+',color='black',ms=12,mew=2,label='Correct roof')
            ax.plot(*b,marker='*',color='black',ms=15,label='All satellites')
            for r in [r for r in rows if r['scan']==scan and r['arm']==arm]:
                p=b+np.array([r['east_shift_m'],r['north_shift_m']])/1000
                highlight=r['satellite'] in selected[scan]
                ax.plot(*p,marker='^' if r['boundary'] else 'o',color=COLORS[arm],alpha=1 if highlight else .2,ms=7 if highlight else 4)
                if highlight:
                    ax.plot([b[0],p[0]],[b[1],p[1]],color=COLORS[arm],alpha=.35,lw=1)
                    index=sorted(selected[scan]).index(r['satellite'])
                    dx,dy=[(-35,-18),(8,-18),(8,12),(-35,12)][index%4]
                    if p[0]>3.5:dx=-8
                    ax.annotate(str(r['satellite']),p,xytext=(dx,dy),textcoords='offset points',fontsize=8,
                                ha='right' if dx<0 else 'left',arrowprops=dict(arrowstyle='-',color='.6',lw=.6))
            ax.set_aspect('equal');ax.set_xlim(-4.3,4.3);ax.set_ylim(-4.3,4.3);ax.grid(alpha=.18)
            ax.set_title(f'{scan} · {"fitted c" if arm=="fitted-c" else "c = 0"}\nAll satellites: {np.linalg.norm(b)*1000:.0f} m')
            ax.set_xlabel('East of correct roof (km)');ax.set_ylabel('North of correct roof (km)');ax.legend(fontsize=8,loc='upper left')
    fig.suptitle('Removing a satellite changes the direction as well as the distance',fontsize=17)
    fig.text(.5,.012,'Highlighted: two smallest errors and largest error per RF arm, unioned within each scan. Others shown faintly.\nLines connect the all-satellite solution to independent deletion solutions; not optimizer trajectories. Dashed circle: 4 km; dotted: former 2 km limit.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.055,1,.95));fig.savefig(OUT/'localization-shifts.png',dpi=160);plt.close(fig)
    # Detailed residual controls for the pre-identified influential tracks.
    targets=[('N15',59381),('N15',62842),('N12',53045),('N12',62870)]
    fig,axes=plt.subplots(4,2,figsize=(14,13))
    for i,(scan,n) in enumerate(targets):
        data,_,_=load(scan);col=int(np.flatnonzero(data.numbers==n)[0]);use=data.owners==n
        for j,arm in enumerate(ARMS):
            ax=axes[i,j];rr,br,_=snapshots[(scan,arm)]
            for rx,marker in [(0,'o'),(1,'^')]:
                m=use&(data.receiver==rx)
                if not m.any():continue
                ax.scatter(data.times[m],rr[m,col],s=17,marker=marker,color='#777777',alpha=.7,label=f'Roof RX{rx}')
                ax.scatter(data.times[m],br[m,col],s=20,marker=marker,color=COLORS[arm],alpha=.8,label=f'Full best RX{rx}')
            p=receipts[scan]['baseline'][arm]['roof']['parts'][n]['stats']
            q=receipts[scan]['baseline'][arm]['best']['parts'][n]['stats']
            ax.set_title(f'{scan} · {n} · {arm}\nRMS {p["rms_hz"]:.1f} → {q["rms_hz"]:.1f} Hz; roof linear/quad {p["curvature_ratio"]:.3f}')
            ax.axhline(0,color='.4',lw=.8);ax.grid(alpha=.2);ax.set_xlabel('Receive time (s)');ax.set_ylabel('GLRT − prediction (Hz)');ax.legend(fontsize=7,ncol=2)
    fig.suptitle('Influential tracks: residuals at the roof versus full-model best location',fontsize=17)
    fig.text(.5,.01,'Identical frozen owned windows; alias-aware residuals; nuisance refitted at each location.\nA lower frequency RMS away from the known roof is model tension, not evidence that the roof is wrong. Receiver/channel mixing can contribute structure.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.045,1,.965));fig.savefig(OUT/'influential-track-residuals.png',dpi=160);plt.close(fig)


def render_saved():
    saved=json.loads((OUT/'role-diagnostics.json').read_text())
    receipts=saved['receipts'];snapshots={}
    with (OUT/'satellite-role-diagnostics.csv').open() as f:rows=list(csv.DictReader(f))
    for r in rows:
        r['satellite']=int(r['satellite']);r['boundary']=r['boundary']=='True'
        for key in ('east_shift_m','north_shift_m'):r[key]=float(r[key])
    for scan in ('N12','N15'):
        data,meta,_=load(scan);baseline=json.loads((OUT/scan/'baseline.json').read_text())
        for arm in ARMS:
            for stage in ('roof','best'):
                p=receipts[scan]['baseline'][arm][stage]
                p['parts']={int(k):v for k,v in p['parts'].items()}
            obj=objective(data,meta,arm)
            _,rr,_=snapshot(obj,data,baseline['arms'][arm]['roof'])
            _,br,loss=snapshot(obj,data,baseline['arms'][arm]['best'])
            snapshots[(scan,arm)]=(rr,br,loss)
    render(rows,[],saved['selected'],receipts,snapshots)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--render-only',action='store_true')
    if parser.parse_args().render_only:render_saved()
    else:main()
