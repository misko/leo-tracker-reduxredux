"""Evaluate the two complete prespecified prior/weight cohorts on all 20 cases."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_history_calibrated_phase import OUT as SCALAR,HISTORY,ROOT
from probe_ds23_phase_variance_law import OUT as LAW
from probe_ds23_learned_prior_weights import OUT as WEIGHTS
from report_algo01_ds23_sample import position_error,summarize
from run_algo01_ds23_sample import read,write,sha

OUT=ROOT/'reports/2026_10_18_ds23_prior_refinements'
METHODS=('scalar_rx','law_only','law_mean','causal_law_selection','unit','confidence_only')
LABELS=('Scalar history prior + RX support','Variance law, zero mean','Variance law + mean',
        'Earlier-TLE law selection','Scalar prior, unit weights','Scalar prior, confidence weights')


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    protocols=[read(d/'protocol.json') for d in (LAW,WEIGHTS)]
    cases=sorted(protocols[0]['cases']);assert len(cases)==20 and cases==sorted(protocols[1]['cases'])
    for directory,protocol in zip((LAW,WEIGHTS),protocols,strict=True):
        receipts=read(directory/'execution.json');assert len(receipts)==20 and all(r['code']==0 for r in receipts)
        assert all(sha(ROOT/'tools'/n)==h for n,h in protocol['source_sha256'].items())
    rows=[];qualification=[];baseline_replay=[]
    for case in cases:
        scalar=read(SCALAR/(case+'.json'));law=read(LAW/(case+'.json'));weights=read(WEIGHTS/(case+'.json'))
        forecast=HISTORY/(case+'_forecast.json');law_receipt=HISTORY/(case+'_variance_law.json')
        assert weights['forecast_sha256']==sha(forecast) and law['law_input_sha256']==sha(law_receipt)
        assert read(law_receipt)['all_past_history_forecast_sha256']==sha(forecast)
        assert not law['GPS_used'] and not weights['GPS_used']
        qualification.append(dict(case=case,qualified=law['law_qualification'],chosen=law['chosen'],learned=law['learned_prior']))
        for arm in ('c0','fitted_c'):
            original=np.asarray(scalar['results']['mean_and_distribution']['arms'][arm]['endpoint_east_north_km'])
            replay=np.asarray(law['results']['scalar']['arms'][arm]['endpoint_east_north_km'])
            baseline_replay.append(float(max(abs(original-replay))))
        for method in METHODS:
            r=(scalar['results']['mean_and_distribution'] if method=='scalar_rx' else
               law['results']['variance_law_only'] if method=='law_only' else
               law['results']['variance_law_and_mean'] if method=='law_mean' else
               law['results'][law['chosen']] if method=='causal_law_selection' else weights['results'][method])
            for arm in ('c0','fitted_c'):
                fit=r['arms'][arm]
                rows.append(dict(case=case,method=method,arm=arm,error_km=position_error(fit['endpoint_latlon']),
                    RMS_hz=fit['RMS_hz'],calibration_points=fit['active_points'],passing_points=fit['gates']['accepted_points'],valid=r['valid']))
    assert max(baseline_replay)<1e-8
    summary={m:{a:summarize([r['error_km'] for r in rows if r['method']==m and r['arm']==a]) for a in ('c0','fitted_c')} for m in METHODS}
    with (OUT/'comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    write(OUT/'summary.json',dict(results=summary,all20_reported=True,target_met=False))
    write(OUT/'validation.json',dict(all_source_hashes_match=True,all_paired_final_gates_pass=all(r['valid'] for r in rows),
        scalar_max_replay_difference_km=max(baseline_replay),variance_law_qualified=sum(r['qualified'] for r in qualification),
        selection_receipts=qualification,report_source_sha256=sha(Path(__file__))))
    fig,axes=plt.subplots(2,1,figsize=(14,8),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for m,label in zip(METHODS,LABELS,strict=True):
            if m=='law_only':continue
            vals=[next(r['error_km'] for r in rows if r['method']==m and r['arm']==arm and r['case']==c) for c in cases]
            ax.plot(range(20),vals,'.-',label=label,alpha=.8)
        ax.axhline(.5,color='crimson',ls='--');ax.set(title=arm,ylabel='Position error (km)');ax.legend(ncol=3,fontsize=8);ax.grid(alpha=.2)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('Causal prior refinements and weight ablations · all outcomes retained')
    fig.savefig(OUT/'position_error_by_scan.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    for ax,field,label in zip(axes,('RMS_hz','calibration_points'),('Frequency RMS (Hz)','Retained calibration points'),strict=True):
        for method,title in zip(METHODS,LABELS,strict=True):
            selected=[r for r in rows if r['method']==method and r['arm']=='c0']
            ax.scatter([r[field] for r in selected],[r['error_km'] for r in selected],s=18,alpha=.7,label=title)
        ax.set(xlabel=label,ylabel='Position error (km)');ax.grid(alpha=.2)
    axes[0].legend(fontsize=6);fig.savefig(OUT/'frequency_and_coverage.png',dpi=160);plt.close(fig)
    table=['| Method | c0 mean / median, km | Fitted-c mean / median, km |','|---|---:|---:|']
    for m,label in zip(METHODS,LABELS,strict=True):
        a,b=summary[m]['c0'],summary[m]['fitted_c'];table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} |")
    body='''# DS23: causal variance-law and association-weight ablations

These are all 20 development scans, including regressions. No per-scan GPS choice
is used. The independent-scan 0.5 km mean/median target remains unmet.

Receiver-support weighting with the simpler scalar history prior remains best
among these rules: 1.315/0.991 km c0 and 1.266/0.896 km fitted-c. Neither the
more flexible variance law nor removing the support weights improves the
cohort. The variance law qualifies on earlier-TLE prediction for 18/20 scans,
yet its declared causal selection worsens position to 1.420/1.109 km c0.

TABLE

![Position error by scan](position_error_by_scan.png)
![Frequency fit and retained calibration counts](frequency_and_coverage.png)

## Controlled hypotheses

The comparator is the [causal scalar-history prior](../2026_10_18_ds23_history_calibrated_phase/README.md),
with receiver-support powers and 300 Hz independent fragment constants.
First separate the phase uncertainty floor from the age/disagreement gain:
sigma=clip(hypot(floor, gain*alignment*age/epoch_gap),0.02,15) seconds.
Learn these parameters, mean shrinkage and tail degrees solely from earlier
candidate-bank TLE transitions. A bounded 2D log grid with five refinements is
used, without SciPy. The first 70% of historical publication times trains a
prefix model; the later historical transitions qualify it against the scalar
prefix model. All precede RF. At least 30 validation transitions and improved
predictive density are required. Otherwise retain the scalar prior. The
declared causal-selection row uses that rule, not the smallest GPS error.
The two unconditional law rows diagnose its mean/distribution contributions.

Second hold the scalar prior fixed and compare unit measurement powers to
identity-confidence powers. Unit means every retained point has likelihood
power 1. Confidence uses the minimum conditional candidate-gap confidence
over the existing five regional anchors, clipped to [0.05,1]. This is an
uncalibrated proxy, not a posterior identity probability. The comparator
receiver rule also considers replication across receivers and channels.

All fits keep the same original causal catalogue, discrete satellite labels,
integer aliases, independent radio noise and regional cold initialization.
All begin with the original ALGO01 retained observations. Each c0/fitted-c
pair has identical masks and budgets: five phase rounds, at most 48 position
steps, four paired gate/refit rounds. No gate is widened. Final masks can
differ across policies and are recorded. The scalar arm is independently
replayed in the variance-law run, and its endpoints match within 1e-8 km.

## Scope and limits

TLE-update innovation is an orbit-error proxy, not reference ephemeris truth.
Better historical predictive density need not imply better receiver position:
on217 the law qualifies yet worsens the scalar prior's 1.025/0.869 km to
1.332/1.245 km. These regressions are part of the comparison. More retained
calibration points and lower frequency RMS do not establish geographic gain.
Position accuracy and RF behavior are reported separately in the CSV/figure.
The methods use causal external TLE history, with one scan's RF; no scan's
fitted position is a prior for another. These 20 scans are now development
data and do not validate a new site or all 413 DS23 recordings. No timing
position fix or updated ALGO01 production default is claimed.

## Reproduction

[Summary](summary.json) · [All outcomes](comparison.csv) · [Validation](validation.json).
Raw evidence and frozen protocols: [variance-law cohort](../2026_10_18_ds23_phase_variance_law/protocol.json)
and [weight cohort](../2026_10_18_ds23_learned_prior_weights/protocol.json).
Run tools/run_ds23_phase_variance_law.py and tools/run_ds23_learned_prior_weights.py,
then tools/report_ds23_prior_refinements.py in the repository venv with
PYTHONPATH=src:tools and BLAS/OMP threads 1. Each runner uses two subprocess
workers with per-case timeouts. Published source snapshots overlay the earlier
ALGO01/DBG01 and prior-control snapshots. Histories are already causal receipts;
no new RF or archive mutation is required.
'''.replace('TABLE','\n'.join(table))
    (OUT/'README.md').write_text(body);print('\n'.join(table),flush=True)


if __name__=='__main__':run()
