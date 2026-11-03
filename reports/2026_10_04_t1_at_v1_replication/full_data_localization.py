"""Compare fold calibration, full-data calibration with old memberships, and rebuilt memberships.

Each RF pair shares observations and candidate bank anchored by its fitted-c
association. Full-data refers to calibration without holdouts; localization
retains the established associated-window input policy. No independent validation.
"""
import argparse
import copy
import csv
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from full_data_calibration import FullCalibration,INPUTS,OUT,ARMS,digest,serial
from run import TopAbsoluteCalibration,HERE
from numeric_data import enable_research_model
from leave_one_satellite_out import load
from convergence_fisher import fit
from resume_position_convergence import best_record
from timing_bound_comparison import feasible_start
from refinement import circular

SCANS=('N12','N15')
CASES=('fold-control','full-fixed-members','full-rebuilt-members')
OLD_ASSOC=Path('/srv/bulk/leo/t1-at-v1-replication-20261004/remaining')
BUDGET=dict(roof=8.,probe=1.,search=12.,polish=15.)


def fold_baseline(cal):
    fixed=np.zeros(cal.group_count);coefficients=[]
    for fold,(destination,part,models) in enumerate(cal.parts):
        record=json.loads((INPUTS/cal.data.label/'seed-timing-v6/calibration-v2'/f'fold-{fold}.json').read_text())
        coeff=record['arms']['fitted-c']['coefficient'];p,_,correction=models['fitted-c']
        fixed[destination]=correction-coeff*(part.rf-record['rf_center_hz'])/1e9+p[2+2*part.receiver]+p[3+2*part.receiver]*(part.times-150.)
        coefficients.append(coeff)
    return fixed[cal.inverse],float(np.median(coefficients))


def prepare(scan,case):
    cal=FullCalibration(scan);raw=cal.data
    old,meta,saved=load(scan)
    folded=TopAbsoluteCalibration(INPUTS/scan/'seed-timing-v6');folded.data.label=scan
    old_baseline,old_c=fold_baseline(folded)
    assert np.array_equal(folded.data.original_rows,raw.original_rows)
    old_receipt=json.loads((OLD_ASSOC/scan/'fitted-c.json').read_text())
    new_receipt=json.loads((OUT/scan/'associations/fitted-c.json').read_text())
    receipt=new_receipt if case=='full-rebuilt-members' else old_receipt
    assigned=sorted(receipt['final']['assignments'],key=lambda a:a['row_index'])
    lookup={int(r):i for i,r in enumerate(raw.original_rows)}
    rows=np.asarray([lookup[a['row_index']] for a in assigned],int)
    owners=np.asarray([a['catalog_number'] for a in assigned],int)
    selected={int(r['catalog_number']):r for r in receipt['final']['selected']}
    numbers=sorted(selected);columns=np.asarray([int(np.flatnonzero(raw.numbers==n)[0]) for n in numbers])
    data=copy.copy(raw)
    for key in ('times','measured','rf','receiver','channel','group','margin','original_rows'):
        setattr(data,key,getattr(raw,key)[rows].copy())
    data.numbers=raw.numbers[columns];data.position=raw.position[columns];data.velocity=raw.velocity[columns]
    full_baseline=cal.receiver_baseline('fitted-c')
    baseline=old_baseline if case=='fold-control' else full_baseline
    data.measured-=baseline[rows];data.fixed_receiver_hz=baseline[rows];data.owners=owners
    data.initial=np.r_[raw.initial[:2],np.zeros(4),[selected[n]['offset_s'] for n in numbers]]
    if case=='fold-control':
        np.testing.assert_array_equal(data.original_rows,old.original_rows)
        np.testing.assert_allclose(data.measured,old.measured,atol=1e-7,rtol=0)
        np.testing.assert_array_equal(data.numbers,old.numbers)
    information=dict(scan=scan,case=case,raw_sources=raw.sources,
        calibration_source=str(cal.path),calibration_sha256=digest(cal.path),
        association_source=str((OUT/scan/'associations' if case=='full-rebuilt-members' else OLD_ASSOC/scan)/'fitted-c.json'),
        rf_center_hz=cal.record['rf_center_hz'],window_count=len(rows),numbers=numbers,
        original_rows=data.original_rows.tolist(),owners=owners.tolist(),
        heldout_rows=[],selection='All fitted-c associated top-one windows; identical bank/observations for both RF variants.')
    # Approximate baseline transfer by receiver lines for warm starts only.
    shifts=np.zeros(4)
    for rx in (0,1):
        mask=data.receiver==rx
        design=np.column_stack([np.ones(sum(mask)),data.times[mask]-150.])
        shifts[2*rx:2*rx+2]=np.linalg.lstsq(design,(old_baseline-baseline)[rows][mask],rcond=None)[0]
    return data,information,old,saved,shifts


