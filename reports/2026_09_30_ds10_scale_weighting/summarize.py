import hashlib
import importlib.util
import json
from pathlib import Path

from scaled_model import Scaled,helper

HERE=Path(__file__).resolve().parent


def read(p):return json.loads(p.read_text())


def main():
    plan=read(HERE/'plan.json')
    for name,digest in plan['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    spec=importlib.util.spec_from_file_location('geo',HERE.parent/'2026_09_29_ds8_union40/summarize.py')
    geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=plan['inputs']))
    base=plan['baseline']
    rows=[]
    for arm in ['constant','variable']:
        result=read(HERE/f'{arm}.json')
        for name,digest in result['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
        f=result['fit']
        row=dict(arm=arm,qualified=f['qualified'],elapsed_seconds=result['elapsed_seconds'])
        if f['qualified']:
            ratios={(w['session_id'],w['track_id']):w[arm] for w in plan['weights']}
            fixed=Scaled(docs,plan['config'],ratios).evaluate(base['x'],gradient=False,held=True)
            fixed_held=sum(r['held_log_score'] for r in fixed['rows'])
            row.update(reference_distance_m=geo.distance(f['estimate_deg'],geo.REFERENCE),
                       position_shift_m=geo.distance(f['estimate_deg'],base['estimate_deg']),
                       held_gain=f['held_score']-base['held_score'],
                       original_model_held_gain=f['original_model_held']-base['held_score'],
                       fixed_position_held_gain=fixed_held-base['held_score'],
                       location_refit_held_gain=f['held_score']-fixed_held,
                       training_gain=f['score']-base['score'])
        rows.append(row)
    summary=dict(baseline_reference_distance_m=geo.distance(base['estimate_deg'],geo.REFERENCE),
                 tracks=1443,supported=len(plan['weights']),rows=rows)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
