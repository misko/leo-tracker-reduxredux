"""Render all cells and cohort comparisons without selecting fits by reference error."""
import csv,json
from pathlib import Path
from summarize import METHODS
HERE=Path(__file__).resolve().parent
LABELS=dict(iid='Original independent Student-t',shared='Shared scale',correlated='Shared scale + 10 s correlation',contrast='Frequency contrasts',q020='q020',q020_correlated='q020 + 10 s correlation',cone40='Shared scale + 40° cones',q020_cone40='q020 + 40° cones',slope='q020 + shared candidate slope',curvature='q020 + shared curvature')
def number(v):return '—' if v is None else f'{v:.0f}'
def main():
    data=json.loads((HERE/'summary.json').read_text());plan=json.loads((HERE/'export-plan.json').read_text())
    previous={r['method']:r for r in json.loads((HERE.parent/'2026_09_30_ds10_single10/summary.json').read_text())['summary']}
    lines=['# DS11: ten methods on 32 independent scans','','Distances are metres to the unsurveyed roof reference. Failure cells remain in attempted denominators. Each scan is fitted independently.','','| Method | Qualified | Median m | P90 m | Min m | Max m | <1 km / attempted | Matched median m | Runtime s |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in sorted(data['summary'],key=lambda r:r['median_m'] if r['median_m'] is not None else float('inf')):
        lines.append(f"| {LABELS[r['method']]} | {r['qualified']}/32 | {number(r['median_m'])} | {number(r['p90_m'])} | {number(r['min_m'])} | {number(r['max_m'])} | {r['below1km']}/32 | {number(r['matched_all_methods_median_m'])} | {r['median_wall_with_prerequisite_s']:.2f} |")
    lines+=['',f"Matched medians use the {len(data['all_methods_qualified_scan_indices'])} scans qualified by all ten methods. Runtime includes q020 prerequisites for slope and curvature; engineering retries are separately retained.",'','## All selected scans','','Column names are method IDs in [run.py](run.py). Unqualified or failed cells are printed as status, not zero.','','| Scan / chronological rank | '+ ' | '.join(METHODS)+' |','|---|'+ '|'.join(['---:']*10)+'|']
    for i,row in enumerate(plan['captures']):
        cells={r['method']:r for r in data['cells'] if r['scan_index']==i}
        lines.append(f"| S{i+1:02d} / {row['ordinal']} | "+' | '.join(number(cells[m]['distance_m']) if cells[m]['status']=='qualified' else cells[m]['status'] for m in METHODS)+' |')
    lines+=['','## Frozen scan membership','','| Scan | DS11 rank | Session | MS/s |','|---|---:|---|---:|']
    for i,r in enumerate(plan['captures']):lines.append(f"| S{i+1:02d} | {r['ordinal']} | {r['session_id']} | {r['sample_rate_hz']/1e6:g} |")
    lines+=['','## DS10 versus DS11','','These are different scan populations (8 versus 32), not paired measurements of improvement. Methods and fit settings are unchanged.','','| Method | DS10 median m | DS11 median m | DS10 P90 m | DS11 P90 m |','|---|---:|---:|---:|---:|']
    comparison=[]
    for r in data['summary']:
        old=previous[r['method']]
        lines.append(f"| {LABELS[r['method']]} | {number(old['median_m'])} | {number(r['median_m'])} | {number(old['p90_m'])} | {number(r['p90_m'])} |")
        comparison.append(dict(method=r['method'],ds10_median_m=old['median_m'],ds11_median_m=r['median_m'],ds10_p90_m=old['p90_m'],ds11_p90_m=r['p90_m'],ds10_qualified=old['qualified'],ds11_qualified=r['qualified']))
    lines+=['','## Common held-observation diagnostic','','All fitted points are scored by the same q020 held model. These are not native cross-model likelihoods or independent future-scan tests.','','| Method | Sum held-score change versus q020 | Paired scans |','|---|---:|---:|']
    for r in data['summary']:
        gain='—' if r['common_q020_held_gain'] is None else f"{r['common_q020_held_gain']:.3f}"
        lines.append(f"| {LABELS[r['method']]} | {gain} | {r['common_score_pairs']} |")
    (HERE/'TABLE.md').write_text('\n'.join(lines)+'\n')
    cells=[dict(**r,session_id=plan['captures'][r['scan_index']]['session_id'],ds11_ordinal=plan['captures'][r['scan_index']]['ordinal']) for r in data['cells']]
    for name,rows in [('per-scan.csv',cells),('ds10-comparison.csv',comparison)]:
        with (HERE/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
if __name__=='__main__':main()