def transferred(record,data,old,shifts):
    p=np.asarray(record['parameters']);previous={int(n):p[6+i] for i,n in enumerate(old.numbers)}
    parameters=np.r_[p[:6],[previous.get(int(n),data.initial[6+i]) for i,n in enumerate(data.numbers)]]
    parameters[2:6]+=shifts
    # Match original drift bounds even if the baseline-transfer approximation is large.
    parameters[[3,5]]=np.clip(parameters[[3,5]],-50.,50.)
    return dict(record,parameters=parameters)


def run(task):
    scan,case=task;target=OUT/scan/f'{case}-position.json'
    if target.exists():return scan,case
    enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    from prediction_plan import SharedPredictionPlan
    data,meta,old,previous,shifts=prepare(scan,case)
    source=OUT/scan/f'{case}-input.npz'
    fields=('times','measured','rf','receiver','channel','group','margin','original_rows','owners',
            'numbers','position','velocity','nodes','initial','fixed_receiver_hz')
    if not source.exists():np.savez_compressed(source,**{k:getattr(data,k) for k in fields})
    result=dict(scope=__doc__,input_metadata=meta,input_sha256=digest(source),
        radius_km=4.,total_timing_bound_s=20.,maximum_budgets_s=BUDGET,
        implementation_sha256=digest(Path(__file__)),arms={})
    for arm in ARMS:
        latest=HERE/'timing-bound-10s-vs-20s/cross-start-polish'/f'{scan}-{arm}-20s.json'
        best_old=json.loads(latest.read_text())['best'] if latest.exists() else previous['arms'][arm]['best']
        seeds=[transferred(r,data,old,shifts) for r in (previous['arms'][arm]['roof'],best_old)]
        obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,60.)
        obj.center=meta['rf_center_hz'];obj.features=((data.rf-obj.center)/1e9)[:,None];obj.likelihood.features=obj.features
        obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
        obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
        if arm=='zero-c':obj.bounds[-1]=(0.,0.)
        records=[]
        def fitted(stage,seed,point,budget,fixed=False):
            r=fit(obj,feasible_start(obj,seed,20.,arm),point,budget,fixed,radius_km=4.)
            r['stage']=stage;records.append(r);return r
        roof=fitted('roof',seeds[0],[0.,0.],BUDGET['roof'],True)
        # Also use the recalibrated association timing at the roof, same extra start for all cases.
        association_seed=dict(parameters=data.initial,coefficient=FullCalibration(scan).record['arms'][arm]['coefficient'])
        roof2=fitted('roof-association-timing',association_seed,[0.,0.],BUDGET['roof'],True)
        roof=min([roof,roof2],key=lambda r:r['objective'])
        probes=[]
        for i,angle in enumerate(np.arange(4)*np.pi/2):
            point=3.2*np.array([np.cos(angle),np.sin(angle)])
            probes.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
        ring=min(probes,key=lambda r:r['objective'])
        for i,seed in enumerate([roof,seeds[1],ring]):
            fitted(f'search-{i}',seed,seed['point_km'],BUDGET['search'])
        best=best_record(records)
        fitted('polish',best,best['point_km'],BUDGET['polish'])
        best=best_record(records)
        obj.base.deadline=float('inf');value,_=obj.evaluate(np.asarray(best['vector']))
        assert abs(value-best['objective'])<1e-7
        penalty,_=obj.base.penalty(np.asarray(best['vector'])[:obj.size])
        probability=obj.likelihood.last_result['row_association_probability']
        assert max(abs(np.asarray(best['parameters'])[6:]))<=20.+1e-7
        assert np.linalg.norm(best['point_km'])<=4.+1e-7
        pred,_vis,_jac=SharedPredictionPlan(data,np.arange(len(data.numbers))).predict(np.asarray(best['parameters']))
        pred=pred.reshape(len(data.times),-1)+best['coefficient']*(data.rf[:,None]-obj.center)/1e9
        owner_index=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in data.owners])
        residual=circular(data.measured-pred[np.arange(len(data.times)),owner_index])
        result['arms'][arm]=dict(best=best,roof=roof,records=records,
            distance_m=1000*np.linalg.norm(best['point_km']),converged=bool(best['success'] and not best['fixed_location']),
            boundary=bool(np.linalg.norm(best['point_km'])>=4.-1e-4),objective=value,data_nll=value-penalty,
            timing_prior_nll=penalty,original_owner_rms_hz=float(np.sqrt(np.mean(residual**2))),
            strong_soft_windows=int(sum(np.max(probability,axis=1)>.5)))
        target.with_suffix('.partial.json').write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
        print('POSITION',scan,case,arm,round(result['arms'][arm]['distance_m']),best['status'],flush=True)
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    return scan,case


