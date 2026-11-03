"""Orbit-blind candidate/score/separation audit for all eighteen refinements.

Only pair histograms collapse numerically exact original alias copies: same
probe, wrapped original frequency (microhertz), epoch (micro-sample), and saved
margin (1e-12). The solver inputs and window denominators are not modified.
Large pair separations can be different signals, not necessarily bad estimates.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from cohort import digest
from refinement import circular

HERE=Path(__file__).resolve().parent
BINS=np.array([0.,10.,50.,100.,300.,1000.,np.inf])
LABELS=['<10','10–50','50–100','100–300','300–1,000','≥1,000']


def canonical_rows(original):
    seen=set();keep=[]
    for i,row in enumerate(original):
        epoch=row['integer_epoch_sample']+row['fractional_epoch_offset_samples']
        key=(tuple(row['probe_key']),round(float(circular(row['original_hz'])),6),round(epoch,6),round(row['original_margin'],12))
        if key not in seen:
            seen.add(key);keep.append(i)
    return keep


def pair_histogram(refined,indices,cutoff):
    groups=defaultdict(list)
    for i in indices:
        row=refined[i]
        score=row['refinement'].get('margin',row['original_margin'])
        if score>=cutoff:groups[tuple(row['probe_key'])].append(row['output_hz'])
    separations=[]
    for values in groups.values():
        for i in range(len(values)):
            separations.extend(abs(circular(np.asarray(values[i+1:])-values[i])).tolist())
    counts=np.histogram(separations,bins=BINS)[0]
    return dict(cutoff=cutoff,candidates=sum(map(len,groups.values())),windows=len(groups),
                multi_candidate_windows=sum(len(v)>1 for v in groups.values()),pairs=len(separations),
                counts=counts.tolist(),percentages=(100*counts/max(1,len(separations))).tolist())


def run(inputs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cohort=json.loads((HERE/'cohort-v2.json').read_text())
    summary=[]
    output=HERE/'refinement-audit';output.mkdir(exist_ok=True)
    for scan in cohort['scans']:
        label=scan['label'];directory=inputs/label
        original_path=directory/'observations.json';refined_path=directory/'refinement/refined.json'
        original=json.loads(original_path.read_text());refined=json.loads(refined_path.read_text())
        if refined['summary']['signature']['observations_sha256']!=digest(original_path.read_bytes()):raise ValueError('refinement binding mismatch')
        rr=refined['records'];oo=original['records']
        if len(rr)!=len(oo) or any(r['candidate_id']!=o['candidate_id'] for r,o in zip(rr,oo)):raise ValueError('refinement row alignment mismatch')
        canonical=canonical_rows(oo)
        cases=[pair_histogram(rr,canonical,c) for c in (0.,.025,.2,.6)]
        fig,axes=plt.subplots(2,2,figsize=(14,8),sharey=True)
        for ax,case in zip(axes.flat,cases):
            bars=ax.bar(np.arange(6),case['percentages'],color='#0072b2')
            ax.bar_label(bars,labels=[f'{p:.1f}%' for p in case['percentages']],padding=3,fontsize=9)
            ax.set_xticks(np.arange(6),LABELS,fontsize=8)
            ax.set(title=f'Margin ≥ {case["cutoff"]:g} · {case["pairs"]:,} pairs\n{case["candidates"]:,} candidates; {case["multi_candidate_windows"]:,} multi-candidate windows',
                   xlabel='Alias-aware pair separation (Hz)',ylabel='Within-window candidate pairs (%)',ylim=(0,105))
            ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
        fig.suptitle(f'{label} · refined GLRT candidate separation by score cutoff',fontsize=15)
        fig.text(.5,.016,f'{len(oo):,} saved hypotheses; {len(canonical):,} after exact original alias-copy removal for this histogram only.\nEvery within-probe pair counts; n candidates contribute n(n−1)/2 pairs. No orbit input; no physical-signal consolidation.',ha='center',fontsize=10)
        fig.tight_layout(rect=(0,.08,1,.94));fig.savefig(output/f'{label}-pair-cutoffs.png',dpi=140);plt.close(fig)
        delta=np.array([float(circular(r['output_hz']-r['original_hz'])) for r in rr])
        before=np.array([r['original_margin'] for r in rr]);after=np.array([r['refinement'].get('margin',r['original_margin']) for r in rr])
        fig,axes=plt.subplots(1,3,figsize=(14,4.5))
        axes[0].hist(delta,bins=np.linspace(-1000,1000,81),color='#0072b2')
        axes[0].set(title='Candidate-guided frequency update',xlabel='Wrapped frequency change (Hz)',ylabel='Saved candidate records')
        axes[1].hist(before,bins=np.linspace(0,1,51),histtype='step',label='Original',color='#d55e00')
        axes[1].hist(after,bins=np.linspace(0,1,51),histtype='step',label='Refined',color='#0072b2')
        axes[1].set(title='Same passing hypotheses',xlabel='GLRT margin');axes[1].legend()
        sizes=[len(oo),len(canonical),len(refined['top_rows'])]
        bars=axes[2].bar(['Saved\nhypotheses','Original alias\ncanonical','Top /\nwindow'],sizes,color=['#999999','#56b4e9','#0072b2'])
        axes[2].bar_label(bars,padding=3);axes[2].set_ylim(0,max(sizes)*1.2);axes[2].set_title('Different counting units')
        fig.suptitle(f'{label} · refinement before/after and accounting',fontsize=15)
        outside=int(sum(abs(delta)>1000))
        fig.text(.5,.015,f'{outside} frequency changes outside displayed ±1 kHz. {refined["summary"]["failed_refinements"]} failed refinements retain original values.\nOriginal rejected hypotheses were not reprocessed. Window denominator remains unchanged.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.1,1,.92));fig.savefig(output/f'{label}-before-after.png',dpi=140);plt.close(fig)
        item=dict(scan=label,raw_candidates=len(oo),canonical_candidates=len(canonical),windows=len(refined['top_rows']),
                  failed_refinements=refined['summary']['failed_refinements'],outside_update_panel=outside,cases=cases,
                  sources={str(p):digest(p.read_bytes()) for p in (original_path,refined_path,Path(__file__))})
        summary.append(item);print('REFINEMENT AUDIT',label,len(oo),len(canonical),flush=True)
    (output/'summary.json').write_text(json.dumps(dict(scope=__doc__,scans=summary),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);a=p.parse_args();run(a.inputs)
