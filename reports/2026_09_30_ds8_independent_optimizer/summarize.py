import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def read(path):
    return json.loads(path.read_text())


def main():
    result=read(HERE/'result.json')
    for name,digest in result['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    spec=importlib.util.spec_from_file_location('geometry',REPORTS/'2026_09_29_ds8_union40/summarize.py')
    geometry=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geometry)
    fit=result['fit']
    summary={k:v for k,v in fit.items() if k!='x'}
    summary['elapsed_seconds']=result['elapsed_seconds']
    if fit['qualified']:
        summary['reference_distance_m']=geometry.distance(fit['estimate_deg'],geometry.REFERENCE)
        controls={
            'original_rank':read(REPORTS/'2026_09_29_ds8_union40/rank.json')['fit'],
            'corrected':read(REPORTS/'2026_09_29_ds8_union_timing/refit_old.json')['fit']}
        summary['controls']={name:dict(endpoint_gap_m=geometry.distance(fit['estimate_deg'],c['estimate_deg']),
                                      training_gain=fit['score']-c['score'],held_gain=fit['held_score']-c['held_score'])
                             for name,c in controls.items()}
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