def render():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    rows=[];coverage=[]
    for scan in SCANS:
        for arm in ARMS:
            for variant,path in [('fold',OLD_ASSOC/scan/f'{arm}.json'),('full',OUT/scan/'associations'/f'{arm}.json')]:
                receipt=json.loads(path.read_text());r=receipt['final']
                coverage.append(dict(scan=scan,arm=arm,calibration=variant,assigned=r['assigned'],
                    denominator=r['denominator'],coverage=r['coverage'],satellites=r['satellites'],
                    greedy_assigned=receipt['initial']['assigned'],replacement_converged=receipt['converged'],
                    rms_hz=float(np.sqrt(np.mean([a['residual_hz']**2 for a in r['assignments']])))))
        for case in CASES:
            r=json.loads((OUT/scan/f'{case}-position.json').read_text())
            for arm,v in r['arms'].items():
                rows.append(dict(scan=scan,case=case,arm=arm,windows=r['input_metadata']['window_count'],
                    satellites=len(r['input_metadata']['numbers']),**{k:v[k] for k in ('distance_m','converged','boundary',
                    'objective','data_nll','timing_prior_nll','original_owner_rms_hz','strong_soft_windows')}))
    for name,values in [('localization-summary.csv',rows),('association-summary.csv',coverage)]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
    fig,axes=plt.subplots(2,3,figsize=(16,9))
    labels=['Five-fold\nold members','Full-scan\nold members','Full-scan\nrebuilt members']
    for i,scan in enumerate(SCANS):
        ax=axes[i,0]
        for j,arm in enumerate(ARMS):
            pair=[next(r for r in coverage if r['scan']==scan and r['arm']==arm and r['calibration']==v) for v in ['fold','full']]
            for k,(r,color) in enumerate(zip(pair,['#999999','#0077ad'])):
                x=j+(-.18 if k==0 else .18)
                ax.bar(x,100*r['coverage'],width=.34,color=color)
                ax.text(x,100*r['coverage']+1,f"{100*r['coverage']:.1f}%\n{r['assigned']:,}",ha='center',fontsize=9)
        ax.set_xticks([0,1],['Fitted c','c = 0']);ax.set_ylim(0,112);ax.set_ylabel('Associated top-candidate windows (%)')
        ax.set_title(f'{scan} · association coverage')
        for j,arm in enumerate(ARMS,1):
            ax=axes[i,j]
            values=[next(r for r in rows if r['scan']==scan and r['arm']==arm and r['case']==c) for c in CASES]
            ax.plot(range(3),[r['distance_m'] for r in values],color='.65',lw=1)
            for k,r in enumerate(values):
                color=['#999999','#009e73','#0077ad'][k]
                ax.scatter(k,r['distance_m'],s=85,marker='^' if r['boundary'] else 'o',color=color,zorder=3)
                if not r['converged']:ax.scatter(k,r['distance_m'],marker='x',color='black',s=75,zorder=4)
                ax.annotate(f"{r['distance_m']:.0f} m",(k,r['distance_m']),xytext=(0,12),textcoords='offset points',ha='center',fontsize=10)
            ax.set_xticks(range(3),labels);ax.set_xlim(-.4,2.4);ax.set_ylim(0,4450)
            ax.axhline(4000,color='.5',ls=':');ax.set_ylabel('Best-found position error (m)')
            ax.set_title(f'{scan} · '+('fitted c' if arm=='fitted-c' else 'c = 0'))
        for ax in axes[i]:ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Full-scan calibration prototype · no held-out calibration folds',fontsize=19,y=.99)
    handles=[Line2D([],[],marker='o',color=c,ls='none',label=l) for c,l in [('#999999','Five-fold baseline'),('#009e73','Full calibration, old associations'),('#0077ad','Full calibration, rebuilt associations')]]
    handles+=[Line2D([],[],marker='^',color='.3',ls='none',label='4 km boundary'),Line2D([],[],marker='x',color='black',ls='none',label='Unconverged')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.065),ncol=3,frameon=False,fontsize=10)
    fig.text(.5,.012,'Same frozen GLRT refinement/top-one observations, TLE bank, priors and ±20 s total timing limit. Independent 4 km searches.\n'
             'Calibration uses all top windows; nonlinear RX correction retains its quality gate. Localization uses associated windows only.\n'
             'Each RF pair uses identical fitted-c-selected localization inputs. In-sample development results, not blind positioning or held-out validation.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.145,1,.955));fig.savefig(OUT/'full-data-comparison.png',dpi=170);plt.close(fig)
    # Inspect the calibrated receiver baseline independently of orbit identities.
    fig,axes=plt.subplots(2,2,figsize=(13,7),sharex=True)
    for i,scan in enumerate(SCANS):
        cal=FullCalibration(scan);old=TopAbsoluteCalibration(INPUTS/scan/'seed-timing-v6');old.data.label=scan
        oldbaseline,_=fold_baseline(old);newbaseline=cal.receiver_baseline('fitted-c');d=cal.data
        for rx,ax in enumerate(axes[i]):
            mask=d.receiver==rx;order=np.flatnonzero(mask);order=order[np.argsort(d.times[mask])]
            ax.scatter(d.times[order],oldbaseline[order],s=4,color='.6',label='Fold-specific baseline')
            ax.plot(d.times[order],newbaseline[order],color='#0077ad',lw=1.5,label='One full-scan baseline')
            ax.set_title(f'{scan} · RX{rx}');ax.set_ylabel('RX correction (Hz), excludes RF term');ax.grid(alpha=.15)
    for ax in axes[1]:ax.set_xlabel('Receive time (s)')
    axes[0,0].legend();fig.suptitle('What changes upstream: receiver offset + drift + nonlinear correction')
    fig.tight_layout();fig.savefig(OUT/'receiver-calibration-comparison.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--render-only',action='store_true');args=parser.parse_args()
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=2) as pool:
            for future in as_completed([pool.submit(run,(s,c)) for s in SCANS for c in CASES]):print('CASE COMPLETE',future.result(),flush=True)
    render()
