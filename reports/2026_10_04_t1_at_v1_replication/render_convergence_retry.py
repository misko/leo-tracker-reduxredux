"""Publish optimizer continuation comparisons without overwriting originals."""
import csv
import hashlib
import json
from pathlib import Path
from plot_assigned_vs_position import HERE, main as plot


def main():
    out=HERE/'convergence-retry'
    with (HERE/'cohort-positions.csv').open(newline='') as f:
        rows=[r for r in csv.DictReader(f) if r['case']=='all-100']
    summary=[]
    for row in rows:
        path=out/'final'/f'{row["scan"]}-{row["arm"]}.json'
        if not path.exists():continue
        r=json.loads(path.read_text());best=r['best']
        summary.append(dict(scan=row['scan'],arm=row['arm'],old_distance_m=float(row['distance_m']),
                            new_distance_m=r['distance_m'],position_change_m=r['movement_m_vs_original'],
                            old_converged=row['converged'],new_converged=r['converged'],
                            old_kkt=float(row['kkt_residual']),new_kkt=best['kkt_residual'],
                            score_change=r['delta_score_vs_original'],boundary=r['boundary'],
                            status=best['status'],fixed_location=best['fixed_location']))
        row.update(distance_m=r['distance_m'],east_m=1000*best['point_km'][0],north_m=1000*best['point_km'][1],
                   best_score=best['objective'],delta_score=best['objective']-float(row['roof_score']),
                   converged=str(r['converged']),boundary=str(r['boundary']),kkt_residual=best['kkt_residual'],
                   source=str(path),source_sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest())
    for name,entries in [('position-results.csv',rows),('final-summary.csv',summary)]:
        with (out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(entries[0]));w.writeheader();w.writerows(entries)
    plot(out/'position-results.csv',out/'assigned-windows-vs-position')
    for r in summary:
        if r['old_converged']=='False':print(r)
    print('Unconverged now',sum(r['converged']=='False' for r in rows),'of',len(rows))


if __name__=='__main__':main()
