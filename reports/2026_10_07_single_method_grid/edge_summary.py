"""Audit edge-priority follow-up and compare with the matched original schedule."""
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Circle
import experiment as base

HERE=Path(__file__).resolve().parent
OUT=HERE/'edge_priority'

def main():
    result=json.loads((OUT/'results.json').read_text())
    assert result['status']=='complete' and len(result['points'])==400
    assert len({tuple(p['point']) for p in result['points']})==400
    for path,expected in result['source_hashes'].items():assert base.digest(path)==expected
    base.load();_,obs,bank,prior,score,_=base.CONTEXT
    pair_source=HERE.parent/'2026_10_07_2139_slope_cutoffs/experiment.py'
    spec=importlib.util.spec_from_file_location('paired_metrics',pair_source)
    paired=importlib.util.module_from_spec(spec);spec.loader.exec_module(paired)
    pair_doc=json.loads((HERE.parent/'2026_10_07_cone_failure_debug/paired_identity/2139.json').read_text())
    pairs=np.asarray(pair_doc['pair_rows'],int)
    rows=[]
    for selection in result['selections']:
        row=selection['result']
        if row is None:
            rows.append(dict(arm=selection['arm'],accepted=False));continue
        e,n=row['point'];radius=row['local_radius_km']
        region=json.loads((HERE/'regions'/f'{e:g}_{n:g}_{radius:g}.json').read_text())
        obj=base.PositionObjective(obs,bank.select(region['association']['selected_indices']),prior,score,
                                   receiver_baseline_hz=np.asarray(region['calibration']['receiver_baseline_hz']))
        v=np.asarray(row['vector']);value,gradient,_=obj.evaluate(v)
        np.testing.assert_allclose(value,row['objective'],atol=1e-6,rtol=0)
        audit=base.audit(obj,v,gradient,selection['arm'],[e,n],radius)
        np.testing.assert_allclose(audit['stationarity'],row['stationarity'],atol=1e-5,rtol=0)
        assert audit['converged'] and audit['feasible']
        rows.append(dict(arm=selection['arm'],accepted=True,error_km=row['horizontal_error_m']/1000,
                         score=row['selection_score'],frequency_rms_hz=row['frequency_rms_hz'],
                         data_nll=row['data_nll'],timing_penalty=row['timing_penalty'],
                         additional_slopes_hz_s=row['additional_slopes_hz_s'],point=[e,n],
                         pair_clock=paired.pair_metrics(obj,v,pairs),**audit))
    legacy=json.loads((HERE/'proposed50_20_5-search.json').read_text())
    baseline=json.loads((HERE/'summary.json').read_text())
    oldrows=[r for r in baseline['rows'] if r['schedule']=='proposed50_20_5']
    oldpoints={tuple(p['point']):p['score'] for p in legacy['points']}
    shared=[p for p in result['points'] if tuple(p['point']) in oldpoints]
    assert all(p['score']==oldpoints[tuple(p['point'])] for p in shared)
    width_counts={str(s):sum(r['spacing_km']==s for r in result['search']['evaluations']) for s in [50.,20.,5.]}
    report=dict(status='passed',rows=rows,baseline_rows=oldrows,shared_points=len(shared),shared_scores_identical=True,
        outer10km_before=sum(math.hypot(*p['point'])>=240 for p in legacy['points']),
        outer10km_after=result['outer10km_points'],by_cell_width_km=width_counts,
        coarse_converged=sum(p['converged'] is True for p in result['points']),
        coarse_failed=sum(p['status']=='failed' for p in result['points']),
        closest_evaluated_error_m=result['closest_evaluated_error_m'],closest_evaluated_rank=result['closest_evaluated_rank'],
        elapsed_s=result['elapsed_s'],regions=result['regions'],total_regression_tests_passed=10)
    base.write(OUT/'summary.json',report)
    # Use the evaluation coordinate conversion already tested in the frozen fixture.
    spec=importlib.util.spec_from_file_location('reference_geometry',HERE.parent/'2026_10_07_slope_priors/prepare.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    ref=json.loads((HERE/'evaluation.json').read_text())
    truth=helper.reference_point(prior,ref['latitude_deg'],ref['longitude_deg'])
    fig,axes=plt.subplots(1,2,figsize=(12,6),layout='constrained')
    for ax,d,label in zip(axes,[legacy,result],['Original: unmeasured edge score = 0','Changed: edge score from nearest measured cell']):
        points=d['search']['evaluations'];xy=np.array([[p['east_km'],p['north_km']] for p in points])
        sc=ax.scatter(xy[:,0],xy[:,1],c=[p['spacing_km'] for p in points],s=13,cmap='viridis_r',norm=LogNorm(5,50))
        ax.add_patch(Circle((0,0),250,fill=False,color='#888'))
        for b in d['basins']:
            ax.add_patch(Circle((b['east_km'],b['north_km']),max(25.,b['spacing_km']/np.sqrt(2)),fill=False,color='#c23b22',lw=1.5))
        ax.scatter(*truth,marker='*',s=180,c='#f3b700',edgecolor='black',zorder=5)
        ax.set(title=label,xlabel='East of search origin (km)',ylabel='North of search origin (km)',
               xlim=(-270,270),ylim=(-270,270),aspect='equal');ax.grid(alpha=.15)
    bar=fig.colorbar(sc,ax=axes,shrink=.75,ticks=[5,20,50]);bar.ax.set_yticklabels(['5','20','50']);bar.minorticks_off();bar.set_label('Cell width (km)')
    fig.suptitle('Same 50 → 20 → 5 km grid, 400 points, V16, σ = 1 s, ±60 Hz/s\nYellow star = evaluation reference; red circles = retained regions')
    fig.savefig(OUT/'edge_priority_comparison.png',dpi=150);fig.savefig(OUT/'edge_priority_comparison.svg');plt.close(fig)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
