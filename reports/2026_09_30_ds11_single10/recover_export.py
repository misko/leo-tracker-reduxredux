"""Complete a timed-out export from its immutable observations, once, stage bounded."""
import hashlib,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'tools'))
import ds7_export_baseline as exporter
import ds7_fast_baseline_adapter as baseline

def main(unit):
    started=time.monotonic();plan=json.loads((HERE/'export-plan.json').read_text())
    for name,h in plan['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h
    row=next(r for r in plan['captures'] if r['unit_id']==unit)
    original=json.loads((HERE/'receipts'/f'{unit}.json').read_text());assert original['state']=='failed'
    folder=HERE/'exports'/unit;observation=folder/'observations.json';bank=folder/'banks/manifest.json'
    doc=json.loads(observation.read_text());before=hashlib.sha256(observation.read_bytes()).hexdigest()
    assert doc['session_id']==row['session_id'] and doc['manifest_sha256']==row['manifest_sha256']
    analysis=json.loads(Path(row['analysis_path']).read_text())
    assert doc['analysis_manifest_sha256']==analysis['glrt']['metrics_manifest_sha256']
    assert not (folder/'banks').exists(),'Partial bank requires separate review'
    exporter.export_banks(row,observation,folder/'banks',Path('/srv/bulk/leo'),Path('/var/lib/leo/tle'))
    assert hashlib.sha256(observation.read_bytes()).hexdigest()==before
    paths=[observation,bank,folder/'banks/banks.npz']
    entry=dict(session_id=row['session_id'],manifest_sha256=row['manifest_sha256'],artifacts=[dict(kind='observations' if i==0 else 'candidates',path=str(p),sha256='sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()) for i,p in enumerate(paths)])
    loaded=baseline.load_documents(dict(config=plan['config'],inputs=[entry]))[0]
    assert loaded['sample_rate_hz']==row['sample_rate_hz']
    assert all(p['collected_utc_ns']<loaded['start_utc_ns']-505_000_000_000 for p in json.loads(bank.read_text())['provider_sources'])
    result=dict(unit=unit,input=entry,tracks=len(loaded['tracks']),observations=sum(len(t['y']) for t in loaded['tracks']),eligibility_exclusions=loaded['eligibility_exclusions'],mint_analysis_match=True,elapsed_seconds=time.monotonic()-started,recovery=True,observation_sha256=before,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with (folder/'validated.json').open('x') as f:json.dump(result,f,indent=2)
    print(unit,'validated',flush=True)

if __name__=='__main__':main(sys.argv[1])
