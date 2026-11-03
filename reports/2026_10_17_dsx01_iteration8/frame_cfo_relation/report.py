"""Render the fixed descriptive audit; no re-fit or altered branch selection."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parents[1]
INVENTORY=REPORTS/'2026_10_17_dsx01_iteration6/frame_phase_inventory'
def read(p):return json.loads(Path(p).read_text())
def digest(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    with Path(p).open('x') as stream:json.dump(v,stream,indent=2,allow_nan=False);stream.write('\n')


def report():
    result=read(HERE/'results.json');points=read(HERE/'points.json')
    meta={r['observation_id']:r for s in (INVENTORY/'observations.jsonl').read_text().splitlines() if (r:=json.loads(s))}
    aliases=[]
    for group in sorted({p['group'] for p in points}):
        rows=sorted([p for p in points if p['group']==group],key=lambda p:p['first_frame_s'])
        rf=meta[rows[0]['observation_id']]['actual_rf_hz'];cfo=np.array([p['y_centered']*rf for p in rows])
        if np.any(abs(np.diff(cfo))>1/4.4e-6/2):
            aliases.append(dict(group=group,source_id=rows[0]['source_id'],receiver=rows[0]['receiver'],channel=rows[0]['channel'],
                observations=len(rows),held_points=sum(p['held'] for p in rows)))
    save(HERE/'provenance-caveats.json',dict(raw_cfo_alias_step_groups=aliases,
        raw_cfo_alias_affected_observations=sum(a['observations'] for a in aliases),raw_cfo_alias_affected_held_points=sum(a['held_points'] for a in aliases),
        policy='Primary predeclared rawwinningCFO metrics unchanged; no favorable posthoc unwrapping, exclusion or re-fit',
        phase_alternatives='Stored winning candidate is fixed; inventory has551/693probes withmultiple numerical passed phases. These are alternatives, not emitters.',
        prior_work='No directall693CFO/phase-rate test found in reviewed oldphaseaudit/scripts; old selectedphase-vs-frozenrange comparison is separate and not rerun.',
        paper=dict(title='Timing Properties of the Starlink Ku-Band Downlink',authors='Wenkai Qin et al.',
            url='https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_starlink_timing_properties.pdf',
            inspected='AuthorPDF sectionsIVB/IX/X, pp4–5 and13–14, read2026-10-17',usage='Context only; not proof of same DSX cause')))
    strata=[s for s in result['strata'] if s['summary'] is not None]
    quad=[(i,g) for i,g in enumerate(result['groups']) if g['eligible'] and g['degree']==2]
    fig,axes=plt.subplots(1,2,figsize=(13,8),constrained_layout=True)
    yy=np.arange(len(quad));labels=[f"{g['source_id']} RX{g['receiver']+1} CH{g['channel']} g{i} (n={g['observations']})" for i,g in quad]
    axes[0].scatter([g['beta'] for _,g in quad],yy,c=['#a34e42' if i in {a['group'] for a in aliases} else '#3267a6' for i,g in quad])
    axes[0].axvline(1,color='#28794f',lw=1,label='Fixed +unit');axes[0].axvline(-1,color='#b47928',lw=1,label='Fixed −unit')
    axes[0].set(yticks=yy,yticklabels=labels,xlabel='Descriptive TRAIN slope β (not physics)',title='All21 quadratic phase groups')
    axes[0].invert_yaxis();axes[0].legend(fontsize=8)
    for sign,marker,color in [('plus','o','#28794f'),('minus','x','#b47928')]:
        ratio=[g['held_'+sign+'_rms_ppm']/g['held_baseline_rms_ppm'] for _,g in quad]
        axes[1].scatter(ratio,yy,marker=marker,c=color,label=sign+' fixed-unit sign')
    axes[1].axvline(1,color='black',lw=.8);axes[1].set(xscale='log',yticks=yy,yticklabels=[],xlabel='Held RMS / centered-CFO baseline RMS',title='Fixed physical factors; left of1 improves')
    axes[1].invert_yaxis();axes[1].legend(fontsize=8)
    fig.savefig(HERE/'phase-cfo-groups.png',dpi=160);plt.close(fig)
    a=result['all_eligible'];q=result['quadratic_only']
    lines=['# Carrier CFO versus positive-arrival phase derivative: local coupling, no universal constraint','',
        f"The predeclared all-source raw-CFO comparison is negative/ambiguous: odd-point RMS is {a['held_rms_ppm']['baseline']:.4f} ppm after TRAIN constant centering, versus {a['held_rms_ppm']['plus']:.4f} for fixed +unit and {a['held_rms_ppm']['minus']:.4f} for fixed −unit phase-rate scaling. A pooled TRAIN slope β={a['pooled_train_beta']:.4f} gives {a['held_rms_ppm']['pooled_beta']:.4f} ppm. Neither sign or pooled slope provides reproducible global improvement under the32 conditional permutations. No clock constraint is justified; the audit stops without tuning or localization fitting.",'',
        'There is limited positive local evidence: many receiver/channel segments show approximately +unit fractional coupling at held points, while other segments reverse sign or have poor scale/alias consistency. Every source/lane and every tested or rejected group is retained. This is not evidence that either reported field is an independently calibrated transmitter clock or known propagation delay.','',
        f"All693 frozen observations across15 windows were accounted. The exact oldautomatic450Hz/45s/24point builder produced {sum(result['source_tracklets'].values())} carrier tracklets; conservative phase branch checks left {result['phase_subsegments']} subsegments. There are49 eligible groups/442 observations,234 even phase/TRAIN-centering points and208 odd comparison points;251 observations are in groups shorter than5. Twenty-one quadratic groups contain271 observations/129 odd points. The remaining28 eligible groups use a linear fallback whose centered phase derivative is zero and hence cannot estimate a phase-rate scale.",'',
        '## Fixed procedure and time/units','',
        'The693 observations are the previously selected original winners. No new peak, satellite, orbit, position or station value enters this audit. Group construction is separately per source, using rawwinningCFO, RX/channel and native metadata; window IDs are descriptive output only. Thus the cohort and tracklets are CFO selected, and the alternating test is conditional on that selection, not independent validation. Carrier CFO and phase also come from the same candidate acquisition.','',
        'Positive phase is the sealed counter/anchor formula modulo the physical Fs/750 period,3333⅓samples at Fs=2.5MHz. Split at nonpositive first-frame time, adjacent gap>5s, or principal phase increment>quarter period. Alternating TRAIN anchors must also pass the quarter-period guard. This defines a conservative numerical minimal branch, not a verified transmitted frame cycle; unknown cycle slips and alternative anchors remain possible.','',
        'Use only even-index phase anchors. Fit degree2 when at least5 even anchors exist; otherwise degree1 with at least3 anchors (totalN≥5). Center polynomial time at the mean TRAIN **first-frame** epoch. Evaluate its derivative at each CFO **support-center** time,8.816–9.483ms later. Set x=(dphase/dt)/Fs and y=CFO/actualRF, subtracting their respective even/TRAIN means per segment. Fixed comparisons are y≈+x and y≈−x, equivalently CFO variation≈±RF/Fs times phase-rate variation. No arbitrary coefficient is fitted to claim this physical equality.','',
        'A descriptive β is fitted on even rows only and applied to odd rows; the phase fit never receives CFO. The32 fixed-seed permutations reorder odd centered CFO within each frozen segment. They are descriptive conditional controls, not tests of an unconditional grouping process. Both signs are reported without selecting a sign by results.','',
        '## All tested source/receiver/channel strata','',
        '| Source / receiver / channel | Groups | Odd N | TRAIN β | Centered baseline ppm | +unit ppm | −unit ppm |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for s in result['strata']:
        z=s['summary'];label=f"{s['source_id']} / RX{s['receiver']+1} / CH{s['channel']}"
        if z is None:lines.append(f'| {label} |0|0| — | — | — | — |');continue
        beta='undefined' if z['pooled_train_beta'] is None else f"{z['pooled_train_beta']:.4f}"
        rms=z['held_rms_ppm'];lines.append(f"| {label} |{z['groups']}|{z['held_points']}|{beta}|{rms['baseline']:.4f}|{rms['plus']:.4f}|{rms['minus']:.4f}|")
    lines += ['',
        '## Why a good free slope does not establish another clock observable','',
        f"For quadratic phase p(t), p′(t) is linear in time. After per-segment constant centering, a free β*p′(t) is exactly an ordinary per-segment CFO linear time trend whenever phase curvature is nonzero. The21 quadratic groups verify this identity: maximum held prediction discrepancy is {q['max_segment_beta_time_only_discrepancy_ppm']:.2g} ppm. Their freely scaled held RMS {q['held_rms_ppm']['segment_beta']:.4f} ppm is identically the time-only baseline. Thus improved free-slope fit alone adds no independent measurement constraint. Reproducible fixed scale/sign across groups would be stronger evidence; it is not universal here.",'',
        f"A further ambiguity is explicit:6 eligible groups ({sum(x['observations'] for x in aliases)} observations/{sum(x['held_points'] for x in aliases)} odd points) have rawCFO steps greater than half the CFO alias interval. The carrier linker uses circular CFO, while the predeclared comparison retains raw winning CFO. These groups can dominate aggregate RMS. The primary numbers were not recomputed after choosing an unwrap or removing them. Even the non-alias S04 RX1 CH3 segment has negative β≈−0.590. Therefore the raw global result is both negative and branch limited, and the local +unit examples cannot justify a universal physical relation.",'',
        'The frame inventory also retains alternative passed phase estimates:551/693 probes have multiple exact numerical fractional phases. Their spread mixes near-identical estimates and widely separated possible anchors. This audit keeps the original winner throughout; it does not resolve which alternative is a physical emitter epoch or estimate phase covariance.','',
        '## Prior evidence and external context','',
        'The [sealed phase audit](../../2026_10_17_dsx01_iteration6/frame_phase_audit/README.md) established positive arrival-phase semantics and replayed selected phase-versus-frozen-range shapes. It did not establish this all693 carrier/phase-rate relationship. No old/tmp script was imported or executed, and no previous range-sign result is counted as a new result.','',
        'Qin et al. distinguish observed timing behavior from a proposed clock architecture. They report that frame and carrier fractional rates can differ, including in sign, and that signals from different beams of one satellite can have different frame phases/rates. This is relevant context against imposing a universal equality, not evidence of the same cause in DSX. See sectionsIVB,IX,X of the [author PDF, Timing Properties of the Starlink Ku-Band Downlink](https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_starlink_timing_properties.pdf).','',
        '![All quadratic groups and fixed-sign held errors](phase-cfo-groups.png)','',
        'Five component tests pass: modulo seam/guard/gaps, first-frame-to-support derivative transport, exclusion of odd phases/CFO from the fitted phase relation, free-quadratic-slope/time-trend equivalence, and linear fallback. Main calculation elapsed0.223s, far below120s; report rendering is separate. There are zero orbit/localization fit calls and no newRF or reference read. protocol-v2.json binds final code/inputs before target CFO loading; protocol.json is preserved as an earlier preflight that stopped on a manifest-schema mismatch before CFO loading and produced no scientific result. groups.csv/results.json preserve all179 groups and stratum metrics; points.json preserves qualified comparisons.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    for name,sha in read(HERE/'protocol-v2.json')['source_sha256'].items():assert digest(name)==sha,name
    files=[dict(path=p.name,sha256=digest(p)) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json']
    save(HERE/'manifest.json',dict(sealed=True,files=files,scope='Descriptive carrier/phase-rate audit; no orbit/localization inference'))
    print(json.dumps(dict(sealed_files=len(files),raw_cfo_alias_groups=len(aliases),no_new_fits=True)))


if __name__=='__main__':report()
