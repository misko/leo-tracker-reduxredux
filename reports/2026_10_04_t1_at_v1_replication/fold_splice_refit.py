"""Controlled no-fold recalibration/reassociation test for N05 and N06.

Use the pre-existing full-data calibration implementation; test the two largest
fold-switch discontinuities, identified without ranking by position truth.
Three cases: old fold calibration/memberships, full calibration/old memberships,
and full calibration/rebuilt memberships. All localization observations in each
case are fitted. Same RF-arm inputs, timing priors, bounds and search budgets.
"""
import argparse
import json
import csv
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import full_data_localization as prototype
from full_data_calibration import OUT as SOURCE, FullCalibration, validate_scope
from leave_one_satellite_out import HERE,load
from post_scan_tle_localization import make_objective
from audit_post_scan_tle import diagnostics
from convergence_fisher import fit
from resume_position_convergence import best_record
from timing_bound_comparison import digest
from subset_positions import serial

SCANS=('N05','N06')
ARMS=('fitted-c','zero-c')
CASES=prototype.CASES
OUT=HERE/'fold-splice-audit/refits'
POLISH_S=30.


def input_data(scan,case):
    path=SOURCE/scan/f'{case}-input.npz'
    with np.load(path) as z:data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    return data,path


def run(task):
    scan,case=task
    prototype.run(task)
    source=SOURCE/scan/f'{case}-position.json'
    target=OUT/scan/f'{case}.json';target.parent.mkdir(exist_ok=True,parents=True)
    if target.exists():return str(target)
    result=json.loads(source.read_text())
    data,input_path=input_data(scan,case)
    assert result['input_sha256']==digest(input_path)
    for arm in ARMS:
        saved=result['arms'][arm]
        obj=make_objective(data,result['input_metadata'],arm)
        best=saved['best']
        new=fit(obj,np.asarray(best['vector']),best['point_km'],POLISH_S,radius_km=4.)
        new['stage']='matched-splice-audit-polish';saved['records'].append(new)
        saved['best']=best_record(saved['records'])
        saved.update(diagnostics(obj,data,saved['best']))
        assert saved['objective']<=best['objective']+1e-7
        print('FULL SCAN POSITION',scan,case,arm,round(saved['distance_m']),saved['converged'],flush=True)
    result.update(parent_source_sha256=digest(source),extra_polish_budget_s=POLISH_S,
        splice_experiment_scope=__doc__,splice_implementation_sha256=digest(Path(__file__)))
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    return str(target)


