"""Retain the lowest-scoring available point under each prior, without refitting.

Same three final candidate locations are evaluated for every prior within each
scan/RF arm. This closes a small cross-prior search gap without falsely calling
the selected point stationary. Original final-fit artifacts are preserved.
"""
import json
from pathlib import Path
import timing_prior_ablation as experiment
from timing_prior_ablation import PriorObjective,load,reprice,diagnostics,best_record,digest,serial

SOURCE=experiment.OUT/'final'
OUT=experiment.OUT/'closed'


def main():
    OUT.mkdir(exist_ok=True)
    changes=[]
    for scan in experiment.SCANS:
        data,meta,_=load(scan)
        for arm in experiment.ARMS:
            paths={m:SOURCE/f'{scan}-{arm}-{m}.json' for m in experiment.PRECISIONS}
            records={m:json.loads(p.read_text()) for m,p in paths.items()}
            for mode,precision in experiment.PRECISIONS.items():
                obj=PriorObjective(data,meta['rf_center_hz'],arm,precision);original=records[mode]
                candidates=[dict(reprice(obj,r['best']),stage=f'final-candidate-{m}') for m,r in records.items()]
                best=best_record([original['best']]+candidates)
                metrics=diagnostics(obj,data,best)
                assert metrics['objective']<=original['objective']+1e-7
                result=dict(original,best=best,records=original['records']+candidates,**metrics,
                    final_candidate_evaluations=3,finalization_scope=__doc__,
                    finalization_sources_sha256={m:digest(p) for m,p in paths.items()},
                    finalization_implementation_sha256=digest(Path(__file__)))
                (OUT/paths[mode].name).write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
                if metrics['objective']<original['objective']-1e-7:
                    changes.append(dict(scan=scan,arm=arm,mode=mode,score_improvement=original['objective']-metrics['objective'],
                        previous_distance_m=original['distance_m'],distance_m=metrics['distance_m'],converged=metrics['converged']))
    experiment.OUT=OUT;experiment.render();print(json.dumps(changes,indent=2))


if __name__=='__main__':main()
