"""Read-only endpoint/observability review of DS23's two largest outliers.

No position optimization, association selection, new measurements or prior
changes. Local information uses curved calibration only, with fixed robust
precisions and labels. Counterfactual known blocks are diagnostics, not fits.
"""

from pathlib import Path
import csv
import hashlib

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ds23_position_information import marginal_position_information, ellipse_scales
from dsx01_joint_marginal import JointMarginal
from probe_ds23_worst_association_bottleneck import setup, build
from run_algo01_ds23_sample import ROOT, read, write

OUT = ROOT/'reports/2026_10_23_ds23_worst_outlier_review'
SOURCE = ROOT/'reports/2026_10_22_ds23_dbg01_iteration_001'
CASES = ['DS23-0081', 'DS23-0326']


def central_design(prediction, position, step):
    x = np.asarray(position, float)
    return np.column_stack([(prediction(x + step*e)-prediction(x-step*e))/(2*step)
                            for e in np.eye(2)])


def csv_write(path, rows):
    with path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def one(case):
    d = setup(case)
    archive = read(SOURCE/'evidence'/case/'DBG01_audit.json')
    records, tracks, information = [], [], []
    for arm, saved in archive['arms'].items():
        for location in ['endpoint', 'diagnostic_point']:
            original = saved[location]
            p = build(d, arm, original['phase_reference'])
            x = np.asarray(original['endpoint_east_north_km'])
            c = p.calculate(x)
            replay_error = float(c['negative_twice_elbo']-original['negative_twice_elbo'])
            if abs(replay_error) > 1e-5:
                raise ValueError(f'{case} {arm} {location}: endpoint replay changed')
            coef = c['coefficient']
            def predict(position):
                geo = JointMarginal.calculate(p, position)
                return p.q*geo['intercept'] + geo['features']@coef
            j = central_design(predict, x, .02)[p.keep]
            finer = central_design(predict, x, .01)[p.keep]
            derivative_error = float(np.linalg.norm(j-finer)/max(np.linalg.norm(finer), 1e-15))
            if derivative_error > 1e-4:
                raise ValueError('position derivative did not stabilize')
            u = c['features'][p.keep]
            w = d['powers'][p.noise_groups[p.keep]]*c['noise_precision'][p.noise_groups[p.keep]]/p.point_noise[p.keep]**2
            prior = c['coefficient_prior_precision']
            nb, ns, nl, no = p.hardware.shape[1], p.smooth.shape[1], len(p.labels), 3*len(p.supported)
            blocks = dict(radio=np.arange(nb), smooth=np.arange(nb, nb+ns),
                          phase=np.arange(nb+ns, nb+ns+nl),
                          orbit=np.arange(nb+ns+nl, nb+ns+nl+no),
                          fragment=np.arange(nb+ns+nl+no, u.shape[1]))
            full = marginal_position_information(finer, u, w, prior)
            raw = finer.T@(w[:,None]*finer)
            # An independent Schur calculation verifies the QR projection.
            cross = finer.T@(w[:,None]*u)
            schur = raw-cross@np.linalg.solve(np.diag(prior)+u.T@(w[:,None]*u), cross.T)
            parity = float(np.linalg.norm(full-schur)/max(np.linalg.norm(full), 1e-15))
            if parity > 1e-5:
                raise ValueError('independent Schur/QR information mismatch')
            for label, known in [('All nuisances uncertain', np.array([], int))] + [(k+' known', v) for k,v in blocks.items()] + [('All nuisances known', np.arange(u.shape[1]))]:
                use = np.setdiff1d(np.arange(u.shape[1]), known)
                info = marginal_position_information(finer, u[:,use], w, prior[use])
                if np.linalg.eigvalsh(info-full).min() < -1e-7:
                    raise ValueError('knowing nuisance coefficients lost information')
                scales = ellipse_scales(info)
                information.append(dict(case=case, arm=arm, location=location, control=label,
                    major_local_sigma_km=scales['major_local_sigma_km'],
                    minor_local_sigma_km=scales['minor_local_sigma_km'],
                    retained_trace_fraction=float(np.trace(info)/np.trace(raw))))
            for k,(row,sl) in enumerate(zip(p.rows,p.slices,strict=True)):
                active = p.keep[sl]
                if not active.any(): continue
                track = p.scan.tracks[p.members[k]]
                residual = c['conditional_residual_hz'][sl][active]
                time = track['times'][active]
                smooth = (c['features'][sl,nb:nb+ns]@coef[nb:nb+ns])[active]
                tracks.append(dict(case=case,arm=arm,location=location,component=row['component'],
                    norad=row['candidate_norad'],receiver=track['receiver'],channel=track['channel'],
                    rf_ghz=track['rf_hz']/1e9,points=int(active.sum()),start_s=float(time.min()),
                    end_s=float(time.max()),span_s=float(np.ptp(time)),pieces=len(track['pieces']),
                    likelihood_power=float(d['powers'][k]),noise_precision=float(c['noise_precision'][k]),
                    median_noise_sigma_hz=float(np.median(p.point_noise[sl][active])),
                    residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
                    maximum_residual_energy_fraction=float(np.max(residual**2)/np.sum(residual**2)),
                    smooth_min_hz=float(smooth.min()),smooth_max_hz=float(smooth.max())))
            records.append(dict(case=case,arm=arm,location=location,position=x,
                replay_difference=replay_error,derivative_relative_change=derivative_error,
                independent_information_relative_difference=parity,
                curved_points=int(p.keep.sum()),predictive_points_omitted_from_local_information=sum(e['points'] for e in d['entries']),
                sum_likelihood_powers=float(np.sum(d['powers'][p.noise_groups[p.keep]])),
                information=full,raw_information=raw,
                conditional_on_Gamma_labels_priors_and_linearization=True,
                not_calibrated_position_uncertainty=True))
    return records, tracks, information


