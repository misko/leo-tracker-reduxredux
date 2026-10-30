"""Publish target influence, native provenance and annotation-role inventory."""
import argparse,csv,gzip,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from evaluate_ds22_merged_tracks import digest


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    evidence={};hashes={}
    def load(p):
        v=read(p);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();evidence[str(p)]=compact_replays(compact_evidence(v));return v
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    root=s/'bundle-67634-influence-v1';protocol=load(root/'protocol.json')
    terminal=load(s/'bundle-67634-influence-v1-terminal.json');assert terminal['status']=='complete'
    trial=Path(protocol['source_trial']);control=load(trial/'control.json');original=load(trial/'new_family.json')
    base=load(root/'all.json');native=load(s/'bundle-67634-native-audit-v1/result.json')
    for source,digest_value in {**protocol['source_hashes'],**native['source_hashes']}.items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=digest_value:raise ValueError('upstream source changed')
    curves=[];rows=[];variants=['all','omit_largest_residual','omit_its_12s_block','member_0_only','member_1_only']
    for name in variants:
        r=load(root/(name+'.json'));curves.append(r)
        for arm,v in r['arms'].items():
            f=v['family'];d=f['diagnostics'][0];x=np.asarray(v['endpoint_east_north_km']);baseline=base['arms'][arm]
            if name=='all':np.testing.assert_array_equal(x,original['arms'][arm]['endpoint_east_north_km'])
            rows.append(dict(variant=name,arm=arm,points=r['points'],control_error_km=error(control['arms'][arm]),
                error_km=error(v),shift_from_all_points_m=float(1000*np.linalg.norm(x-baseline['endpoint_east_north_km'])),
                residual_RMS_hz=d['profile_RMS_hz'],target_noise_pass=all(g['compatible'] for g in f['gates']),
                optimizer_success=v['history'][-1]['success'],optimizer_message=v['history'][-1]['message'],
                phase_change_s=v['history'][-1]['phase_change_s'],quadrature_pass=v['phase_resolution_audit']['local_agreement'],
                phase_map_s=f['phase_map_s'],phase_sigma_s=f['phase_sigma_s'],
                incumbent_objective=v['negative_twice_elbo'],target_objective=f['negative_twice_log_density'],
                east_km=x[0],north_km=x[1]))
    csvout('position_sensitivity.csv',rows)
    point=next(r for r in native['observations'] if r['observation_id']==protocol['largest_residual_id'])
    rawpath=Path(native['job']['root'])/native['job']['case']/'tracking.json';document=read(rawpath)
    hashes[str(rawpath)]=hashlib.sha256(rawpath.read_bytes()).hexdigest();source=document['source']
    probes=[p for p in source['probes'] if digest(f"{source['session_id']}:{p['receiver_id']}:{p['valid_start_counter']}".encode())==point['observation_id']]
    assert len(probes)==1
    detail=dict(point=point,probe=probes[0],capture_mode=source['capture_mode'],sample_rate_hz=source['sample_rate_hz'],
        probe_ms=source['probe_ms'],source=str(rawpath),sha256=hashes[str(rawpath)])
    write(out/'suspect_native_point.json',detail)
    ledger=load(s/'annotation-likelihood-ledger-audit-v1/summary.json');load(s/'annotation-likelihood-ledger-audit-v1/review_queue.json')
    roles=s/'annotation-likelihood-ledger-audit-v1/roles.csv';hashes[str(roles)]=hashlib.sha256(roles.read_bytes()).hexdigest();shutil.copyfile(roles,out/'annotation_roles.csv')
    write(out/'ledger_summary.json',ledger)
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    names=['all','omit_largest_residual','member_0_only','member_1_only']
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        rr=[next(r for r in rows if r['variant']==name and r['arm']==arm) for name in names]
        ax.barh(np.arange(4),[r['error_km'] for r in rr],color=['#0072b2' if r['optimizer_success'] else '#e69f00' for r in rr])
        ax.axvline(error(control['arms'][arm]),color='k',ls='--',label='Control without target')
        ax.set(yticks=np.arange(4),yticklabels=['All 69 points','Omit isolated point (68)','Fragment 1 only (40)','Fragment 2 only (29)'],xlabel='Evaluation position error (km)',title=arm);ax.invert_yaxis();ax.set_xlim(0,2.8);ax.legend(fontsize=8);ax.grid(axis='x',alpha=.2)
        for k,r in enumerate(rr):ax.text(r['error_km']+.02,k,f"{r['error_km']:.3f}"+(' *' if not r['optimizer_success'] else ''),va='center',fontsize=8)
    fig.suptitle('67634 sensitivity: orange / * means optimizer failure; no point removal authorized')
    save(fig,'position_sensitivity.png')
    fig,axs=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    pts=native['observations'];tt=np.array([r['time_s'] for r in pts]);yy=np.array([r['aligned_CFO_hz'] for r in pts]);mm=np.array([r['member'] for r in pts])
    for m in (0,1):
        k=mm==m;axs[0,0].scatter(tt[k],yy[k]/1000,s=18,label=f'Original fragment {m+1}')
        axs[1,0].plot(tt[k],np.array([r['original_polynomial_residual_hz'] for r in pts])[k],'.-',lw=.6,label=f'Original degree-4 fragment {m+1}')
    d=base['arms']['fitted_c']['family']['diagnostics'][0]
    axs[0,0].plot(d['times_s'],(np.array(d['prediction_CFO_hz'])+d['profile_bias_hz'])/1000,c='k',lw=.9,label='67634 orbit + nuisance terms')
    for name,color in [('all','#0072b2'),('omit_largest_residual','#d55e00')]:
        d=next(v for v in curves if v['variant']==name)['arms']['fitted_c']['family']['diagnostics'][0]
        axs[0,1].plot(d['times_s'],np.array(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',c=color,lw=.7,label=name)
    axs[1,1].plot(tt,[r['uniform_timing_shift_hz'] for r in pts],'.',label='Uniform-frame centroid')
    axs[1,1].plot(tt,[r['maximum_support_timing_shift_hz'] for r in pts],label='Within-pilot support maximum',lw=.8)
    for ax,title,ylabel in zip(axs.flat,['Native GLRT curve and causal prediction','Orbital residual before/after diagnostic omission','Original graph-polynomial residual','First-order timing sensitivity'],['CFO (kHz)','Residual (Hz)','Residual (Hz)','Expected CFO shift (Hz)'],strict=True):
        ax.set(title=title,xlabel='Scan time (s)',ylabel=ylabel);ax.axvline(point['time_s'],c='#cc79a7',ls=':',lw=1);ax.grid(alpha=.2);ax.legend(fontsize=8)
    save(fig,'native_and_residuals.png')
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,key,title in zip(axs,['primary_roles','predictive_states'],['Primary annotation role (1,630 curves)','Predictive-role status (581 curves)'],strict=True):
        counts=ledger[key];ax.barh(range(len(counts)),list(counts.values()),color='#4477aa');ax.set(yticks=range(len(counts)),yticklabels=[k.replace('_',' ') for k in counts],xlabel='Curves',title=title);ax.invert_yaxis()
        for k,n in enumerate(counts.values()):ax.text(n,k,' '+str(n),va='center')
        ax.set_xlim(0,max(counts.values())*1.15)
    save(fig,'annotation_roles.png')
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    paired=[]
    for name in names:
        a=next(r for r in rows if r['variant']==name and r['arm']=='c0');b=next(r for r in rows if r['variant']==name and r['arm']=='fitted_c')
        paired.append(dict(variant=name,points=a['points'],c0_error_km=a['error_km'],fitted_c_error_km=b['error_km'],both_optimizers_success=a['optimizer_success'] and b['optimizer_success']))
    text=f'''# 67634 recovery sensitivity and the full annotation-role audit

The 69-point 67634 recovery is **not solely driven by its isolated early residual**. In the fitted-c arm, error changes from **2.479 km without this family to 2.226 km with all points**, and **2.327 km after omitting the isolated point**. Each original fragment also improves fitted-c error by itself. The point moves the fitted position by **101.7 m**, so its influence is material. This is a diagnostic sensitivity result, not permission to delete it, a new association, or an ALGO promotion.

Capture metadata says **adaptive, 10 MS/s**, despite the `fast8-auto` recording name. This result must not be counted as a new fast-scan validation gain. It belongs to the broader research inventory.

## Controlled position experiment

We reconstruct the immutable validated graph bundle and reproduce its all-point endpoint **exactly in both c arms**. Every diagnostic starts at the same regional center, uses the same causal catalogue, physical priors, 25 × 25 km bounds, five phase-refresh rounds, L-BFGS-B budget and 0.025-second phase integration. The target remains predictive evidence: it does not update receiver calibration at a fixed position. Both c arms receive identical subsets. GPS appears only in report-time error calculation.

The suspect is selected by largest absolute residual in the previously saved c=0 trial. Variants retain all points, omit that point, omit its fixed scan-time 12-second block, or retain each original fragment separately. This is **targeted influence analysis, not randomized validation**. The earlier randomized identity tests remain unchanged. The isolated point is the only target observation in its block, so point and block omission are exactly the same experiment; they are not independent corroboration.

{table(paired,['variant','points','c0_error_km','fitted_c_error_km','both_optimizers_success'])}

![Position sensitivity](figures/position_sensitivity.png)

The c=0 omission optimizer reports abnormal termination; its 2.341 km result is provisional, not a validated endpoint. The fitted-c omission optimizer succeeds. All ten diagnostic arm outputs pass target residual and phase-grid checks, but no fresh full ownership/exact-incumbent qualification was run for the altered subsets. They cannot replace the previously qualified all-point trial. Scores and position errors are reported separately in [position_sensitivity.csv](position_sensitivity.csv); raw objective magnitudes across different point counts are not a fair measure of localization quality. Lower target RMS (about 80 to 63 Hz after omission) accompanies worse evaluation position error.

The first fragment alone has 40 points and no isolated early point; fitted-c error is 2.410 km. The second has 29 points including the suspect; fitted-c error is 2.159 km. Both support a position pull in this case, but these conditional fits share the same incumbent calibration and are not independent location measurements. Their gains cannot be summed.

## Native evidence and what remains unexplained

![Native CFO, residual and timing audit](figures/native_and_residuals.png)

Exact winner replay verifies every target CFO and timestamp against archived acquisition output. Graph values differ from native measurements only by integer alias lifts; there is no frequency smoothing or accidental numeric mutation. The suspect at **{point['time_s']:.3f} s** has GLRT margin **{point['fractional_margin']:.3f}** and candidate rank 0. It is the only exported candidate passing the fractional-margin gate for that probe. This establishes detection evidence, not a proven satellite identity for that individual point. [Its archived candidate list](suspect_native_point.json) is retained.

Its original degree-4 polynomial residual is only **{point['original_polynomial_residual_hz']:.1f} Hz**, while its saved orbital residual is roughly 410–430 Hz across c arms. Thus a visually smooth polynomial is insufficient to establish orbital consistency, especially at an isolated endpoint. The other fragment starts about 13.5 seconds later, providing no simultaneous fragment witness at this point. This does not establish that the point is false or that the full join is wrong.

The within-pilot timestamp-support bound at this point is **{point['maximum_support_timing_shift_hz']:.1f} Hz**, and the uniform-frame centroid shift is **{point['uniform_timing_shift_hz']:.2f} Hz**. These are first-order sensitivities from the graph polynomial, not raw-IQ weighted timing estimates or absolute-clock validation. Ordinary within-probe centroid placement is far too small to explain a roughly 400 Hz discrepancy under that local slope. No extra LNB drift or orbital parameter is justified by this point alone. A bounded remeasurement of its existing IQ and adjacent probes, with frame consistency and a continuous CFO estimate, is the next direct measurement test.

## Audit of all 1,630 annotation records

The complete first assessment pass was real, but it did **not** establish that every curve had been validated in its eventual inclusion role. We read and hash each primary source rather than interpreting the ledger's original `state` column as an accepted association. Explicit predictive reassessment sources take precedence over original sources; filesystem modification times are not used. Separate fragment, bundle, partition and inclusion records remain distinct.

![Annotation roles](figures/annotation_roles.png)

Primary sources comprise **1,037 older calibration-participating annotations**, **581 predictive-only annotations**, and **12 records whose assessment is recorded through separate fragment evidence** rather than a primary whole-curve source. The 581 predictive primary assessments comprise 119 supported, 77 ambiguous, 49 unstable, 26 prediction mismatches and 310 insufficient-partition results. These counts describe the primary-source audit, not all historical research or production ownership.

The audit flags **985 records needing predictive-role review in the primary ledger** and **63 supported predictive identities without a recorded inclusion source**. These are **reconciliation queues, not claims that 1,048 curves have never been tested anywhere**. Older manual and cohort research may contain relevant trials not linked in the primary ledger; those must be reconciled before rerunning or crediting a recovery. Another 89 rows have recorded inclusion sources and 34 require separate-role/fragment reconciliation. No missing field is treated as a failed satellite test, and no old supported label is promoted automatically.

The full [role audit](annotation_roles.csv) and [summary with source hashes](ledger_summary.json) make this limitation explicit. The original ledger and trials remain unchanged. Next work should reconcile these sources, take the largest genuinely pending curves through predictive-role validation, and then run matched position inclusion for supported identities. That is a broader path than repeatedly tuning the same geometric fragment groups.

## Status

This iteration adds no association credit and makes no production change. It strengthens the evidence for the existing 69-point recovery while identifying one influential measurement that still deserves raw-IQ checking. The full goal remains incomplete. The five diagnostic variants completed in {terminal['seconds']:.1f} seconds; the focused regression suite passed 18 tests. [Source hashes](sources.json), [compact evidence](evidence.json.gz), native candidate metadata and all per-arm metrics accompany this report.
'''
    (out/'README.md').write_text(text)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
