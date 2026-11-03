"""Validate and plot independent satellite deletions; no new optimization."""
import argparse
import csv
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from leave_one_satellite_out import OUT, ARMS, load, delete_satellite
from subset_positions import enable_research_model
RADIUS=2.


def check_stationarity(obj, best, radius_km=2.):
    from constrained_fit import kkt_residual
    from position_direct import coordinate_jacobian
    scale=obj.scale.copy();scale[:2]=1.
    vector=np.array(best['vector']);z=vector/scale;z[:2]=best['point_km']
    score,gradient=obj.evaluate(vector)
    transformed=gradient*scale
    transformed[:2]=coordinate_jacobian(z[:2]).T@gradient[:2]
    bounds=[(None if lo is None else lo/s,None if hi is None else hi/s)
            for (lo,hi),s in zip(obj.bounds,scale)]
    bounds[:2]=[(-radius_km,radius_km)]*2
    matrix=np.zeros((len(obj.base.satellites),len(z)))
    matrix[:,6]=1.;matrix[:,7:obj.size]=obj.base.basis;matrix*=scale
    lower=np.full(len(matrix),obj.base.minimum_shift_s+1e-6)
    upper=np.full(len(matrix),obj.base.maximum_shift_s-1e-6)
    if np.linalg.norm(z[:2])>=radius_km-1e-5:
        normal=np.r_[-2*z[:2],np.zeros(len(z)-2)]
        matrix=np.vstack([matrix,normal]);lower=np.r_[lower,normal@z];upper=np.r_[upper,np.inf]
    return float(score),float(kkt_residual(transformed,z,bounds,matrix,lower,upper))


