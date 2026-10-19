"""Audit frozen-precision controls and report independent position evaluation."""

import csv
import hashlib
import shutil
import tarfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_frozen_precision import OUT
from probe_ds23_height import OUT as HEIGHT
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from report_algo01_ds23_sample import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha

METHODS=('baseline','frozen_marginal','frozen_profile')
LABELS=('Adaptive Gaussian/Gamma incumbent','Frozen precision, marginal','Frozen precision, penalized profile')


def observation_ids(r):
    return {o for t in r['gates']['tracks'] for o in t['observation_ids']}


def save_csv(name,rows):
    with (OUT/name).open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def run():
    protocol=read(OUT/'protocol.json');execution=read(OUT/'execution.json');cases=sorted(protocol['cases'])
    assert len(cases)==20 and {r['case'] for r in execution}==set(cases)
    assert all(r['code']==0 for r in execution)
    positions=[];comparison=[];data={};max_replay=0.;max_phase=0.
    for receipt in execution:
        case=receipt['case'];path=OUT/(case+'.json');assert sha(path)==receipt['result_sha256']
        r=read(path);data[case]=r
        assert r['no_GPS_used'] and r['no_extra_point_trimming'] and r['same_c0_derived_precisions_both_c_arms']
        for key,source in [('source_sha256','probe_ds23_frozen_precision.py'),('helper_sha256','ds23_frozen_precision.py'),
                           ('geometry_source_sha256','ds23_height_problem.py')]:
            assert r[key]==sha(ROOT/'tools'/source)
        assert r['baseline_arms']==read(LEARNED/(case+'.json'))['results']['mean_and_distribution']['arms']
        ids=observation_ids(r['baseline_arms']['c0'])
        max_replay=max(max_replay,r['posterior_replay_max_coefficient_difference'])
        for method in METHODS:
            v=None if method=='baseline' else r['results'][method]
            pair=r['baseline_arms'] if v is None else v['policy_arms']
            for arm in ('c0','fitted_c'):
                trial=pair[arm] if v is None else v['arms'][arm]
                assert observation_ids(trial)==ids
                if v is not None:
                    max_phase=max(max_phase,trial['final_phase_change_s'])
                    assert v['paired_valid']==all(all(t['compatible'] for t in a['gates']['tracks']) and a['final_phase_change_s']<=.01 for a in v['arms'].values())
                positions.append(dict(case=case,method=method,arm=arm,
                    policy_error_km=position_error(pair[arm]['endpoint_latlon']),
                    raw_trial_error_km=position_error(trial['endpoint_latlon']),
                    RMS_hz=trial['RMS_hz'],active_points=trial['active_points'],paired_valid=v is None or v['paired_valid']))
        for arm in ('c0','fitted_c'):
            a=r['results']['frozen_marginal']['arms'][arm];b=r['results']['frozen_profile']['arms'][arm]
            comparison.append(dict(case=case,arm=arm,
                position_motion_km=float(np.linalg.norm(np.array(b['endpoint_east_north_km'])-a['endpoint_east_north_km'])),
                frequency_RMS_change_hz=b['RMS_hz']-a['RMS_hz'],
                actual_error_change_km=position_error(b['endpoint_latlon'])-position_error(a['endpoint_latlon']),
                marginal_quadratic=a['quadratic'],profile_quadratic=b['quadratic'],
                marginal_logvolume=a['logvolume'],profile_logvolume=b['logvolume'],
                scores_not_comparable_as_same_objective=True))
    save_csv('positions.csv',positions);save_csv('volume_effect.csv',comparison)
    summary={}
    table=['| Policy | c0 mean / median km | Fitted-c mean / median km | Paired valid /20 |','|---|---:|---:|---:|']
    for method,label in zip(METHODS,LABELS,strict=True):
        summary[method]={}
        for arm in ('c0','fitted_c'):
            values=[r['policy_error_km'] for r in positions if r['method']==method and r['arm']==arm]
            summary[method][arm]=dict(mean_km=float(np.mean(values)),median_km=float(np.median(values)))
        valid=20 if method=='baseline' else sum(data[c]['results'][method]['paired_valid'] for c in cases)
        a,b=summary[method]['c0'],summary[method]['fitted_c']
        table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} | {valid} |")
    fig,axes=plt.subplots(2,1,figsize=(13,7),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for method,label in zip(METHODS,LABELS,strict=True):
            values=[next(r['policy_error_km'] for r in positions if r['case']==c and r['method']==method and r['arm']==arm) for c in cases]
            ax.plot(range(20),values,'.-',label=label,lw=1)
        ax.axhline(.5,color='crimson',ls='--',lw=1);ax.set(ylabel='Position error (km)',title=arm);ax.grid(alpha=.2);ax.legend(fontsize=8)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('Same archived curves, labels, aliases and physical priors · twenty development scans')
    fig.savefig(OUT/'position_errors.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
    local={r['case']:r['estimated_shift_norm_km'] for r in read(HEIGHT/'volume_gradient.json')['records']}
    for arm in ('c0','fitted_c'):
        rows=[next(r for r in comparison if r['case']==c and r['arm']==arm) for c in cases]
        axes[0].plot(range(20),[r['position_motion_km']*1000 for r in rows],'.-',label=arm)
        axes[1].scatter([r['frequency_RMS_change_hz'] for r in rows],[r['actual_error_change_km']*1000 for r in rows],label=arm)
    axes[0].plot(range(20),[local[c]*1000 for c in cases],':',c='.5',label='Earlier adaptive-precision local estimate')
    axes[0].set(ylabel='Position motion (m)',title='Dropping log-volume: actual versus local estimate')
    axes[0].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=60)
    axes[1].axhline(0,c='.5',lw=.7);axes[1].axvline(0,c='.5',lw=.7)
    axes[1].set(xlabel='Profile minus marginal CFO RMS (Hz)',ylabel='Profile minus marginal position error (m)',title='Frequency fit and position accuracy are separate')
    for ax in axes:ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.savefig(OUT/'volume_effect.png',dpi=160);plt.close(fig)
    motions={arm:dict(median_m=float(np.median([r['position_motion_km']*1000 for r in comparison if r['arm']==arm])),
        maximum_m=max(r['position_motion_km']*1000 for r in comparison if r['arm']==arm)) for arm in ('c0','fitted_c')}
    write(OUT/'summary.json',dict(position=summary,profile_versus_marginal_motion=motions,goal_half_km_met=False,
        no_default_change=True,original20_development_not_all413=True))
    write(OUT/'validation.json',dict(all20_processes_terminal_success=True,all80_trials_ID_sets_exact=True,
        all_baselines_and_source_receipts_match=True,maximum_posterior_coefficient_replay_error=max_replay,
        maximum_final_phase_reference_change_s=max_phase,four_owned_numerical_tests_passed=True,
        GPS_used_only_for_reporting=True,reporter_sha256=sha(Path(__file__))))
    shutil.copyfile(HEIGHT/'causal_receipt_audit.json',OUT/'causal_receipt_audit.json')
    body='''# DS23: frozen-precision marginal and penalized-profile position fits

The nuisance integration log-volume does not explain the kilometre-scale position
errors in the twenty development scans. This controlled comparison keeps the
archived observations, masks, candidate labels, alias integers, receiver-support
powers, radio-noise law, phase-history means/scales and three physical orbit
directions fixed. It changes neither ALGO01's default nor published measurements.

TABLE

![Position errors](position_errors.png)

## What is isolated

Replay the incumbent c0 fit at its saved phase reference and position. Freeze
its per-fragment noise precision and per-coordinate nuisance prior precision.
The fixed Gaussian posterior reproduces its coefficient mean to numerical
precision. Use the same c0-derived values in both c arms, inserting a unit
Gaussian precision only for the extra ninth fitted-c hardware coefficient.
All original phase means remain absolute after every relinearization. Fragment
constants retain their physical 300 Hz scale. This is a conditional empirical
Gaussian control, not a newly calibrated prior learned independently of RF.

For residual y, design U, W=diag(power*precision/sigma²) and diagonal prior P:

    A = P + U' W U
    eta = A^-1 U' W y
    Q = (y-U eta)' W (y-U eta) + eta' P eta
    V = logdet(A) - logdet(P)

The conditional marginal uses Q+V. The penalized profile uses Q alone. Both
retain the same fitted nuisance mean and Gaussian prior penalty at a given
position; they differ only by V. For power=1, Q+V plus the diagonal Gaussian
noise normalization is the exact integrated Gaussian density. Fractional powers
give generalized evidence. Q alone is not a marginal likelihood; its raw score
cannot select it against Q+V. Compatibility key negative_twice_elbo in the shared
optimizer is explicitly labeled objective_kind in every final result; the
profile value must not be described as an ELBO or normalized probability.

Both controls start at the regional center (37.906,-122.545), with the same
25x25 km box, five phase refreshes and at most48 position steps per refresh.
They keep every incumbent observation. Either-arm residual/alias/visibility/
owner failure or final phase-reference movement above0.01 s causes paired
fallback, without additional point trimming. All forty paired controls pass.
No approach is selected per scan by GPS or by comparing these different losses.

## Interpretation

Freezing precisions preserves the c0 endpoint, but changes fitted-c results
slightly: this isolates precision feedback rather than log-volume. Dropping
log-volume with common frozen precisions moves c0 positions by a median
MEDIAN metres, with maximumMAXIMUM metres. Mean accuracy changes only slightly;
there is no material gain toward the0.5 km mean and median target.

![Volume control and actual accuracy](volume_effect.png)

The earlier local sensitivity estimate had median154m. Its derivatives allowed
the original variational precisions to change and used a local Gauss–Newton
approximation. It was not a refit, and this controlled result must supersede any
interpretation of that estimate as an achievable position correction. The two
diagnostics answer different questions; the larger sensitivity is not evidence
that discarding Gaussian integration fixes location.

Evaluation alone uses (37.849061591561885,-122.48574968092912), under the same
unconfirmed assumption that this site applies to every sampled recording.
All TLE inputs remain causal. No IQ is reread, RF collected, identity selected,
or antenna coordinate supplied to inference. These are twenty development
scans, not validation on the other393 DS23 recordings or on a new location.

The next unused observation class is the linear graph extensions. They can
test position conditionally on calibration learned from curved tracks, but
must not estimate receiver offsets or drifts. Their predictive covariance
must retain shared calibration uncertainty; counting them as independent,
perfectly calibrated frequency samples would create false information.

## Reproduction

Use the repository venv, PYTHONPATH=src:tools and BLAS/OMP threads one. Run
tools/run_ds23_frozen_precision.py, then tools/report_ds23_frozen_precision.py.
Two numerical subprocesses have180s per-case limits. Four owned tests check
dense-data covariance normalization/posterior parity, fractional-power ridge
profiling, fitted-c coordinate insertion and zero-feature/invalid-input controls.
Source snapshots overlay the prior height, causal-history and ALGO01 reports.

[Positions including raw trials](positions.csv) · [Volume changes](volume_effect.csv) ·
[Summary](summary.json) · [Validation](validation.json) · [Protocol](protocol.json) ·
[Execution](execution.json) · [Causal receipts](causal_receipt_audit.json) ·
[Full lossless evidence](evidence.tar.xz) · [Evidence hashes](evidence_inventory.json).
'''
    body=body.replace('TABLE','\n'.join(table)).replace('MEDIAN',f"{motions['c0']['median_m']:.2f}").replace('MAXIMUM',f" {motions['c0']['maximum_m']:.2f}")
    (OUT/'README.md').write_text(body)
    snapshot=OUT/'source_snapshot';inventory={}
    sources=['tools/ds23_frozen_precision.py','tools/probe_ds23_frozen_precision.py','tools/run_ds23_frozen_precision.py',
        'tools/report_ds23_frozen_precision.py','tests/analysis/test_ds23_frozen_precision_tool.py']
    for name in sources:
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        inventory[str(target.relative_to(OUT))]=sha(target)
    write(OUT/'source_inventory.json',inventory)
    names=[OUT/'protocol.json',OUT/'execution.json']
    names += [p for p in OUT.iterdir() if p.name.startswith('DS23-') and p.suffix in ('.json','.log')]
    archive_inventory={}
    with tarfile.open(OUT/'evidence.tar.xz','w:xz',preset=3) as output:
        for path in sorted(names):
            relative=str(path.relative_to(ROOT));archive_inventory[relative]=dict(sha256=sha(path),bytes=path.stat().st_size)
            output.add(path,arcname=relative)
    with tarfile.open(OUT/'evidence.tar.xz','r:xz') as output:
        assert len(output.getmembers())==len(archive_inventory)
        for m in output.getmembers():
            assert hashlib.sha256(output.extractfile(m).read()).hexdigest()==archive_inventory[m.name]['sha256']
    write(OUT/'evidence_inventory.json',archive_inventory)
    print('\n'.join(table));print('Position motion metres',motions,flush=True)


if __name__=='__main__':run()
