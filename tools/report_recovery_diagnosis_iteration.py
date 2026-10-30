"""Publish receiver-transfer diagnosis, the CH7 counterexample and next ledger."""
import argparse,csv,gzip,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_omitted_predictive_recovery import target_diagnostic
from report_predictive_track_annotation import table
from report_predictive_role_reassessment import complete_replay_slacks
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();s=args.study;hashes={};evidence={};metrics=[];failures=[]
    def load(path):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();z=read(path);evidence[str(path)]=compact_replays(compact_evidence(z));return z
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n');w.writeheader();w.writerows(rows)
    root=s/'batch3-ch7-shared-refresh-v2';load(root/'protocol.json');execution=load(root/'execution.json')
    if len(execution)!=2 or any(r['status']!='complete' for r in execution):raise ValueError('shared-refresh trial not terminal')
    load(s/'batch3-ch7-shared-refresh-v1/execution.json')
    fig,axes=plt.subplots(1,2,figsize=(13,4),layout='constrained')
    for label,trial in [('Original',s/'reconciled-role-inclusion-v3/bfdf8ca6908647a6187d/trial'),('Shared satellite refresh',root/'trial')]:
        pr=load(trial/'protocol.json');control=load(trial/'control.json');addition=load(trial/'target_0.json');audit=load(trial/'exact_owner_replay.json')
        for path,digest in audit['source_hashes'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('replay source changed')
        for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
            c=control['arms'][arm];a=addition['arms'][arm];d=target_diagnostic(a)
            before=set(c['proposed_associated_ids']);after=set(a['proposed_associated_ids'])
            if before-after or after-before!=set(pr['targets'][0]['observation_ids']):raise ValueError('trial changes unexpected observations')
            metrics.append(dict(variant=label,arm=arm,control_error_km=error(c),addition_error_km=error(a),target_RMS_hz=d['RMS_hz'],
                control_paired_valid=control['paired_valid'],addition_paired_valid=addition['paired_valid'],exact_replay_pass=audit['all_verified'],added_points=len(after-before)))
            ax.plot(d['times_s'],d['residual_hz'],'.-',lw=.7,label=label)
            ax.set(title=arm,xlabel='Scan time (s)',ylabel='CH7 satellite residual (Hz)');ax.grid(alpha=.2);ax.axhline(0,c='k',lw=.5)
        for row in audit['rows']:
            for gate,slack in complete_replay_slacks(row).items():
                if slack<0:failures.append(dict(variant=label,role=row['role'],arm=row['arm'],gate=gate,slack=slack))
    for ax in axes:ax.legend(fontsize=8)
    fig.savefig(out/'figures/ch7_refresh.png',dpi=145);plt.close(fig)
    csvout('position_trials.csv',metrics);csvout('failed_gates.csv',failures)
    receiver=load(s/'independent-receiver-transfer-v1/result.json');graph=load(s/'graph-orbit-role-batch3-v1/result.json')
    ledger=list(csv.DictReader((args.previous/'annotation_ledger.csv').open()))
    for r in ledger:
        if r['track_id']=='bfdf8ca6908647a6187d':
            r['shared_family_refresh_source']=str(root/'trial')
            r['shared_family_refresh_status']='rejected; target and incumbent residual failures, including control'
    csvout('annotation_ledger.csv',ledger)
    shutil.copyfile(args.previous/'remaining_role_candidates.json',out/'remaining_role_candidates.json')
    summary=load(args.previous/'summary.json')
    write(out/'summary.json',dict(batch=summary,receiver_transfer_recovered_targets=0,shared_refresh_recovered_points=0,production_changed=False,goal_complete=False))
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    (out/'README.md').write_text(f'''# Recovery diagnosis: independent receiver transfer and shared-family consistency

This iteration advances the full large-track inventory and tests two concrete explanations for rejected curves. Neither tested correction justifies a new recovery. No production model, prior or acceptance threshold is changed.

## Other satellites do not supply the missing 60342 trend

The [receiver-transfer audit](../2026_10_30_independent_receiver_transfer/README.md) uses incumbent observations only to predict a receiver correction. At the refined 60342 inclusion endpoint, the fitted-c residual slope is **−2.922 Hz/s**. Incumbents supply **−0.241 Hz/s**, leaving **−2.681 Hz/s**. RMS changes from **23.99 to 22.23 Hz** and lag-one correlation from **0.822 to 0.805**, still above **0.686**. At the target-excluded control endpoint, the discrepancy is larger: **−4.975 Hz/s**, versus **−0.256 Hz/s** supplied by incumbents. V06 CH5 also retains its correlation failure.

![Receiver transfer](../2026_10_30_independent_receiver_transfer/figures/b1a4154c4ad9eb46.png)

Thus the difference between the gate's original receiver mean and the likelihood's incumbent-conditioned receiver mean is insufficient to explain these failures. This does not prove an orbital error or rule out receiver-model inadequacy. The projected receiver trend uncertainty is about 1.54 Hz/s for 60342, conditional on the existing empirical model; it is not independently calibrated confidence. No target-driven receiver posterior is adopted.

## Seven more supported identities still fail physical inclusion

The [third predictive-role batch](../2026_10_30_predictive_role_reassessment_batch3/README.md) finishes 16 more curves: **seven supported identities, five unstable identities, three ambiguous identities and one prediction mismatch**. All seven supported cases receive matched c=0/fitted-c position trials and exact replay. Every original control passes; every addition fails target residual checks. Three additions improve GPS error despite failing RF checks, so error improvement is not used to accept them. The batch comprises 15 fast curves and one adaptive curve according to verified acquisition provenance, not the compatibility export's capture-mode label. **{summary['remaining_role_candidates']} older-role cases remain**.

The failed-gate CSV now includes nominal and continuously refined new-family target screens. Previously this report's helper collected incumbent/shared-family failures only; the omitted target failures remained in the raw replay evidence and qualification decisions were already correct. The corrected report preserves the full failure inventory.

## The largest smooth mismatch: AUTO-afec5a1f RX1 CH7, 77 points

The [original-polynomial audit](../2026_10_30_graph_orbit_residuals/README.md) compares all seven supported curves without refitting their polynomials. This CH7 curve has **88 Hz polynomial RMS**, but **265 Hz satellite RMS** and about **251 Hz centered RMS difference between the predictions**. It is one original degree-four polynomial piece. That makes it a useful physical-model or identity challenge, but an in-sample polynomial cannot rule out source mixing or prove an identity.

![CH7 polynomial and orbital residuals](../2026_10_30_graph_orbit_residuals/figures/bfdf8ca6908647a6187d.png)

The predictive annotation selects **59632** in every random partition and both c arms, with minimum margin about **27.9** over its tested competitor. This is conditional evidence, not proof of family consistency. We applied the existing shared-satellite refresh prototype, which exposes the satellite posterior from predictive evidence while keeping receiver means unchanged. Both c arms, all points, priors, search budgets and the 25 × 25 km regional initialization are retained; no new free drift or arbitrary polynomial correction is introduced.

{table(metrics,['variant','arm','control_error_km','addition_error_km','target_RMS_hz','control_paired_valid','addition_paired_valid','exact_replay_pass'])}

![Shared-family refresh](figures/ch7_refresh.png)

The refresh reduces fitted-c target RMS from **265 to 193 Hz**, but the target still fails slope, curvature, step and correlation checks. It also breaks residual consistency on existing RX1 CH6 and RX2 CH6 evidence. Even the refresh control fails conditional-mean gates. Receiver coefficient changes are exactly zero at fixed position; phase linearization errors are below 0.000001 Hz, so this is not a stale-phase approximation failure. The 456 m position result is rejected. The original 457 m inclusion was also rejected. No 77-point recovery is claimed.

## Next investigation and evidence

For this CH7 case, challenge the identity and the shared-family model jointly against the existing CH6 evidence. A correction that improves CH7 but damages the family is insufficient. For measurement-dominated cases, use the existing IQ refinement with independent-frame checks before widening satellite priors. Continue the frozen inventory in bounded batches; do not force ambiguous labels.

The [latest 1,630-row ledger](annotation_ledger.csv) preserves the 60342 withholding decision, V06 joint rejection and this CH7 refresh rejection. [Position trials](position_trials.csv), [failed gates](failed_gates.csv), source hashes and compressed evidence preserve the experiments. An initial launch used an incorrect inventory path and failed before loading data; its terminal receipt is retained, and the completed run derives the path from the authoritative source protocol. Eight focused tests passed for receiver-trend projection, exact polynomial coverage, complete gate reporting, measurement ownership and inclusion routing. No future TLE or evaluation GPS enters inference. The full goal remains incomplete.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