def collect():
    enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    rows=[]
    for scan in ('N12','N15'):
        full,meta,_=load(scan)
        expected={None,*map(int,full.numbers)}
        files=list((OUT/scan).glob('*.json'))
        assert len(files)==len(expected), (scan,len(files),len(expected))
        seen=set()
        baseline=json.loads((OUT/scan/'baseline.json').read_text())
        for path in sorted(files):
            saved=json.loads(path.read_text());number=saved['removed_satellite']
            assert number not in seen;seen.add(number)
            data,keep,ids=delete_satellite(full,number)
            assert saved['retained_rows_sha256']=='sha256:'+hashlib.sha256(data.original_rows.tobytes()).hexdigest()
            assert saved['retained_satellites']==data.numbers.tolist()
            assert saved['removed_windows']==int(sum(~keep))
            assert saved['retained_windows']==int(sum(keep))
            assert saved['input_sha256']==meta['input_sha256']
            for arm in ARMS:
                result=saved['arms'][arm];best=result['best']
                obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,100.)
                obj.center=meta['rf_center_hz'];obj.features=((data.rf-obj.center)/1e9)[:,None]
                obj.likelihood.features=obj.features
                obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
                obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
                if arm=='zero-c':obj.bounds[-1]=(0.,0.)
                obj.base.deadline=float('inf')
                score,kkt=check_stationarity(obj,best,RADIUS)
                assert abs(score-best['objective'])<1e-7
                assert np.linalg.norm(best['point_km'])<=RADIUS+1e-7
                if RADIUS==4.:
                    previous_path=OUT.with_name(OUT.name.removesuffix('-4km'))/scan/path.name
                    previous=json.loads(previous_path.read_text())['arms'][arm]
                    assert score<=previous['best']['objective']+1e-7, (scan,number,arm,'regressed score')
                if not best['fixed_location']:
                    assert abs(kkt-best['kkt_residual'])<1e-7
                    assert (kkt<=1e-3)==result['converged']
                base=baseline['arms'][arm]['distance_m']
                rows.append(dict(scan=scan,removed_satellite='none' if number is None else number,arm=arm,
                                 removed_windows=saved['removed_windows'],retained_windows=saved['retained_windows'],
                                 removed_rx0_windows=saved['removed_rx0_windows'],removed_rx1_windows=saved['removed_rx1_windows'],
                                 distance_m=result['distance_m'],baseline_distance_m=base,
                                 improvement_m=base-result['distance_m'],east_m=1000*best['point_km'][0],
                                 north_m=1000*best['point_km'][1],boundary=result['boundary'],
                                 converged=result['converged'],ambiguous=result['ambiguous'],kkt_residual=kkt,
                                 score_minus_same_case_roof=result['delta_score_to_roof'],score_reconstruction_error=score-best['objective'],
                                 result_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        assert seen==expected
    return rows


def render(rows):
    colors={'fitted-c':'#0072B2','zero-c':'#D55E00'}
    fig,axes=plt.subplots(2,1,figsize=(18,11),sharey=True)
    for ax,scan in zip(axes,('N12','N15')):
        selected=[r for r in rows if r['scan']==scan]
        numbers=sorted({r['removed_satellite'] for r in selected if r['removed_satellite']!='none'})
        for arm,offset in zip(ARMS,(-.14,.14)):
            base=next(r for r in selected if r['arm']==arm and r['removed_satellite']=='none')
            ax.axhline(base['distance_m'],color=colors[arm],ls='--',lw=1.4,alpha=.65)
            for i,number in enumerate(numbers):
                row=next(r for r in selected if r['arm']==arm and r['removed_satellite']==number)
                x=i+offset;y=row['distance_m']
                marker='^' if row['boundary'] else 'o'
                ax.plot(x,y,marker=marker,color=colors[arm],ms=8,ls='none')
                if not row['converged']:ax.plot(x,y,'x',color='black',ms=8,mew=1.6)
                if row['ambiguous']:ax.plot(x,y,marker='o',mfc='none',mec='black',ms=13,ls='none')
                if row['improvement_m']>300:
                    ax.annotate(f'{y:.0f} m',(x,y),xytext=(0,-18),textcoords='offset points',
                                ha='center',color=colors[arm],fontsize=9)
        counts={r['removed_satellite']:r['removed_windows'] for r in selected}
        ax.set_xticks(range(len(numbers)),[f'{n}\n({counts[n]})' for n in numbers],fontsize=9)
        ax.set_xlim(-.6,len(numbers)-.4);ax.set_ylim(0,1090*RADIUS)
        ax.set_ylabel('Best-found distance from correct roof (m)')
        ax.set_xlabel('Removed satellite NORAD ID (assigned GLRT windows removed)')
        ax.grid(axis='y',alpha=.23);ax.set_axisbelow(True)
        baseline=[next(r for r in selected if r['arm']==a and r['removed_satellite']=='none') for a in ARMS]
        unresolved=sum(not r['converged'] for r in selected if r['removed_satellite']!='none')
        ax.set_title(f'{scan} · {len(numbers)} independent removals · no removal: fitted c {baseline[0]["distance_m"]:.0f} m, c = 0 {baseline[1]["distance_m"]:.0f} m\n'
                     f'{unresolved} unconverged deletion fits; triangles indicate the {RADIUS:g} km search boundary',fontsize=13)
    handles=[Line2D([],[],color=colors[a],marker='o',ls='none',label=label)
             for a,label in zip(ARMS,('Fitted c','c = 0'))]
    handles += [Line2D([],[],color='gray',ls='--',label='Matched no-removal control'),
                Line2D([],[],color='gray',marker='^',ls='none',label='Search boundary'),
                Line2D([],[],color='black',marker='x',ls='none',label='Unconverged'),
                Line2D([],[],color='black',marker='o',mfc='none',ls='none',label='Search ambiguity')]
    fig.suptitle(f'T1-AT v1 · leave one satellite out · independent {RADIUS:g} km position searches',fontsize=20,y=.98)
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.946),ncol=6,frameon=False)
    fig.text(.5,.025,'Remove the satellite and all its original assigned windows from the full baseline; removals are not cumulative.\n'
             'Remaining measurements and saved receiver baseline stay fixed; nuisance terms and position refitted. Same inputs and search budgets in both RF arms.\n'
             f'Three-start local searches, not a global-minimum certificate. Boundary results may prefer locations beyond {RADIUS:g} km. Post-hoc diagnostic, not satellite-identity proof.',
             ha='center',fontsize=10)
    fig.subplots_adjust(top=.84,bottom=.15,hspace=.48,left=.07,right=.985)
    fig.savefig(OUT/'removed-satellite-vs-position-error.png',dpi=160)
    fig.savefig(OUT/'removed-satellite-vs-position-error.svg')
    plt.close(fig)


def main():
    global OUT,RADIUS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--radius-km',type=float,choices=(2.,4.),default=2.)
    RADIUS=parser.parse_args().radius_km
    if RADIUS!=2.:OUT=OUT.with_name(OUT.name+f'-{RADIUS:g}km')
    rows=collect()
    with (OUT/'results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    audit=dict(cases=len(rows)//2,arms=len(rows),converged=sum(r['converged'] for r in rows),
               maximum_score_error=max(abs(r['score_reconstruction_error']) for r in rows),
               removal_and_input_hashes_verified=True,stationarity_recomputed=True,
               radius_m=RADIUS*1000,score_comparison_between_deletions_valid=False)
    (OUT/'audit.json').write_text(json.dumps(audit,indent=2))
    render(rows);print(json.dumps(audit,indent=2))
    for scan in ('N12','N15'):
        for arm in ARMS:
            group=[r for r in rows if r['scan']==scan and r['arm']==arm and r['removed_satellite']!='none']
            print(scan,arm,'closest removals',[(r['removed_satellite'],round(r['distance_m']),r['converged']) for r in sorted(group,key=lambda r:r['distance_m'])[:5]])


if __name__=='__main__':main()