def plots(tracks, info):
    fig, axes = plt.subplots(2,1,figsize=(12,8),gridspec_kw={'height_ratios':[4,1]},constrained_layout=True)
    for ax,case in zip(axes,CASES,strict=True):
        rows = [r for r in tracks if r['case']==case and r['arm']=='fitted_c' and r['location']=='endpoint']
        labels=sorted({r['norad'] for r in rows});colors={n:plt.get_cmap('tab10')(k) for k,n in enumerate(labels)}
        for k,r in enumerate(rows):
            ax.plot([r['start_s'],r['end_s']],[k,k],c=colors[r['norad']],lw=5,solid_capstyle='butt')
            ax.text(r['end_s']+2,k,f"{r['points']} pts; power {r['likelihood_power']:g}",va='center',fontsize=8)
        ax.set_yticks(range(len(rows)),[f"{r['norad']} RX{r['receiver']} CH{r['channel']}" for r in rows],fontsize=8)
        ax.set(xlim=(0,350),xlabel='Time in scan (s)',title=f'{case}: accepted curved sources, published reference')
        ax.grid(axis='x',alpha=.25);ax.invert_yaxis()
    fig.suptitle('Coverage is concentrated in satellite/time blocks; spans do not imply continuous sampling')
    fig.savefig(OUT/'figures/calibration_timeline.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.7),constrained_layout=True)
    for ax,case in zip(axes,CASES,strict=True):
        rows=[r for r in info if r['case']==case and r['arm']=='fitted_c' and r['location']=='endpoint']
        ax.barh(np.arange(len(rows)),[r['major_local_sigma_km'] for r in rows],color='#526da8')
        ax.set_yticks(np.arange(len(rows)),[r['control'] for r in rows]);ax.invert_yaxis();ax.set_xscale('log')
        ax.set_xlim(.005,20);ax.set_xticks([.01,.1,1,10],['0.01','0.1','1','10']);ax.minorticks_off()
        for i,r in enumerate(rows):ax.text(r['major_local_sigma_km']*1.05,i,f"{r['major_local_sigma_km']:.3f}",va='center',fontsize=8)
        ax.axvline(.5,c='gray',ls=':');ax.set(title=case,xlabel='Weak-axis local scale (km); smaller means more information')
        ax.grid(axis='x',alpha=.2)
    fig.suptitle('Curved data only: nuisance coefficients frozen one block at a time\nLocal Gaussian sensitivity, NOT a confidence interval or achieved error',fontsize=12)
    fig.savefig(OUT/'figures/local_information.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
    for ax,case in zip(axes,CASES,strict=True):
        a=read(SOURCE/'evidence'/case/'DBG01_audit.json')['arms']['fitted_c']
        old=a['endpoint']['decomposition']['terms'];ref=a['diagnostic_point']['decomposition']['terms']
        keys=['weighted_data','prior_smooth','noise_Gamma','prior_fragment','prior_orbit','prior_phase','prior_drift','logvolume','prior_Gamma','predictive_linear','prior_offset','prior_c']
        values=[ref[k]-old[k] for k in keys]
        ax.barh(range(len(keys)),values,color=['#b64c50' if v>0 else '#447cac' for v in values]);ax.axvline(0,c='black',lw=.6)
        ax.set_yticks(range(len(keys)),[k.replace('_',' ') for k in keys],fontsize=8);ax.invert_yaxis()
        ax.set(title=f'{case}: total preference {sum(values):.2f}',xlabel='Loss at true site − loss at returned boundary')
        ax.grid(axis='x',alpha=.2)
    fig.suptitle('Why the current fitted-c model prefers the wrong position\nPositive bars favor the returned boundary; coupled terms are not independent causal effects',fontsize=12)
    fig.savefig(OUT/'figures/objective_preference.png',dpi=150);plt.close(fig)


def main():
    for part in ['figures','tables','evidence','source']:(OUT/part).mkdir(exist_ok=True,parents=True)
    records,tracks,info=[],[],[]
    for case in CASES:
        a,b,c=one(case);records.extend(a);tracks.extend(b);info.extend(c)
        print(case,'replayed and information audited',flush=True)
    write(OUT/'evidence/local_review.json',dict(records=records,no_new_position_fits=True,
        no_changed_associations_or_priors=True,all_replay_and_information_checks_passed=True))
    csv_write(OUT/'tables/calibration_tracks.csv',tracks);csv_write(OUT/'tables/local_information.csv',info)
    plots(tracks,info)
    paths=[Path(__file__),ROOT/'tools/ds23_position_information.py']+[SOURCE/'evidence'/c/'DBG01_audit.json' for c in CASES]
    write(OUT/'evidence/inputs.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


if __name__=='__main__':main()
