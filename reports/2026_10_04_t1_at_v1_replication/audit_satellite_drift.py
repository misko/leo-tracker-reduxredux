"""Reconstruct every drift fit, its unchanged data, and baseline equivalence."""
import csv
import json
from pathlib import Path

import numpy as np
from satellite_drift_localization import (OUT, SCANS, ARMS, MODES, BUDGET,
    SatelliteDriftObjective, diagnostics, load, digest, serial,
    SLOPE_SIGMA_HZ_S, REFERENCE_RF_HZ)
from post_scan_tle_localization import make_objective
from audit_timing_prior_ablation import geometry


def verify_zero_drift(obj, data, meta, arm, record):
    original = make_objective(data,meta,arm)
    v = np.asarray(record['vector']).copy()
    v[obj.size:-1] = 0.
    indices = np.r_[np.arange(obj.size),len(v)-1]
    old_v = v[indices]
    old_score,old_gradient = original.evaluate(old_v)
    score,gradient = obj.evaluate(v)
    np.testing.assert_allclose(score,old_score,atol=1e-8,rtol=0)
    np.testing.assert_allclose(gradient[indices],old_gradient,atol=1e-9,rtol=1e-12)
    h = obj.curvature(v)
    np.testing.assert_allclose(h[np.ix_(indices,indices)],original.curvature(old_v),atol=1e-8,rtol=1e-12)


def satellite_rows(obj,data,record):
    v = np.asarray(record['vector'])
    obj.evaluate(v)
    likelihood = obj.likelihood.last_result
    by_group = dict(zip(likelihood['group_values'],likelihood['log_likelihood']))
    row_nll = -np.array([by_group[g] for g in data.group])
    pred,_ = obj.base.predict(v[:obj.size])
    pred += obj.likelihood.correction()
    alias = obj.likelihood.alias_hz
    e = (data.measured[:,None]-pred+alias/2)%alias-alias/2
    result = []
    for j,n in enumerate(data.numbers):
        rows = data.owners==n
        t = data.times[rows]-obj.time_centers[j]
        design = np.c_[np.ones(sum(rows)),t,t**2]
        y = e[rows,j]
        linear = y-design[:,:2]@np.linalg.lstsq(design[:,:2],y,rcond=None)[0]
        quad = y-design@np.linalg.lstsq(design,y,rcond=None)[0]
        result.append(dict(satellite=int(n),windows=int(sum(rows)),span_s=float(np.ptp(t)),
            drift_hz_s=float(v[obj.size+j]),owner_rms_hz=float(np.sqrt(np.mean(y**2))),
            owner_group_data_nll=float(row_nll[rows].sum()),
            linear_rms_hz=float(np.sqrt(np.mean(linear**2))),quadratic_rms_hz=float(np.sqrt(np.mean(quad**2))),
            curvature_ratio=float(np.linalg.norm(linear)/max(np.linalg.norm(quad),1e-12))))
    return result


