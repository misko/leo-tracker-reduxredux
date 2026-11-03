"""Summarize conditional pilot prediction without asserting duplicate sources."""
import csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from benchmark import ROOT,digest


def main():
    folder=ROOT/'raw-peak-expanded';rp=folder/'replay.json';tp=folder/'two-source-tracking-cfo.json'
    replay=json.loads(rp.read_text());test=json.loads(tp.read_text());assert test['source_sha256']==digest(rp)
    assert all(r['replay_matches_persisted'] for r in replay['results'])
    assert {(r['scan'],tuple(r['probe_key'])) for r in replay['results']}=={(r['scan'],tuple(r['probe_key'])) for r in test['results']}
    rows=[];summary={};fig,axes=plt.subplots(1,2,figsize=(12,6),sharex=True)
    for ax,scan in zip(axes,('A','B')):
        items=[r for r in test['results'] if r['scan']==scan];values=[];valid=[]
        for i,r in enumerate(items):
            for direction,dy,color in [('forward',-.12,'#0072B2'),('reverse',.12,'#D55E00')]:
                q=r[direction];delta=100*(q['two_over_one_test_sse']-1);boundary=q['one_frequency_grid_boundary']
                rows.append(dict(scan=scan,visit=r['probe_key'][0],receiver=r['probe_key'][1],direction=direction,
                    separation_hz=float(r['frequency_separation_hz']),two_source_test_error_change_percent=delta,
                    one_source_grid_boundary=boundary,template_correlation=q['template_correlation'],condition_number=q['normalized_design_condition']))
                values.append(delta)
                if not boundary:valid.append(delta)
                ax.scatter(delta,i+dy,color=color,marker='^' if boundary else 'o',s=45,label=direction if i==0 else None)
        ax.axvline(0,color='black',lw=1);ax.set_yticks(range(len(items)),[f"visit {r['probe_key'][0]} / RX{r['probe_key'][1]}" for r in items]);ax.invert_yaxis()
        ax.set_title(f'Scan {scan} · {len(items)} sampled visits');ax.grid(axis='x',alpha=.2);ax.legend()
        ax.set_xlabel('Two-source held-out SSE change versus one-source (%)\nPositive = two-source prediction is worse')
        summary[scan]=dict(pairs=len(items),split_comparisons=len(values),nonboundary_comparisons=len(valid),
            nonboundary_two_source_improvements=sum(v<0 for v in valid),minimum_change_percent=min(values),maximum_change_percent=max(values),
            eligible_visit_population=replay['selection'][scan]['eligible_visits'])
    fig.suptitle('Close GLRT alternatives: conditional one-source versus two-source pilot prediction')
    fig.text(.5,.02,'Epoch/hypotheses were selected using the full probe; this is not independent detector validation.\nTriangles mark a one-source search-boundary hit. No measurements merged; coverage unchanged.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.09,1,.95));fig.savefig(folder/'comparison.png',dpi=160);plt.close(fig)
    with (folder/'comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (folder/'summary.json').write_text(json.dumps(dict(summary=summary,sources={str(p):digest(p) for p in (rp,tp)},
        warning='Evidence against counting these close alternatives as independently resolved sources under this conditional pilot model. Not proof of a single physical source, not satellite identification, not a population duplicate-rate estimate.'),indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
