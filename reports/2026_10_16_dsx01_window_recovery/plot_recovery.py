"""Describe saved DSX01 window recovery and timing fits; no fitting or tuning."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
MODELS = HERE.parent / '2026_10_16_dsx01_models'
DATA = HERE.parent / '2026_10_16_dsx01_fast_association_losses'
METHODS = ['A','B','C','continuation']
COLORS = {'A':'#0072b2','B':'#d55e00','C':'#009e73','original':'#666666'}


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def save_csv(path,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    regions=read_csv(DATA/'regions.csv')
    members=read_csv(DATA/'membership.csv')
    context=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    sources=json.loads((DATA/'sources.json').read_text())
    fits={}
    states={}
    input_files=[DATA/'regions.csv',DATA/'membership.csv',DATA/'context-observations.jsonl']
    for source in sources:
        sid=source['source_id']
        for method in ['original',*METHODS]:
            path=MODELS/'results'/f'{sid}-full-fitted-c-{method}.json'
            fits[sid,method]=json.loads(path.read_text())
            states[sid,method]=dict(np.load(path.with_suffix('.npz')))
            input_files.extend([path,path.with_suffix('.npz')])
    lookup={s['source_id']:{o['observation_id']:i for i,o in enumerate(
        x for x in context if x['source_id']==s['source_id'])} for s in sources}
    rows=[]
    for region in regions:
        sid=region['source_id']
        ix=np.array([lookup[sid][m['observation_id']] for m in members if m['region_id']==region['region_id']])
        before=states[sid,'original']['associated'][ix]
        assert len(ix)==int(region['observation_count'])
        assert before.sum()==int(region['original_associated_count'])
        for method in METHODS:
            after=states[sid,method]['associated'][ix]
            new=int(np.sum(after & ~before))
            lost=int(np.sum(before & ~after))
            missing=int((~before).sum())
            rows.append(dict(region_id=region['region_id'],source_id=sid,
                recording_id=region['recording_id'],receiver=int(region['receiver']),channel=int(region['channel']),
                start_s=float(region['start_s']),end_s=float(region['end_s']),method=method,
                observations=len(ix),original_associated=int(before.sum()),variant_associated=int(after.sum()),
                original_pct=100*float(before.mean()),variant_pct=100*float(after.mean()),
                originally_unassociated=missing,newly_associated=new,lost_original_associations=lost,
                net_gain=new-lost,newly_associated_fraction_of_original_missing_pct=100*new/missing,
                net_fraction_of_original_missing_pct=100*(new-lost)/missing))
    save_csv(HERE/'window-recovery.csv',rows)
    main_rows=[r for r in rows if r['method']=='A']
    assert len(main_rows)==15 and sum(r['observations'] for r in main_rows)==693
    assert sum(r['original_associated'] for r in main_rows)==96
    assert sum(r['variant_associated'] for r in main_rows)==253

    fig,ax=plt.subplots(figsize=(13,9.3),constrained_layout=True)
    yy=np.arange(15)
    ax.barh(yy-.17,[r['original_pct'] for r in main_rows],height=.30,color='#8c8c8c',label='Original')
    ax.barh(yy+.17,[r['variant_pct'] for r in main_rows],height=.30,color=COLORS['A'],label='Automatic model A')
    labels=[f"{r['region_id'][-3:]}  {r['source_id']}  RX{r['receiver']}/CH{r['channel']}  {r['start_s']:g}–{r['end_s']:g}s" for r in main_rows]
    ax.set_yticks(yy,labels)
    for y,r in zip(yy,main_rows):
        ax.text(102,y,f"{r['original_associated']} → {r['variant_associated']} / {r['observations']}",va='center',fontsize=10)
    ax.set_xlim(0,122)
    ax.set_xticks([0,20,40,60,80,100])
    ax.set_xlabel('Associated observations / all original observations in the requested window (%)')
    ax.invert_yaxis()
    ax.grid(axis='x',alpha=.2)
    handles,legend_labels=ax.get_legend_handles_labels()
    fig.legend(handles,legend_labels,loc='outside lower center',ncol=2)
    ax.set_title('DSX01: recovery of all 15 frozen windows, fitted-c\nAssociation coverage, not verified identity recovery; model A endpoints are nonstationary',pad=14)
    fig.savefig(HERE/'window-recovery.png',dpi=180)
    plt.close(fig)

    timing_rows=[]
    active=set()
    for source in sources:
        sid=source['source_id']
        base=fits[sid,'original']['full_scan']
        old=states[sid,'original']
        numbers,counts=np.unique(old['satellite_number'][old['associated']],return_counts=True)
        active.update((sid,str(int(n))) for n,c in zip(numbers,counts) if c>=5)
        for method in ['original',*METHODS]:
            m=fits[sid,method]['full_scan']
            assert list(m['total_timing_s'])==list(base['total_timing_s'])
            for number,total in m['total_timing_s'].items():
                timing_rows.append(dict(source_id=sid,satellite=int(number),method=method,
                    total_timing_s=total,common_timing_s=m['common_timing_s'],
                    relative_timing_s=total-m['common_timing_s'],
                    total_timing_change_s=total-base['total_timing_s'][number],
                    original_support_at_least_5=(sid,number) in active))
    save_csv(HERE/'timing-offsets.csv',timing_rows)
    n_pairs=sum(len(fits[s['source_id'],'original']['full_scan']['total_timing_s']) for s in sources)
    assert n_pairs==215
    bins=np.arange(-24.,24.0001,2.)
    for supported,name in [(False,'satellite-timing-histogram.png'),(True,'supported-satellite-timing-histogram.png')]:
        fig,axes=plt.subplots(2,3,figsize=(14,7.3),sharex=True,sharey='row',constrained_layout=True)
        for col,method in enumerate(['A','B','C']):
            for row,(field,label) in enumerate([('total_timing_s','Total fitted orbit-time offset τ (s)'),
                                                ('relative_timing_s','Satellite offset after removing common clock (s)')]):
                ax=axes[row,col]
                original=[r[field] for r in timing_rows if r['method']=='original' and (not supported or r['original_support_at_least_5'])]
                variant=[r[field] for r in timing_rows if r['method']==method and (not supported or r['original_support_at_least_5'])]
                assert np.histogram(original,bins=bins)[0].sum()==len(original)
                assert np.histogram(variant,bins=bins)[0].sum()==len(variant)
                ax.hist(original,bins=bins,histtype='step',linewidth=2,color=COLORS['original'],linestyle='--',label='Original')
                ax.hist(variant,bins=bins,histtype='step',linewidth=2,color=COLORS[method],label=method)
                ax.axvline(0,color='#444444',linewidth=.7)
                if row==0:
                    ax.axvline(-20,color='#bbbbbb',linewidth=1)
                    ax.axvline(20,color='#bbbbbb',linewidth=1,label='Total timing bounds ±20 s')
                ax.set_xlim(-24,24)
                ax.set_xlabel(label)
                ax.set_ylabel('Recording–satellite fits / 2 s bin')
                ax.grid(axis='y',alpha=.2)
                if row==0:
                    ax.set_title(f'Model {method} vs original; N={len(original)}')
                ax.legend(fontsize=8)
        cohort='Fixed original-supported cohort (≥5 assigned observations)' if supported else 'All 215 fitted recording–satellite pairs, including weakly supported candidates'
        fig.suptitle(f'DSX01 satellite timing-offset histograms, fitted-c\n{cohort}; original dashed, variant solid',fontsize=13)
        fig.savefig(HERE/name,dpi=180)
        plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(13,4.2),sharex=True,sharey=True,constrained_layout=True)
    for ax,method in zip(axes,['A','B','C']):
        change=[r['total_timing_change_s'] for r in timing_rows if r['method']==method]
        change_bins=np.arange(-41,41.01,1)
        assert np.histogram(change,bins=change_bins)[0].sum()==len(change)
        ax.hist(change,bins=change_bins,color=COLORS[method],alpha=.75)
        ax.axvline(0,color='black',linewidth=1)
        ax.set_title(f'Model {method} − original')
        ax.set_xlabel('Change in fitted total timing (s)')
        ax.set_ylabel('Recording–satellite fits / 1 s bin')
        ax.set_yscale('symlog',linthresh=1)
        ax.grid(axis='y',alpha=.2)
    fig.suptitle('Paired timing changes, same 215 recording–satellite pairs\nSymmetric-log count axis makes the few large branch changes visible',fontsize=12)
    fig.savefig(HERE/'satellite-timing-change-histogram.png',dpi=180)
    plt.close(fig)

    summary={}
    for method in ['original',*METHODS]:
        group=[r for r in timing_rows if r['method']==method]
        relative=np.array([r['relative_timing_s'] for r in group])
        total=np.array([r['total_timing_s'] for r in group])
        delta=np.array([r['total_timing_change_s'] for r in group])
        summary[method]=dict(fits=len(group),relative_rms_s=float(np.sqrt(np.mean(relative**2))),
            total_rms_s=float(np.sqrt(np.mean(total**2))),absolute_relative_gt_5_s=int(np.sum(abs(relative)>5)),
            absolute_total_ge_19_s=int(np.sum(abs(total)>=19)),
            timing_changes_gt_1_s=int(np.sum(abs(delta)>1)),max_absolute_timing_change_s=float(np.max(abs(delta))))
    new=sum(r['newly_associated'] for r in main_rows)
    lost=sum(r['lost_original_associations'] for r in main_rows)
    result=dict(method='A',scope='full-data development diagnostic, fitted-c, original vs automatic model A',
        windows=15,improved=sum(r['net_gain']>0 for r in main_rows),unchanged_count=sum(r['net_gain']==0 for r in main_rows),
        worsened=sum(r['net_gain']<0 for r in main_rows),
        at_least_80_pct_of_original_missing_restored_net=sum(r['net_fraction_of_original_missing_pct']>=80 for r in main_rows),
        fully_associated_windows=sum(r['variant_associated']==r['observations'] for r in main_rows),
        new_associations=new,lost_associations=lost,net_gain=new-lost,
        original_missing=597,net_fraction_of_original_missing_pct=100*(new-lost)/597,
        supported_original_pair_count=len(active),timing=summary)
    (HERE/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# DSX01: 15-window recovery and satellite timing histograms','',
        'This is a read-only analysis of the saved full-data, fitted-c endpoints. No model was refitted. '
        '“Recovered” below means increased satellite-association coverage, not independently verified '
        'satellite identity or a validated localization improvement. All five A endpoints remain nonstationary.','',
        f"Model A improves counts in {result['improved']}/15 windows; {result['unchanged_count']} have unchanged counts and {result['worsened']} worsens. "
        f"Four windows restore at least 80% of their originally missing associations on a net basis; one reaches 100% window coverage. "
        f"This 80% threshold is a descriptive grouping, not a pre-registered success gate. "
        f"Across all 693 observations, coverage is 96 → 253: {new} newly assigned, {lost} lost, net +{new-lost}. "
        f"That closes {result['net_fraction_of_original_missing_pct']:.1f}% of the original 597 missing associations. "
        'B, C and equal-budget continuation leave all 15 window counts unchanged.','',
        '![All 15 window counts](window-recovery.png)','',
        '| Window | Source / region | Before | A after | Newly assigned / originally missing | Lost | Net missing restored |',
        '|---|---|---:|---:|---:|---:|---:|']
    for r in main_rows:
        lines.append(f"| {r['region_id'][-3:]} | {r['source_id']} RX{r['receiver']}/CH{r['channel']} {r['start_s']:g}–{r['end_s']:g}s | "
            f"{r['original_associated']}/{r['observations']} | {r['variant_associated']}/{r['observations']} ({r['variant_pct']:.1f}%) | "
            f"{r['newly_associated']}/{r['originally_unassociated']} | {r['lost_original_associations']} | {r['net_fraction_of_original_missing_pct']:.1f}% |")
    lines+=['','Source IDs map to the five recording IDs in the [parent report](../2026_10_16_dsx01_models/README.md). '
        'All requested observations remain in the denominator, including other trajectories, positive controls and outliers. '
        'An unchanged count can hide changes of identity or membership; the CSV reports new and lost memberships separately.','',
        '![Satellite timing histograms](satellite-timing-histogram.png)','',
        'The top row shows total orbit-time offsets τ; the bottom removes each recording’s common clock shift, '
        'showing δτ = τ − common. Each entry is one recording–satellite pair, not one GLRT point. '
        'The same satellite can contribute once per recording. All methods use the same 215 pairs and 2 s bins. '
        'These are fitted model parameters, not independently measured satellite clock errors or TLE ages. '
        'The ±20 s bounds apply to total τ; relative offsets can extend beyond them when a nonzero common term is removed.','',
        '| Method | Relative timing RMS (s) | Pairs with abs(δτ) > 5 s | Total abs(τ) ≥ 19 s | Changes > 1 s |',
        '|---|---:|---:|---:|---:|']
    for method in ['original','A','B','C']:
        s=summary[method]
        lines.append(f"| {method} | {s['relative_rms_s']:.3f} | {s['absolute_relative_gt_5_s']}/215 | {s['absolute_total_ge_19_s']}/215 | {s['timing_changes_gt_1_s']} |")
    lines+=['','The timing distribution remains broad. A moves a small number of timing branches substantially, '
        'while B/C largely overlap the original. Lower timing RMS is not a proof of more accurate timing or position.','',
        '![Paired timing changes](satellite-timing-change-histogram.png)','',
        f"Some fitted candidates have little evidence. The following plot fixes the original-supported cohort "
        f"(at least five original assignments), retaining all {len(active)} pairs for every variant even if support is lost:",'',
        '![Fixed supported cohort](supported-satellite-timing-histogram.png)','',
        '| Source | Original common (s) | A common (s) | B common (s) | C common (s) |',
        '|---|---:|---:|---:|---:|']
    for source in sources:
        sid=source['source_id']
        values=[fits[sid,m]['full_scan']['common_timing_s'] for m in ['original','A','B','C']]
        lines.append(f"| {sid} | "+' | '.join(f'{v:.3f}' for v in values)+' |')
    lines+=['','[Window CSV](window-recovery.csv) · [Timing CSV](timing-offsets.csv) · [Summary](summary.json). '
        'Prior target-informed track fits, the automatic full-data variants, and temporal cold starts are distinct '
        'experiments. These tables use only the automatic full-data endpoints, without choosing a different best '
        'model or temporal fold for each window. Original dataset and parent evaluation artifacts are unchanged.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    bindings=[]
    for path in sorted(set(input_files)):
        bindings.append(dict(path=str(path.resolve()),sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()))
    outputs=[]
    for path in sorted(HERE.iterdir()):
        if path.is_file() and path.name!='manifest.json':
            outputs.append(dict(path=path.name,sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()))
    (HERE/'manifest.json').write_text(json.dumps(dict(inputs=bindings,outputs=outputs),indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