def audit():
    rows=[];coverage=[];sources={}
    for scan in SCANS:
        cal=FullCalibration(scan);validate_scope(cal.record,cal.data)
        assert cal.record['converged'] and not cal.record['heldout_original_rows']
        sources[str(cal.path)]=digest(cal.path)
        original,old_meta,_=load(scan)
        for calibration,path in [('fold',Path(old_meta['association_source']).parent),
                                 ('full',SOURCE/scan/'associations')]:
            for arm in ARMS:
                receipt_path=path/f'{arm}.json';r=json.loads(receipt_path.read_text());a=r['final']
                assert a['denominator']==len(cal.data.times)
                assert len(a['assignments'])==a['assigned']==len({x['row_index'] for x in a['assignments']})
                assert set(x['row_index'] for x in a['assignments'])<=set(cal.data.original_rows)
                assert {x['catalog_number'] for x in a['assignments']}=={x['catalog_number'] for x in a['selected']}
                sources[str(receipt_path)]=digest(receipt_path)
                coverage.append(dict(scan=scan,calibration=calibration,arm=arm,assigned=a['assigned'],
                    denominator=a['denominator'],coverage=a['assigned']/a['denominator'],satellites=a['satellites'],
                    association_rms_hz=float(np.sqrt(np.mean([x['residual_hz']**2 for x in a['assignments']]))),
                    converged=r['converged']))
        inputs={}
        for case in CASES:
            data,input_path=input_data(scan,case);inputs[case]=data
            path=OUT/scan/f'{case}.json';r=json.loads(path.read_text())
            assert r['input_sha256']==digest(input_path)
            assert r['parent_source_sha256']==digest(SOURCE/scan/f'{case}-position.json')
            assert r['extra_polish_budget_s']==POLISH_S and r['maximum_budgets_s']==prototype.BUDGET
            assert r['splice_implementation_sha256']==digest(Path(__file__))
            assert r['input_metadata']['original_rows']==data.original_rows.tolist()
            assert not r['input_metadata']['heldout_rows']
            assert r['input_metadata']['calibration_sha256']==digest(cal.path)
            assert r['input_metadata']['numbers']==data.numbers.tolist()
            # Verify the raw measurements behind every selected row, including
            # newly associated windows absent from the original position fit.
            lookup={int(n):i for i,n in enumerate(cal.data.original_rows)}
            ix=np.array([lookup[int(n)] for n in data.original_rows])
            np.testing.assert_allclose(data.measured+data.fixed_receiver_hz,cal.data.measured[ix],atol=1e-7,rtol=0)
            for arm in ARMS:
                saved=r['arms'][arm]
                obj=make_objective(data,r['input_metadata'],arm)
                values=diagnostics(obj,data,saved['best'])
                for key,value in values.items():
                    np.testing.assert_allclose(value,saved[key],atol=1e-7,rtol=0,err_msg=f'{scan} {case} {arm} {key}')
                assert np.linalg.norm(saved['best']['point_km'])<=4.+1e-7
                assert np.max(abs(np.asarray(saved['best']['parameters'])[6:]))<=20.+1e-7
                assert abs(saved['best']['vector'][6])<=10.+1e-7
                if arm=='zero-c':assert saved['best']['coefficient']==0.
                rows.append(dict(scan=scan,case=case,arm=arm,windows=len(data.times),satellites=len(data.numbers),**values))
        for field in ('times','rf','receiver','channel','group','owners','original_rows','numbers','position','velocity'):
            np.testing.assert_array_equal(getattr(inputs['fold-control'],field),getattr(inputs['full-fixed-members'],field))
            np.testing.assert_array_equal(getattr(inputs['fold-control'],field),getattr(original,field))
        np.testing.assert_allclose(inputs['fold-control'].measured,original.measured,atol=1e-7,rtol=0)
    report=dict(status='passed',scope=__doc__,sources=sources,position_cases=len(rows),
        converged=sum(r['converged'] for r in rows),rows=rows,coverage=coverage,
        caveats=['Known roof used for upstream calibration, as in the baseline. This is not blind geolocation.',
                 'Full-scan calibration pre/post fits use every passing top window. Nonlinear RX fit retains its posterior/600 Hz quality gate.',
                 'No holdouts in new calibration or localization. Position fitting uses associated windows only.',
                 'Rebuilt memberships change the bank and observation set; absolute NLL is not comparable across membership cases.',
                 'Fixed-membership cases preserve raw observations but use different frozen calibration; RF pairs share identical inputs.',
                 'Local 4 km searches; boundaries and nonconvergence are not unconstrained/global minima.'])
    (OUT/'audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    for name,values in [('position-summary.csv',rows),('association-summary.csv',coverage)]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
    print(json.dumps(dict(converged=report['converged'],rows=rows,coverage=coverage),default=serial,indent=2))
    render(report)


def render(report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig,axes=plt.subplots(2,2,figsize=(13,9))
    for i,scan in enumerate(SCANS):
        ax=axes[i,0]
        for j,arm in enumerate(ARMS):
            for dx,cal,color in [(-.18,'fold','#999999'),(.18,'full','#0072b2')]:
                r=next(r for r in report['coverage'] if (r['scan'],r['arm'],r['calibration'])==(scan,arm,cal))
                ax.bar(j+dx,100*r['coverage'],width=.34,color=color)
                ax.text(j+dx,100*r['coverage']+1,f"{100*r['coverage']:.1f}%\n{r['assigned']:,}",ha='center',fontsize=10)
        ax.set_xticks([0,1],['Fitted c','c = 0']);ax.set_ylim(0,112)
        ax.set_title(f'{scan} · coverage before / after full-scan calibration')
        ax.set_ylabel('Passing top GLRT windows associated (%)')
        ax=axes[i,1]
        for arm,color in zip(ARMS,['#0072b2','#d55e00']):
            values=[next(r for r in report['rows'] if (r['scan'],r['arm'],r['case'])==(scan,arm,c)) for c in CASES]
            ax.plot(range(3),[r['distance_m'] for r in values],c=color,lw=1,alpha=.7)
            for j,r in enumerate(values):
                ax.scatter(j,r['distance_m'],c=color,s=60,marker='^' if r['boundary'] else 'o')
                if not r['converged']:ax.scatter(j,r['distance_m'],c='black',s=70,marker='x')
                ax.annotate(f"{r['distance_m']:.0f}",(j,r['distance_m']),xytext=(8,10 if arm=='fitted-c' else -16),textcoords='offset points',color=color,fontsize=10)
        ax.axhline(1000,c='.5',ls='--');ax.axhline(4000,c='.6',ls=':');ax.set_ylim(0,4450);ax.set_xlim(-.35,2.4)
        ax.set_xticks(range(3),['Fold calibration\nold members','Full calibration\nold members','Full calibration\nrebuilt members'])
        ax.set_title(f'{scan} · independent 4 km position search');ax.set_ylabel('Best-found position error (m)')
    for ax in axes.ravel():ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    handles=[Line2D([],[],c=c,marker='o',label=l) for c,l in [('#0072b2','Fitted c (position)'),('#d55e00','c = 0 (position)')]]
    handles += [Line2D([],[],c='.4',marker=m,ls='none',label=l) for m,l in [('x','Unconverged'),('^','4 km boundary')]]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.08),ncol=4,frameon=False)
    fig.suptitle('Replacing stitched fold calibrations with one full-scan fit',fontsize=18)
    fig.text(.5,.015,'Same raw GLRT refinement, top-candidate rule, TLE bank, timing priors and ±20 s timing limits. No new held-out folds.\n'
        'Calibration uses the known roof; nonlinear RX correction retains its quality gate. Localization uses all associated windows.\n'
        'Each RF pair shares fitted-c-selected localization inputs. Matched search budgets; better coverage is not proof of better localization.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.14,1,.94));fig.savefig(OUT/'comparison.png',dpi=165);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--audit-only',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if not args.audit_only:
        with ProcessPoolExecutor(max_workers=4) as pool:
            for f in as_completed([pool.submit(run,(s,c)) for s in SCANS for c in CASES]):f.result()
    audit()
