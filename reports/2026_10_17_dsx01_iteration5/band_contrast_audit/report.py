"""Read-only conditional contrast assay report; no reference coordinates."""
import csv
import json
from pathlib import Path
import numpy as np
from run_assay import HERE,digest


def run():
    data=json.loads((HERE/'results.json').read_text());verification=json.loads((HERE/'verification.json').read_text())
    assert verification['passed'];rows=data['results'];selection=data['selections']
    with (HERE/'window-comparison.csv').open('w') as stream:
        writer=csv.writer(stream);writer.writerow(['arm','method','region_id','train_observations','train_associated','held_observations','held_associated'])
        for r in rows:
            for w in r['windows']:writer.writerow([r['arm'],r['method'],w['region_id'],w['train']['observations'],w['train']['associated'],w['held']['observations'],w['held']['associated']])
    lines=['# Conditional frozen-band contrast assay','',
        'Revising only the frozen band constants modestly improves fitted-c held support:795→805/1909 (+40/−30), while requested held support stays66/80. '
        'The held frequency NLL improves by85.236. Thus the constants are a measured conditional fit bottleneck, but this assay does not restore another requested held observation.','',
        'The exact TRAIN-selected blocked-production endpoint supplies every physical coordinate, timing, residual clock, q and candidate. Only two receiver high-band corrections vary. '
        'The c=0 control changes only the RF coefficient before the same assay; it remains conditional on fitted-c production discovery and all its other learned coordinates. '
        'No geography, timing, clock, q, identity selection or reference coordinates are tuned or consulted.','',
        'The protocol was persisted before loading the real training context: per receiver, update±10000Hz at500Hz spacing, then±500Hz at25Hz spacing around the best coarse point, clipped to the original search box and public absolute alias-branch bounds. '
        'Receivers are separable because q is fixed and their high-band rows are disjoint. The score is exact shared lane likelihood plus the **absolute** contrast prior relative to zero: '
        '`originalJ + sum(laneNLL_new-laneNLL_original) + .5*(sum(new_offsets²)-sum(original_offsets²))/50000²`. '
        'The existing global prior is replaced once; no donor prior or prior on the update is added. Both selected updates were persisted before held scoring.','',
        '| c arm | RX1 update Hz | RX2 update Hz | Absolute RX1/RX2 Hz | TRAIN J before→after | Calls |',
        '|---|---:|---:|---:|---:|---:|']
    for arm,s in selection.items():lines.append(f"| {arm} | {s['updates_hz'][0]:.0f} | {s['updates_hz'][1]:.0f} | {s['absolute_offsets_hz'][0]:.3f} / {s['absolute_offsets_hz'][1]:.3f} | {s['training_objective_before']:.3f}→{s['training_objective']:.3f} | {s['diagnostics']['evaluations']} |")
    lines+=['','| c arm | Method | Train associated | Held associated | Held NLL | Held new/lost | Requested held |','|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        target=sum(w['held']['associated'] for w in r['windows'])
        lines.append(f"| {r['arm']} | {r['method']} | {r['train']['associated']}/2073 | {r['held']['associated']}/1909 | {r['held']['frequency_nll']:.3f} | +{r['held']['new_vs_paired_baseline']}/−{r['held']['lost_vs_paired_baseline']} | {target}/80 |")
    lines+=['','Fitted-c requested windows remain20/26,20/28,26/26; conditional c=0 windows remain17/26,13/28,24/26. '
        'The c=0 profiles improve broader held coverage405→500 and held NLL25196.099→24801.587 without increasing requested held coverage54/80. '
        'These are fixed-state frequency/calibration effects; location is unchanged and no localization improvement follows.','',
        'Each arm uses159 counted calls: one original shared objective,156 noncached lane densities, one full zero-update density check and one full endpoint density check. '
        'There are166 profile requests and10 cache hits per arm. Both arms have the same200-call/120-second allowance and finish their profile calculations in about0.10seconds. '
        'Initial context replay adds one separately declared strict shared-objective audit; initial full-cohort scoring adds four density calls and two prediction orbit queries. '
        'The independent no-fit replay separately reports one context audit, four direct shared objectives, four metadata prediction queries and four scoring densities. '
        'No continuous KKT or full-joint admission is claimed for a grid endpoint.','',
        'All fixed denominators remain:2073train+1909held+6boundary=3988source winners;58train+80held+0boundary+555untested other-source=693challenge observations. '
        'The other16096context observations remain untested. No original observation is replaced or credited via an alternate peak.','',
        'Four component tests pass: zero update nests the original objective exactly; separable scores match a directly reconstructed shared model with the absolute prior once; held CFO cannot change training selection; and cached/density accounting respects the cap and retains the incumbent. '
        'Actual endpoint replay reproduces both direct shared objectives/NLLs, frozen predictions and original125Hz classifier arrays. Old sealed reports are unchanged.','',
        '![Training-only contrast profiles](profiles.png)','',
        'This local frozen-state assay does not test joint band/timing/clock readjustment or drift. Its modest fitted-c gain leaves that question open; it is not a full-pipeline c=0 or independent-position validation result.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    plot(selection)
    files=[p for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json']
    (HERE/'manifest.json').write_text(json.dumps(dict(files=[dict(path=str(p.relative_to(HERE)),sha256=digest(p)) for p in sorted(files)]),indent=2)+'\n')
    print(json.dumps(dict(sealed=True,files=len(files),profile_calls=data['actual_profile_evaluations'])))


def plot(selection):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(10,6),sharex=True)
    for axis,(arm,s) in zip(axes,selection.items()):
        for rx,ax in enumerate(axis):
            trace=[t for t in s['trace'] if t['receiver']==rx]
            baseline=next(t['lane_objective'] for t in trace if t['update_hz']==0)
            for phase,label,color in [('coarse','Coarse500Hz','#3979b2'),('fine','Fine25Hz','#df8c33')]:
                points=[t for t in trace if t['phase']==phase]
                ax.plot([t['update_hz']/1000 for t in points],[t['lane_objective']-baseline for t in points],'.-',color=color,label=label,linewidth=1)
            ax.axvline(s['updates_hz'][rx]/1000,color='#777777',linestyle='--');ax.axhline(0,color='#aaaaaa',linewidth=.8)
            ax.set_title(f'{arm}, RX{rx+1} high band');ax.set_xlim(-10,10);ax.set_xlabel('Offset update (kHz)');ax.set_ylabel('TRAIN lane objective change');ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(HERE/'profiles.png',dpi=160);plt.close(fig)


if __name__=='__main__':run()
