"""Reporting-only detail panels; preserve every original frozen scientific file."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import experiment as e


def main():
    for name in ('RF_seal.json','report_seal.json'):
        for path,expected in e.read(e.HERE/name)['files'].items():
            if e.sha(path)!=expected: raise ValueError('sealed file changed')
    rows=e.read(e.HERE/'rows.json'); contexts=[]; numeric=[]; closures=[]
    for case in e.CASES:
        context=e.read(e.HERE/case/'context.json');contexts.append(dict(case=case,eligible_generators=len(context['eligible_generating_indices']),
            catalogue_count=context['catalogue_count'],generated_norads=context['selected_generating_norads']))
        for trial in range(6):
            truth=e.read(e.HERE/case/('trial'+str(trial))/'generation.json');closures.append(truth['maximum_forward_identity_error_hz'])
            for arm in e.ARMS:
                result=e.read(e.HERE/case/('trial'+str(trial))/(arm+'_result.json'))
                for candidate in result['candidates']:
                    numeric.append(dict(case=case,trial=trial,kind='physical' if trial<4 else 'unresolved',arm=arm,
                        norad=candidate['norad'],status=candidate['status'],numerically_qualified=candidate['numerically_qualified'],
                        score_error=candidate.get('score_error'),adaptive_error=candidate.get('adaptive_score_error'),
                        adaptive_failure=candidate.get('adaptive_failure'),blocked_reason=candidate.get('reason')))
    record=dict(contexts=contexts,candidate_contexts=len(numeric),defined_candidates=sum(r['status']=='complete' for r in numeric),
        blocked_candidates=[r for r in numeric if r['status']!='complete'],
        finite_unqualified_candidates=[r for r in numeric if r['status']=='complete' and not r['numerically_qualified']],
        adaptive_failure_count=sum(r['adaptive_failure'] is not None for r in numeric),
        maximum_primary_dense_error=max(r['score_error'] for r in numeric if r['score_error'] is not None),
        maximum_finite_adaptive_error=max(r['adaptive_error'] for r in numeric if r['adaptive_error'] is not None),
        maximum_forward_closure_hz=max(closures),new_orbit_propagations=0,new_scores=0,new_fits=0)
    e.write(Path('details.json'),record)
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    for j,arm in enumerate(e.ARMS):
        for i,kind in enumerate(('physical','unresolved')):
            ax=axes[i,j];chosen=sorted((r for r in rows if r['arm']==arm and r['kind']==kind),key=lambda r:(r['case'],r['trial']))
            for n,row in enumerate(chosen):
                ax.scatter(n,row['best_physical_minus_null'],color='#2563eb' if kind=='physical' else '#d97706',
                    marker='o' if row['ordering_numerically_qualified'] else 'x',s=50)
            labels=[f'{r["case"][-4:]} {"P" if kind=="physical" else "U"}{r["trial"] if kind=="physical" else r["trial"]-4}' for r in chosen]
            ax.set_xticks(range(len(chosen)),labels,rotation=40);ax.set(title=arm+'; '+kind,ylabel='Best physical minus null objective')
            ax.axhline(0,color='black',lw=.6);ax.grid(alpha=.2)
    fig.suptitle('Conditional density gaps; × = ordering guard failed (visibility or numerical)')
    fig.savefig(e.HERE/'candidate_null_gaps_detail.png',dpi=160);plt.close(fig)
    files=[e.HERE/name for name in ('details.py','details.json','candidate_null_gaps_detail.png')]
    e.write(Path('detail_seal.json'),dict(files={str(p):e.sha(p) for p in files},original_report_seal_sha256=e.sha(e.HERE/'report_seal.json'),
        RF_seal_sha256=e.sha(e.HERE/'RF_seal.json'),reporting_only=True))
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()
