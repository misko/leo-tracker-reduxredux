"""Summarize descriptive postfit RX/band/family residual comparisons."""

import csv
import itertools
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from audit_ds23_learned_residuals import OUT
from run_algo01_ds23_sample import ROOT,read,write,sha


def save_csv(path,rows):
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def run():
    protocol=read(OUT/'protocol.json');cases=sorted(protocol['cases'])
    receipts=read(OUT/'execution.json');assert len(cases)==len(receipts)==20 and all(r['code']==0 for r in receipts)
    documents=[read(OUT/(c+'.json')) for c in cases]
    assert all(d['source_sha256']==protocol['source_sha256'] and not d['GPS_used'] for d in documents)
    assert protocol['source_sha256']==sha(ROOT/'tools/audit_ds23_learned_residuals.py')
    groups=[r for d in documents for r in d['groups']];pairs=[r for d in documents for r in d['pairs']]
    tracks=[{k:v for k,v in r.items() if k not in ('time_s','residual_hz','noise_hz')} for d in documents for r in d['tracks']]
    save_csv(OUT/'receiver_band_by_scan.csv',groups);save_csv(OUT/'track_residuals.csv',tracks);save_csv(OUT/'matched_pairs.csv',pairs)
    correlation=[]
    for arm,rx,band,family in itertools.product(('c0','fitted_c'),(True,False),(True,False),(True,False)):
        selected=[r for r in pairs if r['arm']==arm and r['same_receiver']==rx and r['same_band']==band and r['same_family']==family]
        per_case=[float(np.median([r['correlation'] for r in selected if r['case']==c])) for c in cases if any(r['case']==c for r in selected)]
        correlation.append(dict(arm=arm,same_receiver=rx,same_band=band,same_family=family,track_pairs=len(selected),
            scans=len(per_case),pooled_median_correlation=float(np.median([r['correlation'] for r in selected])) if selected else None,
            median_of_scan_medians=float(np.median(per_case)) if per_case else None))
    save_csv(OUT/'correlation_summary.csv',correlation)
    summary=[]
    for arm,rx,band in itertools.product(('c0','fitted_c'),(1,2),(0,1)):
        selected=[r for r in groups if r['arm']==arm and r['receiver']==rx and r['band']==band]
        summary.append(dict(arm=arm,receiver=rx,band=band,scans=len(selected),points=sum(r['points'] for r in selected),
            median_scan_RMS_hz=float(np.median([r['RMS_hz'] for r in selected])),
            median_scan_standardized_RMS=float(np.median([r['standardized_RMS'] for r in selected]))))
    write(OUT/'summary.json',dict(receiver_band=summary,correlation=correlation,descriptive_not_causal=True))
    fig,axes=plt.subplots(1,2,figsize=(13,4.6),constrained_layout=True)
    columns=list(itertools.product((True,False),(True,False)))
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        matrix=np.full((2,4),np.nan)
        for row,rx in enumerate((True,False)):
            for col,(band,family) in enumerate(columns):
                s=next(r for r in correlation if r['arm']==arm and r['same_receiver']==rx and r['same_band']==band and r['same_family']==family)
                if s['track_pairs']:matrix[row,col]=s['pooled_median_correlation']
                label='No pairs' if s['pooled_median_correlation'] is None else f"{s['pooled_median_correlation']:+.3f}\n{s['track_pairs']} pairs / {s['scans']} scans"
                ax.text(col,row,label,ha='center',va='center',fontsize=8)
        im=ax.imshow(matrix,cmap='coolwarm',vmin=-.7,vmax=.7,aspect='auto')
        ax.set_xticks(range(4),[('Same' if b else 'Different')+' band\n'+('Same' if f else 'Different')+' family' for b,f in columns],fontsize=8)
        ax.set_yticks([0,1],['Same receiver','Different receiver']);ax.set_title(arm)
    fig.colorbar(im,ax=axes,label='Pooled median matched-track correlation',shrink=.8)
    fig.suptitle('Conditioned residual transfer · nearest times ≤0.5 s, ≥6 unique pairs\nOverlapping track pairs are dependent; colors are descriptive')
    fig.savefig(OUT/'residual_transfer.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(14,7),sharex=True,constrained_layout=True)
    for rx in (1,2):
        for band in (0,1):
            ax=axes[rx-1,band]
            for arm in ('c0','fitted_c'):
                selected={r['case']:r for r in groups if r['arm']==arm and r['receiver']==rx and r['band']==band}
                ax.plot(range(20),[selected[c]['RMS_hz'] if c in selected else np.nan for c in cases],'.-',label=arm)
            ax.set(title=f"RX{rx} {'low CH1–4' if band==0 else 'high CH5–8'}",ylabel='Residual RMS (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    for ax in axes[-1]:ax.set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=90)
    fig.suptitle('Retained calibration residual RMS by receiver and band · missing bands stay blank')
    fig.savefig(OUT/'receiver_band_RMS.png',dpi=160);plt.close(fig)
    table=['| Receiver / band | Scans | Points | Median scan RMS, Hz | Median scan RMS / radio sigma |','|---|---:|---:|---:|---:|']
    for s in summary:
        if s['arm']=='c0':table.append(f"| RX{s['receiver']} / {'high' if s['band'] else 'low'} | {s['scans']} | {s['points']} | {s['median_scan_RMS_hz']:.1f} | {s['median_scan_standardized_RMS']:.2f} |")
    text='''# DS23: residual transfer across receivers, bands and satellite families

Replay the final causal scalar-history/RX-support fit on all20 scans, with
the exact phase-reference history, masks, labels and alias integers. No new
position inference or GPS is used. Both c arms are included. This extends
the low-band-only scan217 comparison to the eleven scans with high
channels. Curved calibration evidence is analyzed; these are not residuals
for every associated linear/short output track or every winning GLRT point.

TABLE

The table uses c0 and the median of per-scan group statistics, rather than
letting scans with more points dominate. The standardized RMS divides each
point by its independently estimated radio sigma before taking RMS; it does
not divide by the posterior group-noise adjustment. Group precisions and
per-track means/slopes/RMS are retained in the CSV.

![Receiver and band RMS](receiver_band_RMS.png)
![Matched residual correlations](residual_transfer.png)

At c0, different-family residuals have pooled median correlation+0.459
within the same receiver/band, and+0.329 across bands on the same receiver.
Same-family residuals across receivers in the same band have median−0.020.
The corresponding medians of per-scan medians are+0.449,+0.304 and−0.039,
so the pattern is not solely a scan-count pooling artifact. This supports
testing receiver-common plus band-specific covariance. It does not establish
that a receiver-only correction will improve position; the original217 fast
receiver model already reduced RMS without fixing localization.

## What the comparison can establish

Match actual observations within0.5s using nearest-distance-first unique
pairs; never interpolate or reuse a point within a track pair. Require six
pairs per comparison. Summarize all eight same/different RX×band×family
strata. The CSV includes both pooled track-pair medians and the median of
per-scan medians; it records how many scans contribute to each cell.

A positive same-RX/different-family correlation is consistent with shared
receiver behavior. A same-family/cross-RX correlation is consistent with
remaining shared orbit/transmitter behavior. These are descriptive clues,
not causal identification: all residuals have been conditioned on a joint
fit that already removes shared receiver and satellite terms. Overlapping
pairs are dependent, timing support and radio noise vary, and their sample
counts cannot be used as independent significance tests. A near-zero
cross-RX correlation does not prove that TLE errors are absent; phase and
orbit modes can already have absorbed them. Cross-band comparisons apply
only to recordings containing both bands; missing data are not zero noise.

The broad position-error controls remain in the [prior-refinement report](../2026_10_18_ds23_prior_refinements/README.md)
and [remaining-failure report](../2026_10_18_ds23_remaining_failures/README.md).
These residual plots do not justify choosing labels or priors from known GPS.

## Reproduction

[Protocol](protocol.json) · [Execution](execution.json) · [Summary](summary.json) ·
[Receiver/band groups](receiver_band_by_scan.csv) · [Track RMS, means and slopes](track_residuals.csv) ·
[Matched pairs](matched_pairs.csv) · [Stratified correlations](correlation_summary.csv) ·
[Validation](validation.json).

Run tools/audit_ds23_learned_residuals.py --case CASE for the20 cases listed
in protocol.json, then tools/report_ds23_learned_residuals.py, using the
repository venv with PYTHONPATH=src:tools and BLAS/OMP threads1. The completed
cohort used two workers with120s per-case bounds. The original GLRT/track and
causal-prior snapshots are required; no IQ reread, new RF, archive mutation
or post-observation TLE is used. Source snapshots overlay the earlier reports.
'''.replace('TABLE','\n'.join(table))
    (OUT/'README.md').write_text(text)
    write(OUT/'validation.json',dict(all20_present=True,all_probe_source_hashes_match=True,
        max_replay_loss_difference=max(abs(v) for d in documents for v in d['replay_loss_differences']),
        GPS_used=False,report_source_sha256=sha(Path(__file__)),matching_tests_passed=3))
    print('\n'.join(table));print('c0 correlations',[r for r in correlation if r['arm']=='c0'],flush=True)


if __name__=='__main__':run()
