"""Evaluate the sealed causal-history prior cohort, including all failures."""

import csv
from pathlib import Path

import matplotlib
import numpy as np
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from probe_ds23_history_calibrated_phase import OUT,HISTORY,SOURCE,ROOT
from report_algo01_ds23_sample import position_error,summarize
from run_algo01_ds23_sample import read,sha,write

METHODS=('original','baseline','mean_only','distribution_only','mean_and_distribution')
LABELS=('Original ALGO01','RX support + fragment300','Causal mean only','Causal distribution only','Causal mean + distribution')


def run():
    protocol=read(OUT/'protocol.json');cases=sorted(protocol['cases'])
    execution=read(OUT/'execution.json')
    assert len(cases)==20 and len(execution)==20 and all(r['code']==0 for r in execution)
    source_mismatch=[n for n,h in protocol['code_sha256'].items() if sha(ROOT/'tools'/n)!=h]
    assert not source_mismatch,source_mismatch
    rows=[];validation=[]
    for case in cases:
        d=read(OUT/(case+'.json'));original=read(SOURCE/case/'result.json')
        forecast=read(HISTORY/(case+'_forecast.json'));raw=read(HISTORY/(case+'.json'))
        assert d['source_sha256']==protocol['code_sha256']['probe_ds23_history_calibrated_phase.py']
        assert d['history_forecast_sha256']==sha(HISTORY/(case+'_forecast.json'))
        assert forecast['history_sha256']==sha(HISTORY/(case+'.json'))
        assert not d['GPS_used'] and not forecast['GPS_or_radio_used'] and forecast['strictly_pre_RF']
        assert all(v['epoch']<=raw['cutoff_utc_ns'] and v['collected_utc_ns']<=raw['cutoff_utc_ns'] for vv in raw['past_versions'].values() for v in vv)
        for method in METHODS:
            for arm in ('c0','fitted_c'):
                if method=='original':
                    r=original['arms'][arm]['record'];valid=True
                    passing=original['arms'][arm]['metrics']['accepted_points']
                else:
                    r=d['results'][method]['arms'][arm];valid=d['results'][method]['valid']
                    passing=r['gates']['accepted_points']
                rows.append(dict(case=case,method=method,arm=arm,error_km=position_error(r['endpoint_latlon']),
                    input_points=r['active_points'],passing_points=passing,valid=valid,
                    RMS_hz=r.get('RMS_hz',r.get('frequency_rms_hz',r.get('fit',{}).get('residual_rms_hz')))))
        v=forecast['distribution_validation'];b=forecast['original_distribution_validation']
        validation.append(dict(case=case,qualified=d['earlier_TLE_validation_qualified'],
            validation_transitions=v['count'],old_predictive_cost=b['negative_twice_log_density'],
            learned_predictive_cost=v['negative_twice_log_density'],**d['hyperparameters_from_pre_RF_TLE_only']))
    results={m:{a:summarize([r['error_km'] for r in rows if r['method']==m and r['arm']==a]) for a in ('c0','fitted_c')} for m in METHODS}
    with (OUT/'comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    write(OUT/'summary.json',dict(results=results,target_met=False,all_20_outcomes_reported=True))
    write(OUT/'validation.json',dict(source_mismatch=source_mismatch,all_pre_RF=True,all_final_gates_pass=all(r['valid'] for r in rows),
        rows=len(rows),qualified_scans=sum(r['qualified'] for r in validation),scans=validation,report_source_sha256=sha(Path(__file__))))
    fig,axes=plt.subplots(2,1,figsize=(14,8),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for m,label in zip(METHODS,LABELS,strict=True):
            ax.plot(range(len(cases)),[next(r['error_km'] for r in rows if r['case']==c and r['method']==m and r['arm']==arm) for c in cases],'.-',label=label,alpha=.8)
        ax.axhline(.5,color='crimson',ls='--',label='0.5 km target');ax.grid(alpha=.2)
        ax.set(title=arm,ylabel='Position error (km)');ax.legend(ncol=3,fontsize=8)
    axes[-1].set_xticks(range(len(cases)),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('Causal TLE-history priors · all 20 independent DS23 scans')
    fig.savefig(OUT/'position_error_by_scan.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for m,label in zip(METHODS,LABELS,strict=True):
            e=np.sort([r['error_km'] for r in rows if r['method']==m and r['arm']==arm]);ax.step(e,np.arange(1,21)/20,where='post',label=label)
        ax.axvline(.5,color='crimson',ls='--');ax.set(title=arm,xlabel='Position error (km)',ylabel='Fraction of scans');ax.grid(alpha=.2)
    axes[0].legend(fontsize=7);fig.savefig(OUT/'error_distribution.png',dpi=160);plt.close(fig)
    table=['| Method | c0 mean / median, km | Fitted-c mean / median, km |','|---|---:|---:|']
    for m,label in zip(METHODS,LABELS,strict=True):
        a,b=results[m]['c0'],results[m]['fitted_c'];table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} |")
    body='''# DS23: phase priors learned from causal TLE history

The 0.5 km mean/median target remains unmet. Every scan and regression is retained.
The primary rule was declared as **mean_and_distribution** before the cohort run;
GPS is used only by this reporter, never to select a prior or endpoint.

TABLE

![Position error by scan](position_error_by_scan.png)
![Error distribution](error_distribution.png)

## Experiment

These are the same 20 scans from the original sealed random sample, now development
data, rather than an untouched validation set or all 413 DS23 scans. The control is
receiver-support weighting plus a 300 Hz fragment-offset prior. Regional search
remains a 25×25 km square centered at 37.906, −122.545, cold start at its center.
Satellite labels and alias integers are inherited from the original causal ALGO01
run. This experiment changes phase priors; it does not redo full association search.

For each scan separately, export up to 72 h of earlier TLEs for every satellite in
its regional causal candidate bank. Require collection and encoded epochs before
that scan. Deduplicate epochs, retaining earliest publication. Consecutive A/B/C
versions predict the next update in the along-track time coordinate, using only
states available when C was published. The innovation is a TLE-update proxy,
not measured orbit truth. Exclude triples whose encoded epoch was still future
at that past validation instant. No later-scan catalogue is used for earlier RF.

Use the first 70% of historical publication times for learning and the later 30%
for predictive validation, all before RF. Grid-select signed forecast shrinkage,
phase standard-deviation multiplier, and Gaussian versus unit-variance Student
tails. The Student t scale is sigma*sqrt((nu−2)/nu); sigma denotes standard deviation.
Require at least 30 later historical transitions and better predictive density
than the original Gaussian; otherwise use the zero-mean Gaussian fallback.
After qualification, relearn on all pre-scan history for the current scan. The
candidate-bank-wide fit is not selected from RF-associated satellites.

Only satellite phase coefficients receive heavy tails. Physical orbit modes,
receiver drift, cross-band terms and other priors stay unchanged. Nonzero means
are in physical seconds; the latent prior penalty and posterior native-coordinate
scaling are preserved. Every c0/fitted-c pair starts with identical observations,
labels, aliases, weights and budgets: five phase-reference rounds, at most 48
position steps, and four paired gate/exclusion rounds. A failure in either arm
removes that component from both. Masks may differ between methods: this is a
quality-gated policy comparison, not a pure fixed-observation attribution.

## Interpretation

Scan217 improves from 2.846/2.764 km under the weighted fragment300 control to
1.025/0.869 km with the learned mean and distribution. That selection uses past
TLE prediction, unlike choosing the 0.493/0.415 km combination by known GPS.
It does not establish that the same prior is optimal for every scan or location.

Raw RF residual scores have different normalization constants across Gaussian
and Student models and cannot be compared as normalized model probabilities.
More associated GLRT points and lower frequency RMS also do not imply better
position. Retained calibration counts and RMS are in the CSV. Satellite-family
and receiver correlations, alternative-peak additions, and simultaneous identity
searches are documented in the linked scan217 investigation; they are not rerun
inside this prior-only cohort.

The next work is to diagnose remaining regressions and validate any frozen rule
on untouched independent DS23 scans before changing ALGO01 defaults. No timing
or pseudorange claim is made from the unresolved frame-epoch sign behavior.

## Reproduction and evidence

[Protocol](protocol.json) · [Summary](summary.json) · [All outcomes](comparison.csv) ·
[Validation](validation.json) · [Execution](execution.json).

Run tools/run_ds23_history_calibrated_phase.py then this reporter in the repository
venv with PYTHONPATH=src:tools and BLAS/OMP threads set to 1. Histories and forecast
receipts are in ../2026_10_18_ds23_causal_phase_mean/history/. The archive reader is
read-only; no new RF, QNAP mutation, post-observation TLE, or GPS fitting occurs.
ALGO01 and DBG01 remain published; this is a research extension, not a replacement
of their specifications or golden fixtures.
'''.replace('TABLE','\n'.join(table))
    (OUT/'README.md').write_text(body)
    print('\n'.join(table),flush=True)


if __name__=='__main__':run()
