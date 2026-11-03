"""Freeze the explicitly confirmed fast comparison cohort, preserving DS24 IDs."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030')
WORK=Path('/srv/bulk/leo/research/ds25-fast-causal-variants-20261101')
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,z):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(z,indent=2,allow_nan=False)+'\n')
def main():
    path=Path('/srv/bulk/leo/research/ds25-20261024/sample.json');sample=read(path)
    fast=[r for r in sample['selected'] if r['mode']=='fast'];assert len(fast)==34
    dataset=read(OLD/'datasets/DS24.json');cases={r['case']:r for r in dataset['cases']};rows=[]
    for m in fast:
        c=cases[m['dataset_label']];assert c['recording_id']==m['recording_id'] and c['recording_format']=='short_window_iq_recording'
        folder=OLD/'cases'/c['case'];terminal=folder/'candidate-v2/terminal.json'
        row=dict(case=c['case'],recording_id=c['recording_id'],captured_utc_ns=m['captured_utc_ns'],sample_rate_hz=m['sample_rate_hz'],
                 state='ready' if terminal.exists() else 'unavailable',source_terminal=str(terminal),source_recovery=str(terminal.parent/'recovery'),
                 input=c['input'],source_baseline_receipt=str(folder/'baseline-receipt.json'),reason=None if terminal.exists() else 'No frozen public GLRT input')
        if terminal.exists():
            t=read(terminal);assert t['state']=='complete' and t['input_sha256']==c['input']['sha256']
            row.update(terminal_sha256=digest(terminal),historical_read_audit_verified=bool((t.get('read_audit') or {}).get('verified')))
        rows.append(row)
    write(ROOT/'roster.json',dict(study='DS25 same-interval fast comparison; DS24 members',cases=rows,
        source_sample=str(path),source_sample_sha256=digest(path),no_GPS_inference=True,
        variants=['ALGO05','48h_15s','72h_15s','72h_30s','72h_30s_recency'],arms=['c0','fitted_c'],
        parent_dataset_manifest_sha256=sample['parent_manifest_sha256'],DS25_dataset_unchanged=True))
    print('Frozen',len(rows),'fast comparison scans;',sum(r['state']=='ready' for r in rows),'have ALGO03 results')
if __name__=='__main__':main()
