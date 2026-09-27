"""Summarize the frozen conditional clock diagnostic without truth fitting."""
import json
import csv
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    results=[json.loads((HERE/f'{s}.json').read_text()) for s in protocol['sessions'] if (HERE/f'{s}.json').exists()]
    comparisons={}
    for name,a,b in [('linear_vs_constant','1','0'),('quadratic_vs_linear','2','1')]:
        gains=[r['arms'][a]['held']-r['arms'][b]['held'] for r in results]
        comparisons[name]=dict(improved=sum(g>0 for g in gains),total_gain=sum(gains),median_gain=statistics.median(gains) if gains else None)
    summary=dict(completed=len(results),expected=len(protocol['sessions']),comparisons=comparisons,
        unconverged=[dict(session=r['session_id'],order=k) for r in results for k,v in r['arms'].items() if not v['converged']],
        iteration_audit_max_abs_held_change=max((abs(r['iteration_audit']['held_change']) for r in results),default=0),
        iteration_audit_unconverged=[r['session_id'] for r in results if not r['iteration_audit']['converged']])
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (HERE/'scores.csv').open('w') as stream:
        writer=csv.writer(stream)
        writer.writerow(['scan_id','linear_minus_constant_held_log_score','quadratic_minus_linear_held_log_score','all_arms_converged'])
        for r in results:
            writer.writerow([r['session_id'],r['arms']['1']['held']-r['arms']['0']['held'],r['arms']['2']['held']-r['arms']['1']['held'],all(a['converged'] for a in r['arms'].values())])
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
