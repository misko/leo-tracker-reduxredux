"""Publish the causal-shortlist challenge and carry forward unresolved identities."""
import argparse
import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from debug_fast_graph_unassociated import read, write
from review_annotation_competition import matched_expansion


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    sources={};evidence={}
    def load(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        value=read(path);evidence[str(path)]=value;return value
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n')
            w.writeheader();w.writerows(rows)
    s=args.study;root=s/'shifted-rejected-wide-candidates-v1'
    protocol=load(root/'protocol.json');execution=load(root/'execution.json')
    if any(r['status']!='complete' for r in execution):raise ValueError('unfinished expansion')
    for path,digest in protocol['source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('source changed')
    previous=args.previous/'annotation_ledger.csv';sources[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};rows=[];scores=[]
    for job in protocol['jobs']:
        tid=job['track_id'];old=load(s/'shifted-annotation-inventory-v1'/tid/'result.json');new=load(root/tid/'result.json')
        load(root/(tid+'-terminal.json'));load(root/tid/'protocol.json')
        counts=matched_expansion(old,new);a=old['annotation'];b=new['annotation']
        rows.append(dict(scan=job['label'],track_id=tid,norad=b['norad'],old_status=a['status'],new_status=b['status'],
            old_margin=a['minimum_margin'],new_margin=b['minimum_margin'],
            counts=' '.join(str(r['expanded']) for r in counts),
            unique_candidates=len({p['norad'] for f in new['folds'] for p in f['proposals']})))
        for f in new['folds']:
            for arm in ('c0','fitted_c'):
                best=min(p['arms'][arm]['scores']['conditional_target']['negative_twice_log_density'] for p in f['proposals'])
                for p in f['proposals']:
                    value=p['arms'][arm]['scores']['conditional_target']
                    scores.append(dict(scan=job['label'],track_id=tid,seed=f['seed'],arm=arm,norad=p['norad'],
                        delta_negative_twice_log_density=value['negative_twice_log_density']-best,RMS_hz=value['rms_hz']))
        byid[tid].update(predictive_recheck_source=str(root/tid/'result.json'),predictive_recheck_state=b['status'],
            predictive_recheck_minimum_margin=b['minimum_margin'],candidate_competition_source=str(root/tid/'result.json'),
            candidate_competition_status=b['status'])
    csvout('candidate_comparison.csv',rows);csvout('candidate_scores.csv',scores);csvout('annotation_ledger.csv',ledger)
    pending={}
    for kind in ('shifted','role'):
        name='remaining_'+kind+'_candidates.json';pending[kind]=len(load(args.previous/name));shutil.copyfile(args.previous/name,out/name)
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,row in zip(axes,rows,strict=True):
        ax.bar(['Original shortlist','Expanded shortlist'],[row['old_margin'],row['new_margin']],color=['#777777','#0072b2'])
        ax.axhline(10,color='#d55e00',ls='--',label='Existing identity margin threshold')
        ax.set(title=row['scan']+' / '+str(row['norad']),ylabel='Minimum held-score margin across folds and c arms')
        ax.legend(fontsize=7);ax.grid(axis='y',alpha=.2)
    fig.savefig(out/'figures/candidate_margin.png',dpi=150);plt.close(fig)
    batch=load(args.previous/'summary.json')
    summary=dict(cases=rows,batch=batch,remaining=pending,production_changed=False,position_rerun=False,
        original_candidate_scores_replayed=True,goal_complete=False)
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    table='\n'.join('| '+r['scan']+' | '+str(r['norad'])+' | '+f"{r['old_margin']:.2f} → {r['new_margin']:.2f}"+' | '+r['new_status']+' | '+r['counts']+' |' for r in rows)
    (out/'README.md').write_text(f'''# Causal candidate competition before model correction

Expanding the shortlist changes one previously supported identity to **ambiguous**. Both targets were already withheld after shared-family consistency failures. The expansion does not authorize either target for localization, and does not prove that the runner-up is the true satellite.

The two targets are all shared-family failures from shifted batch one, chosen without GPS ranking. Candidate budget increases from three to twelve; actual eligible counts remain smaller. The algorithm still nominates from its existing causal catalogue using training-only geometry at the regional centre, training-derived positions and regional grid points. It retains the top three geometry offers at each location/arm before deduplicating and applying the enlarged cap. This is a wider shortlist, **not exhaustive catalogue likelihood evaluation**, and it remains conditional on the incumbent graph, receiver model and training positions.

| Scan | Preferred NORAD | Minimum margin, original → expanded | Reviewed status | Actual candidates in three folds |
| --- | --- | --- | --- | --- |
{table}

![Candidate margin](figures/candidate_margin.png)

For RX1 CH8 / 67618, new competitor **50805** reduces the minimum held-score margin from about 192.36 to 31.40, while 67618 remains preferred in all three folds and both c arms. For RX1 CH3 / 68057, competitor **55951** reduces the margin from about 56.93 to 7.05, below the existing threshold of ten. The leading identity remains 68057 in every fold; its separation from alternatives is insufficient. A score margin is not a calibrated probability of correct identity.

The experiment exactly replays original candidates' held scores (within numerical tolerance), aliases, c arms and physical random partitions. Observations, 12-second blocks, two-second guards, priors and position-training budgets are unchanged. The three partitions overlap and are not independent replications. No GPS, future TLE or raw-IQ modification enters candidate selection. [Full candidate scores](candidate_scores.csv) preserve all tested alternatives and both c arms. Terminal receipts and source hashes accompany the evidence.

## Implication for systematic recovery

The previous [measurement and shared-family investigation](../2026_10_30_shifted_family_challenges/README.md) found no joined-fragment seam, only small local IQ CFO corrections, and no fully qualified shared correction. The present result identifies a concrete additional limitation: a narrow geometry shortlist can overstate separation from competing satellites. It would be premature to attribute the entire discrepancy to LNB or orbital errors.

For [shifted batch three](../2026_10_30_shifted_annotation_batch3/README.md), all **{batch['competition_reviews']}** initially supported identities receive the same expansion **before** position inclusion. **{batch['competition_downgrades']}** lose conditional support. The resulting batch has **{batch['qualified_curves']} curves / {batch['qualified_points']} points** passing matched RF, residual, ownership and numerical checks in separate position trials. Position gains and regressions remain in that report; additional associations alone are not evidence of improved localization.

The ledger now records 68057 as ambiguous and retains both targets' failed-inclusion history. **{pending['shifted']} shifted-origin cases and {pending['role']} older-role cases remain; these queues overlap.** No production change or new ALGO promotion follows from this result.

Next, apply the broader competition check to previously qualified recoveries before joint/cohort promotion. Where satellite competition remains inconclusive, seek independent same-satellite evidence across channels/receivers or native alternative-peak evidence. Any extra receiver/orbit flexibility must predict held family data, rather than merely lower in-sample RMS. Do not use known GPS error to choose an identity or rescue a failed fit.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