def main(root=OUT):
    rows, tracks, cohort, pairs = [], [], [], []
    for scan in SCANS:
        data,meta,_ = load(scan)
        cases = {}
        for arm in ARMS:
            for mode in MODES:
                path = root/f'{scan}-{arm}-{mode}.json'
                r = json.loads(path.read_text())
                cases[arm,mode] = r
                assert r['input_sha256']==meta['input_sha256']
                assert r['numbers']==data.numbers.tolist()
                assert r['fit_original_rows']==r['evaluation_original_rows']==data.original_rows.tolist()
                assert not r['heldout_original_rows']
                assert r['maximum_budgets_s']==BUDGET
                assert r['source_sha256']==digest(Path(r['source']))
                assert r['implementation_sha256']==digest(OUT.parent/'satellite_drift_localization.py')
                if root!=OUT:
                    assert r['pre_polish_source_sha256']==digest(OUT/path.name)
                    assert r['extra_polish_budget_s']==30.
                    assert r['polish_implementation_sha256']==digest(OUT.parent/'polish_satellite_drift.py')
                assert r['slope_prior_sigma_hz_s']==SLOPE_SIGMA_HZ_S
                assert r['slope_reference_rf_hz']==REFERENCE_RF_HZ
                assert r['roof_starts']==r['spatial_starts']==3
                assert r['radius_km']==4.
                assert r['total_timing_bound_s']==20. and r['common_timing_bound_s']==10.
                obj = SatelliteDriftObjective(data,meta['rf_center_hz'],arm,mode)
                np.testing.assert_array_equal(obj.time_centers,r['slope_time_centers_s'])
                verify_zero_drift(obj,data,meta,arm,r['best'])
                values = diagnostics(obj,data,r['best'])
                for key,value in values.items():
                    np.testing.assert_allclose(value,r[key],atol=1e-7,rtol=0,err_msg=f'{scan} {arm} {mode} {key}')
                assert np.linalg.norm(r['best']['point_km'])<=4.+1e-7
                assert np.max(abs(np.asarray(r['best']['parameters'])[6:]))<=20.+1e-7
                assert abs(r['best']['vector'][6])<=10.+1e-7
                np.testing.assert_array_equal(r['best']['satellite_drift_hz_s'],r['best']['vector'][obj.size:-1])
                if arm=='zero-c':assert r['best']['vector'][-1]==0.
                if mode=='control':assert np.all(np.asarray(r['best']['satellite_drift_hz_s'])==0.)
                probabilities = obj.likelihood.last_result['row_association_probability']
                owners = np.array([np.flatnonzero(data.numbers==n)[0] for n in data.owners])
                strong = probabilities.max(axis=1)>.5
                ownership = dict(posterior_weight_sum=float(probabilities.sum()),
                    strong_changed_owner_windows=int(sum(strong & (probabilities.argmax(axis=1)!=owners))),
                    low_posterior_windows=int(sum(~strong)))
                information = geometry(obj,r['best'])
                row = dict(scan=scan,arm=arm,mode=mode,windows=len(data.times),satellites=len(data.numbers),
                    **values,**information,**ownership,receipt_sha256=digest(path))
                rows.append(row)
                tracks.extend(dict(scan=scan,arm=arm,mode=mode,**t) for t in satellite_rows(obj,data,r['best']))
            a,b = [cases[arm,m] for m in MODES]
            pairs.append(dict(scan=scan,arm=arm,error_change_m=b['distance_m']-a['distance_m'],
                data_nll_change=b['data_nll']-a['data_nll'],objective_change=b['objective']-a['objective'],
                owner_rms_change_hz=b['owner_rms_hz']-a['owner_rms_hz'],
                both_converged=a['converged'] and b['converged']))
        for r in cases.values():
            for key in ('input_sha256','numbers','fit_original_rows','evaluation_original_rows',
                        'maximum_budgets_s','slope_time_centers_s'):
                assert r[key]==cases['fitted-c','control'][key],(scan,key)
    assert len(rows)==64
    for arm in ARMS:
        for mode in MODES:
            part = [r for r in rows if (r['arm'],r['mode'])==(arm,mode)]
            errors = np.array([r['distance_m'] for r in part])
            cohort.append(dict(arm=arm,mode=mode,scans=len(part),
                median_error_m=float(np.median(errors)),mean_error_m=float(np.mean(errors)),
                below_1km=int(sum(errors<1000)),
                converged_below_1km=sum(r['distance_m']<1000 and r['converged'] for r in part),
                unconverged=sum(not r['converged'] for r in part),boundary=sum(r['boundary'] for r in part),
                pooled_owner_rms_hz=float(np.sqrt(sum(r['windows']*r['owner_rms_hz']**2 for r in part)/sum(r['windows'] for r in part))),
                pooled_posterior_weighted_rms_hz=float(np.sqrt(sum(r['posterior_weight_sum']*r['posterior_weighted_rms_hz']**2 for r in part)/sum(r['posterior_weight_sum'] for r in part))),
                strong_changed_owner_windows=sum(r['strong_changed_owner_windows'] for r in part),
                low_posterior_windows=sum(r['low_posterior_windows'] for r in part),
                median_drift_rms_hz_s=float(np.median([r['satellite_drift_rms_hz_s'] for r in part]))))
    report = dict(status='passed',cases=len(rows),converged=sum(r['converged'] for r in rows),
        cohort=cohort,rows=rows,pairs=pairs,notes=[
        'Original baseline observations and satellite banks; no reassignment, drops or folds in these position fits.',
        'Archived fold-derived upstream RX calibration remains fixed. Not an end-to-end no-fold calibration comparison.',
        'Independent 4 km searches, matched RF/model budgets, unchanged timing priors/bounds.',
        'One global Gaussian slope sigma 2 Hz/s, shared by receivers and scaled to actual RF; not fitted to position truth.',
        'Residual polynomial ratios are in-sample, pooled-channel diagnostics, not validation of satellite identity.',
        'Original owners remain input labels, not hard constraints: the unchanged finite-set position loss can reassign or favor clutter. Posterior >0.5 counts are diagnostics, not new coverage.',
        'Owner-group NLL partitions the complete mixture likelihood by original labels. It is bookkeeping, not causal attribution to one satellite.',
        'Profile Fisher scales are conditional approximations, not calibrated confidence regions or global-minimum certificates.',
        'A passed reconstruction audit does not mean every optimization converged.'])
    (root/'audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    for name,values in [('summary.csv',rows),('satellite-summary.csv',tracks),('paired-changes.csv',pairs)]:
        keys = list(dict.fromkeys(k for r in values for k in r))
        with (root/name).open('w',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=keys)
            writer.writeheader();writer.writerows(values)
    print(json.dumps(dict(converged=report['converged'],cohort=cohort),default=serial,indent=2))
    render(report,root)


def render(report,root=OUT):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig,axes = plt.subplots(2,1,figsize=(15,9),sharex=True,sharey=True)
    for ax,arm in zip(axes,ARMS):
        for i,s in enumerate(SCANS):
            cases = [next(r for r in report['rows'] if (r['scan'],r['arm'],r['mode'])==(s,arm,m)) for m in MODES]
            ax.plot([i-.12,i+.12],[r['distance_m'] for r in cases],c='.7',lw=1)
            for dx,r,color in zip([-.12,.12],cases,['#777777','#0072b2']):
                ax.scatter(i+dx,r['distance_m'],c=color,s=46,marker='^' if r['boundary'] else 'o')
                if not r['converged']:ax.scatter(i+dx,r['distance_m'],c='black',s=58,marker='x')
            ax.annotate(f"{cases[1]['distance_m']:.0f}",(i+.12,cases[1]['distance_m']),xytext=(0,8),textcoords='offset points',ha='center',fontsize=9)
        summaries = [next(r for r in report['cohort'] if (r['arm'],r['mode'])==(arm,m)) for m in MODES]
        ax.set_title(('Fitted c' if arm=='fitted-c' else 'c = 0')+' · converged below 1 km: '+
            ' → '.join(str(r['converged_below_1km']) for r in summaries)+' of 16')
        ax.axhline(1000,c='.4',ls='--');ax.axhline(4000,c='.5',ls=':')
        ax.set_ylim(0,4450);ax.set_ylabel('Best-found position error (m)');ax.grid(axis='y',alpha=.2)
    axes[-1].set_xticks(range(16),SCANS)
    handles = [Line2D([],[],color=c,marker=m,ls='none',label=l) for c,m,l in
        [('#777777','o','Original model control'),('#0072b2','o','Per-satellite slope prior σ = 2 Hz/s'),
         ('black','x','Unconverged'),('.4','^','4 km boundary')]]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.055),ncol=4,frameon=False)
    fig.suptitle('Does allowing correlated satellite residual drift reduce position bias?',fontsize=17)
    fig.text(.5,.012,'All original associated top-one windows fitted; identical data/bank, upstream RX calibration and timing priors. No coverage change.\n'
        'One slope per satellite shared across RX/channels; Gaussian prior fixed before this run. Independent, matched 4 km local searches.\n'
        'No truth-position prior, held-out rows, per-scan model choice or global-minimum certificate.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.11,1,.95));fig.savefig(root/'position-comparison.png',dpi=165);plt.close(fig)
    fig,axes = plt.subplots(1,2,figsize=(12,5),sharey=True)
    for ax,arm in zip(axes,ARMS):
        for pair in [p for p in report['pairs'] if p['arm']==arm]:
            x,y = -pair['data_nll_change'],pair['error_change_m']
            ax.scatter(x,y,c='#0072b2',s=42)
            if not pair['both_converged']:ax.scatter(x,y,c='black',s=55,marker='x')
            ax.annotate(pair['scan'],(x,y),xytext=(5,4),textcoords='offset points',fontsize=8)
        ax.axhline(0,c='.5',lw=1);ax.grid(alpha=.15)
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0')
        ax.set_xlabel('Data NLL reduction (positive = better frequency fit)')
    axes[0].set_ylabel('Position error change (m; negative = better)')
    fig.suptitle('A better full-data frequency fit need not give a better location',fontsize=14)
    fig.text(.5,.015,'Identical windows and satellite bank in each pair. × = at least one unconverged fit. In-sample diagnostic, not held-out validation.',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.055,1,.93));fig.savefig(root/'fit-quality-vs-position.png',dpi=165);plt.close(fig)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--polished',action='store_true');args=parser.parse_args()
    main(OUT/'polished' if args.polished else OUT)
