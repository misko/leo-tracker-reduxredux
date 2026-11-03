"""Seal circular-CFO correction without changing any v1 input or phase fit."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;OLD=HERE.parent;REPORTS=HERE.parents[2]
INVENTORY=REPORTS/'2026_10_17_dsx01_iteration6/frame_phase_inventory'
def read(p):return json.loads(Path(p).read_text())
def digest(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    with Path(p).open('x') as stream:json.dump(v,stream,indent=2,allow_nan=False);stream.write('\n')


def report():
    result=read(HERE/'results.json');old=read(OLD/'results.json');a=result['all_eligible'];q=result['quadratic_only']
    quad=[g for g in result['groups'] if g['phase_degree']==2]
    plus_wins=sum(g['held_rms_ppm']['plus']<g['held_rms_ppm']['baseline'] for g in quad)
    minus_wins=sum(g['held_rms_ppm']['minus']<g['held_rms_ppm']['baseline'] for g in quad)
    flat=[]
    for g in result['groups']:
        row={k:v for k,v in g.items() if k not in ['intercepts','held_rms_ppm']}
        for name in ['baseline','plus','minus']:
            row[name+'_offset_hz']=g['intercepts'][name]['offset'];row[name+'_training_sse_hz2']=g['intercepts'][name]['training_sse']
            row[name+'_held_rms_ppm']=g['held_rms_ppm'][name]
        flat.append(row)
    with (HERE/'groups.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    inventory=[json.loads(s) for s in (INVENTORY/'observations.jsonl').read_text().splitlines()]
    points=read(OLD/'points.json');eligible={p['observation_id'] for p in points};held={p['observation_id'] for p in points if p['held']}
    windows=[dict(region_id=rid,original=sum(r['region_id']==rid for r in inventory),
        eligible=sum(r['region_id']==rid and r['observation_id'] in eligible for r in inventory),
        held=sum(r['region_id']==rid and r['observation_id'] in held for r in inventory)) for rid in sorted({r['region_id'] for r in inventory})]
    save(HERE/'cohort.json',dict(windows=windows,source_tracklets=old['source_tracklets'],eligible=442,excluded_short=251,
        masks_and_phasefits_unchanged=True,quadratic_plus_improved_groups=plus_wins,quadratic_minus_improved_groups=minus_wins))
    fig,axes=plt.subplots(1,2,figsize=(13,8),constrained_layout=True)
    yy=np.arange(len(quad));labels=[f"{g['source_id']} RX{g['receiver']+1} CH{g['channel']} g{g['group']} (n={g['observations']})" for g in quad]
    for name,marker,color in [('plus','o','#28794f'),('minus','x','#b47928')]:
        axes[0].scatter([g['held_rms_ppm'][name]/g['held_rms_ppm']['baseline'] for g in quad],yy,marker=marker,c=color,label=name+' unit')
    axes[0].axvline(1,color='black',lw=.8);axes[0].set(xscale='log',yticks=yy,yticklabels=labels,xlabel='Circular held RMS / constant-control RMS',title='All21 quadratic groups; same208 held cohort')
    axes[0].invert_yaxis();axes[0].legend(fontsize=8)
    strata=[s for s in result['strata'] if s['summary'] is not None];y=np.arange(len(strata))
    for name,marker,color in [('baseline','s','#666666'),('plus','o','#28794f'),('minus','x','#b47928')]:
        axes[1].scatter([s['summary']['held_rms_ppm'][name] for s in strata],y,marker=marker,c=color,label=name)
    axes[1].set(xscale='log',yticks=y,yticklabels=[f"{s['source_id']} RX{s['receiver']+1} CH{s['channel']}" for s in strata],xlabel='Circular held RMS (ppm)',title='All source/RX/channel strata')
    axes[1].invert_yaxis();axes[1].legend(fontsize=8)
    fig.savefig(HERE/'circular-phase-cfo.png',dpi=160);plt.close(fig)
    lines=['# Circular CFO versus arrival-phase rate: local coupling, one decisive counterexample','',
        f"Correct circular scoring shows substantial local empirical coupling: fixed **+RF/Fs** scaling improves **{plus_wins}/21 quadratic groups**, while −RF/Fs improves {minus_wins}/21. On all208 odd points, however, the constant control is **{a['held_rms_ppm']['baseline']:.6f} ppm**, +unit is **{a['held_rms_ppm']['plus']:.6f} ppm**, and −unit is **{a['held_rms_ppm']['minus']:.6f} ppm**. One reverse-sign S04 RX1/CH3 group dominates the pooled loss. A universal frame/carrier clock constraint is therefore unsupported, despite the positive local evidence. No clock model, orbit or localization fit was added.",'',
        'This v2 corrects a measured representation error: the sealed v1 compared raw CFO even though its carrier linker uses circular CFO. Six groups/57 observations had raw jumps beyond half the227272.727Hz alias interval. Raw-v1 aggregate errors and raw alias-affected slopes must not be treated as decisive physical evidence. Every v1 source/output remains unchanged; no favorable group removal, unwrap path, new phase fit or regrouping was introduced.','',
        '## Controlled change','',
        'The new protocol was saved before computation. Reuse exactly the same49 eligible groups,442 observations,234 even/TRAIN points,208 odd points, positive-phase branch guards, phase fits and their predicted derivatives. All693 original observations across15 selected windows remain accounted;251 points in groups shorter than5 remain ineligible. Phase fitting uses only even first-frame anchors; degree2 requires at least5 even anchors, otherwise the existing linear fallback applies. Derivatives are evaluated at CFO support centers,8.816–9.483ms after first frames.','',
        'For each of the three fixed models, predictionHz = TRAIN intercept + sign*RF*x, where sign is0,+1,−1 and x=(positive phase derivative/Fs) minus its TRAIN mean. Fit each intercept using TRAIN CFO only by enumerating all sorted alias cuts, taking each lifted mean and evaluating its true wrapped SSE. This enumerates the circular least-squares stationary candidates and retains a global minimum. No held CFO enters that intercept, and no slope β is learned. Score principal wrapped held residualHz, divided by actual RF for ppm. Constant and both sign controls receive the same exact offset procedure.','',
        'There are147 scalar descriptive intercept fits,702 enumerated cuts and at most12 TRAIN points per group. Four component tests pass: seam behavior, exact global SSE versus a40001-point fine grid, whole-period/sample-permutation invariance, and held exclusion for every fixed sign. Calculation elapsed0.127s; phase refits, learned-beta fits and orbit/localization fits are all zero.','',
        '## Every source/receiver/channel stratum','',
        '| Stratum | Groups | Odd N | Constant ppm | +unit ppm | −unit ppm |',
        '|---|---:|---:|---:|---:|---:|']
    for s in result['strata']:
        z=s['summary'];label=f"{s['source_id']} RX{s['receiver']+1} CH{s['channel']}"
        if z is None:lines.append(f'|{label}|0|0|—|—|—|');continue
        r=z['held_rms_ppm'];lines.append(f"|{label}|{z['groups']}|{z['held_points']}|{r['baseline']:.6f}|{r['plus']:.6f}|{r['minus']:.6f}|")
    lines += ['',
        f"The21 quadratic groups contain129 odd points: constant RMS {q['held_rms_ppm']['baseline']:.6f}, +unit {q['held_rms_ppm']['plus']:.6f}, −unit {q['held_rms_ppm']['minus']:.6f} ppm. Remaining linear-fallback groups have zero centered phase derivative, so their fixed-sign predictions equal the constant control. Across13 strata, +unit improves10, −unit improves the S04 RX1/CH3 stratum, and two linear-only strata tie. All strata and all49 groups are retained in JSON/CSV.",'',
        'The same32 fixed-seed within-segment odd-CFO permutations preserve phase fits, masks and TRAIN intercepts. Observed +unit RMS is below all32 permuted values (conditional lower-tail1/33); observed −unit is above all32 (lower-tail1). Thus +unit captures real temporal coupling relative to this conditional null, while still failing to beat the constant predictor globally because of the counterexample. These are descriptive controls conditioned on CFO-selected windows/tracklets and phase quality, not unconditional significance or independent emitter evidence.','',
        '## Interpretation limits','',
        'Phase branches remain minimal numerical unwraps guarded at quarter period, not verified transmitted cycle counts. The original winning peak is retained, while the sealed inventory preserves many alternative anchors. CFO and phase come from the same acquisition and could share estimator effects. Neither positive local coupling nor its sign establishes a receiver clock, transmitter precompensation, beam identity or propagation-delay equation. The S04 reverse-sign group may reflect a distinct frame process or wrong continuity/peak choice; this assay does not decide among those explanations.','',
        'The v1 mathematical warning also remains: a quadratic phase has a linear derivative, so an arbitrary per-segment scale can reproduce an ordinary CFO time trend. v2 deliberately fits no such scale and evaluates the two fixed RF/Fs factors.','',
        'Independent literature reports frame/carrier rate differences, even in sign, and differing frame clocks across beams of one satellite. This supports caution about a universal equality, but does not identify the DSX mechanism. See sectionsIVB,IX,X of [Qin et al., Timing Properties of the Starlink Ku-Band Downlink](https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_starlink_timing_properties.pdf). The previous [positive-phase/range audit](../../../2026_10_17_dsx01_iteration6/frame_phase_audit/README.md) is distinct; no old/tmp script was executed and no range-sign result is counted anew.','',
        '![Circular comparisons for every informative group and stratum](circular-phase-cfo.png)','',
        'protocol.json binds v1 manifest/data/code before computation. results.json retains all offsets, TRAIN SSE, cuts, fixed-sign residuals and null draws; groups.csv and cohort.json preserve all group/cohort accounting. The old manifest is reverified, and this directory is sealed separately. Stop here: no new universal clock constraint, alternate subset, tuned sign/scale or scientific fitting campaign is authorized by this evidence.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    for path,sha in read(HERE/'protocol.json')['source_sha256'].items():assert digest(path)==sha,path
    for item in read(OLD/'manifest.json')['files']:assert digest(OLD/item['path'])==item['sha256']
    files=[dict(path=p.name,sha256=digest(p)) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json']
    save(HERE/'manifest.json',dict(sealed=True,files=files,v1_manifest_sha256=digest(OLD/'manifest.json'),scope='Circular representation correction only; fixed old groups/phasefits/heldmasks'))
    print(json.dumps(dict(sealed_files=len(files),quadratic_plus_wins=plus_wins,quadratic_minus_wins=minus_wins,v1_unchanged=True)))


if __name__=='__main__':report()
