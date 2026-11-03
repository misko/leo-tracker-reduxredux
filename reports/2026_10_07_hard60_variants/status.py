"""Fast paired interim summary; denominators are completed cases only."""
import json
import numpy as np
import run_variants as run
from summarize import distance_km
from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior


def main():
    old=run.read(run.SOFT/'summary.json')
    control={(r['label'],r['arm']):r for r in old['rows'] if r['phase']=='sigma2_60'}
    r=run.read(run.OLD/'evaluation.json');reference=[r['reference_latitude_deg'],r['reference_longitude_deg']]
    groups={}
    rows=[]
    for label in run.LABELS:
        prior=RegionalPrior(**run.read(run.OLD/'inputs'/label/'inputs.json')['prior'])
        for phase in run.PHASES:
            path=run.HERE/'results'/label/phase/'result.json'
            if not path.exists():continue
            result=run.read(path)
            for arm,entry in result['selections'].items():
                s=entry['result'];baseline=control[label,arm]['error_km']
                error=distance_km(*coordinates(prior,s['vector'][:2]),reference) if s else None
                row=dict(label=label,phase=phase,arm=arm,error_km=error,control_km=baseline,
                    change_km=error-baseline if error is not None else None)
                groups.setdefault((phase,arm),[]).append(row);rows.append(row)
    summary=[]
    for (phase,arm),group in groups.items():
        accepted=[r for r in group if r['error_km'] is not None]
        deltas=[r['change_km'] for r in accepted]
        worst=max(accepted,key=lambda r:r['error_km']) if accepted else None
        summary.append(dict(phase=phase,arm=arm,completed=len(group),accepted=len(accepted),
            improved=sum(d<-.001 for d in deltas),worsened=sum(d>.001 for d in deltas),
            unchanged=sum(abs(d)<=.001 for d in deltas),median_paired_change_km=float(np.median(deltas)) if deltas else None,
            worst=worst))
    run.engine.write(run.HERE/'status.json',dict(summary=summary,rows=rows))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
