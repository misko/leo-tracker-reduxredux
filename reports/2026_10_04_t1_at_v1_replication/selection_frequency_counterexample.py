"""Same-window N01 identity comparison: timing-only selection versus frequency evidence.

Known roof and archived receiver/RF calibration fixed. Refine only each proposed
satellite's total timing locally around its saved mode. The same 70 top-candidate
windows are scored for both IDs, with identical priors and sigma=200 Hz. This is
conditional in-sample evidence, not ground-truth identity validation.
"""
import json
import numpy as np
from scipy.optimize import minimize_scalar
from regularized_associations import OUT,INPUTS
from run import TopAbsoluteCalibration
from timing_selection_score import timing_cost
from timing_bound_comparison import digest
from subset_positions import serial


def cost(errors,total,other_totals):
    values=np.r_[np.asarray(other_totals),total]
    return float(.5*np.sum((np.asarray(errors)/200.)**2)+timing_cost(len(values),values.sum(),values@values))


def main():
    scan='N01';folder=OUT/scan
    paths=[folder/f'fitted-c-{mode}.json' for mode in ('count-control','timing-regularized')]
    records=[json.loads(p.read_text()) for p in paths]
    numbers=[59540,65543]
    assigned=[[a for a in r['final']['assignments'] if a['catalog_number']==n] for r,n in zip(records,numbers)]
    ids=[sorted(a['row_index'] for a in rows) for rows in assigned]
    assert ids[0]==ids[1] and len(ids[0])==70
    cal=TopAbsoluteCalibration(INPUTS/scan/'seed-timing-v6');data=cal.data
    lookup={int(r):i for i,r in enumerate(data.original_rows)};rows=np.array([lookup[r] for r in ids[0]])
    other=[s['offset_s'] for s in records[0]['final']['selected'] if s['catalog_number']!=numbers[0]]
    results=[]
    for record,number in zip(records,numbers):
        index=int(np.flatnonzero(data.numbers==number)[0])
        selected=next(s for s in record['final']['selected'] if s['catalog_number']==number)
        initial=selected['offset_s'];bounds=(max(-20.,initial-1.),min(20.,initial+1.))
        def errors(t):
            residual,visible,_=cal.residual('fitted-c',index,float(t))
            assert visible[rows].all()
            return residual[rows]
        def objective(t):return cost(errors(t),t,other)
        fit=minimize_scalar(objective,bounds=bounds,method='bounded',options={'xatol':1e-8})
        value,t=min((fit.fun,fit.x),(objective(initial),initial))
        e=errors(t)
        results.append(dict(satellite=number,initial_total_s=initial,refined_total_s=float(t),
            initial_rms_hz=float(np.sqrt(np.mean(errors(initial)**2))),rms_hz=float(np.sqrt(np.mean(e**2))),
            gaussian_frequency_cost=float(.5*np.sum((e/200.)**2)),frequency_plus_timing_cost=float(value),
            timing_prior_cost=float(value-.5*np.sum((e/200.)**2)),residual_hz=e,
            local_search_bounds_s=bounds,optimizer_success=bool(fit.success)))
    result=dict(scope=__doc__,scan=scan,windows=70,original_rows=ids[0],
        time_s=data.times[rows],receiver=data.receiver[rows],channel=data.channel[rows],
        other_total_timing_s=other,comparison='Equal windows and satellite count; old other-satellite timings frozen for both.',
        source_sha256={str(p):digest(p) for p in paths},results=results)
    (OUT/'N01-frequency-counterexample.json').write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True,sharey=True)
    colors=['#0072b2','#d55e00','#009e73','#cc79a7']
    for ax,r in zip(axes,results):
        for channel in np.unique(data.channel[rows]):
            m=data.channel[rows]==channel
            ax.scatter(data.times[rows][m],np.asarray(r['residual_hz'])[m],s=22,color=colors[int(channel)-1],label=f'CH{int(channel)}')
        ax.axhline(0,color='.5',lw=1);ax.grid(alpha=.15);ax.set_ylabel('GLRT − orbit (Hz)')
        ax.set_title(f"NORAD {r['satellite']} · same 70 windows · locally refined RMS {r['rms_hz']:.1f} Hz\n"
            f"Total timing {r['refined_total_s']:+.3f} s; frequency + timing cost {r['frequency_plus_timing_cost']:.2f}")
    axes[0].legend(ncol=4);axes[1].set_xlabel('Receive time (s)')
    fig.suptitle('A smaller timing correction is not sufficient evidence for satellite identity',fontsize=16)
    fig.text(.5,.018,'N01: timing-regularized coverage replaces 59540 with 65543 without adding a single window.\n'
        'Here both candidates get the same local timing fit, fixed roof/RX/RF and Gaussian frequency + timing score.\n'
        'All-window in-sample diagnostic on the identical 70-window track; not an independent identity confirmation.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.115,1,.955));fig.savefig(OUT/'N01-frequency-counterexample.png',dpi=165);plt.close(fig)
    print(json.dumps([{k:v for k,v in r.items() if k!='residual_hz'} for r in results],indent=2))


if __name__=='__main__':main()
