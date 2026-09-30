import hashlib
import json
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import ds7_export_baseline as exporter
import ds7_fast_baseline_adapter as baseline


def main(unit):
    started=time.monotonic()
    plan=json.loads((HERE/'export-plan.json').read_text())
    for name,h in plan['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    row=next(r for r in plan['captures'] if r['unit_id']==unit)
    folder=HERE/'exports'/unit
    observation=folder/'observations.json'
    bank=folder/'banks/manifest.json'
    if observation.exists() or bank.exists():
        raise FileExistsError('Preserve existing outputs; explicit stage recovery required')
    doc=exporter.export(row,observation,Path('/srv/bulk/leo'),Path('/var/lib/leo/tle'))
    analysis=json.loads(Path(row['analysis_path']).read_text())
    assert doc['analysis_manifest_sha256']==analysis['glrt']['metrics_manifest_sha256']
    exporter.export_banks(row,observation,folder/'banks',Path('/srv/bulk/leo'),Path('/var/lib/leo/tle'))
    paths=[observation,bank,folder/'banks/banks.npz']
    inputs=dict(session_id=row['session_id'],manifest_sha256=row['manifest_sha256'],artifacts=[dict(kind='observations' if i==0 else 'candidates',path=str(p),sha256='sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()) for i,p in enumerate(paths)])
    loaded=baseline.load_documents(dict(config=plan['config'],inputs=[inputs]))[0]
    assert loaded['sample_rate_hz']==row['sample_rate_hz']
    bank_doc=json.loads(bank.read_text())
    assert all(p['collected_utc_ns']<loaded['start_utc_ns']-505_000_000_000 for p in bank_doc['provider_sources'])
    result=dict(unit=unit,input=inputs,tracks=len(loaded['tracks']),observations=sum(len(t['y']) for t in loaded['tracks']),eligibility_exclusions=loaded['eligibility_exclusions'],mint_analysis_match=True,elapsed_seconds=time.monotonic()-started,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with (folder/'validated.json').open('x') as out:json.dump(result,out,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ['input','eligibility_exclusions']},indent=2))


if __name__=='__main__':main(sys.argv[1])
