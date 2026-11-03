"""Replay learned target scores through the full geographic likelihood."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent


def read(p):return json.loads(p.read_text())


def main():
    stats=read(HERE/'statistics.json');result=read(HERE/'results.json')
    for obj in [stats,result]:
        for name,digest in obj['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    base=HERE.parent/'2026_09_30_ds10_scale_weighting'
    plan=read(base/'plan.json')
    for name,digest in plan['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    spec=importlib.util.spec_from_file_location('scale_model',base/'scaled_model.py')
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    docs=model.helper.baseline.load_documents(dict(config=plan['config'],inputs=plan['inputs']))
    rows=[r for r in stats['rows'] if r['dataset']=='DS10'];audits={}
    for arm in ['constant','variable']:
        fit=result['summary']['fits'][arm]
        assert fit['qualified'];p=fit['params'];ratios={}
        for r in rows:
            value=p[r['rx']]
            if arm=='variable':value+=p[2+r['rx']]*math.log(r['feature']/100.)
            ratios[r['session_id'],r['track_id']]=math.exp(value)
        scored=model.Scaled(docs,plan['config'],ratios).evaluate(plan['baseline']['x'],gradient=False,held=True)
        gain=sum(r['held_log_score'] for r in scored['rows'])-plan['baseline']['held_score']
        expected=result['summary'][arm]['total_log_score_gain'];error=abs(gain-expected)
        assert error<1e-7
        audits[arm]=dict(full_model_gain=gain,statistics_gain=expected,absolute_difference=error)
    (HERE/'audit.json').write_text(json.dumps(audits,indent=2)+'\n')
    print(json.dumps(audits,indent=2))


if __name__=='__main__':main()
