import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    source=HERE.parent/'2026_09_28_full_manifest_inputs'
    full=json.loads((source/'plan.json').read_text())
    old_path=HERE.parent/'2026_09_29_scan_budget/manifest.json'
    old=json.loads(old_path.read_text())
    assert full['config']==old['config']
    hashes={};sets=[]
    for ds in ['DS7','DS8','DS9']:
        rows=sorted([r for r in full['captures'] if r['dataset_id']==ds],key=lambda r:(r['capture_start_utc_ns'],r['session_id']))
        chosen=[rows[i*(len(rows)-1)//23] for i in range(24)]
        assert len({r['session_id'] for r in chosen})==24
        prior=next(u for u in old['sets'] if u['unit']==f'{ds}_n24_0')
        old_ids={r['session_id'] for r in prior['scans']}
        selected=[]
        for row in chosen:
            p=source/'validated'/f"{row['unit_id']}.json"
            recovery=False
            if not p.exists():
                p=source/'recovery-validated'/f"{row['unit_id']}.json";recovery=True
            raw=p.read_bytes();hashes[str(p)]=hashlib.sha256(raw).hexdigest()
            result=json.loads(raw);assert result['request']['config']==full['config']
            entry=result['request']['inputs'][0]
            assert entry['session_id']==row['session_id'] and entry['manifest_sha256']==row['manifest_sha256']
            for a in entry['artifacts']:
                digest=hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()
                assert 'sha256:'+digest==a['sha256'];hashes[a['path']]=digest
            selected.append(dict(unit=row['unit_id'],ordinal=row['ordinal'],session_id=row['session_id'],recovery_input=recovery,input=entry))
        sets.append(dict(dataset=ds,scans=selected,overlap_with_old_n24=len(old_ids & {r['session_id'] for r in chosen})))
    for p in [source/'plan.json',old_path,HERE/'prepare.py',HERE/'run.py',HERE/'PROTOCOL.md',HERE.parent/'2026_09_29_scan_budget/run.py',HERE.parent/'2026_09_29_receiver_holdout/run.py',HERE.parent/'2026_09_29_unassociated_trend/trend_mixture.py',ROOT/'tools/ds7_fast_baseline_adapter.py',ROOT/'tools/ds7_baseline_adapter.py']:
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE/'plan.json').open('x') as out:json.dump(dict(config=full['config'],sets=sets,hashes=hashes),out,indent=2)
    print([(s['dataset'],s['overlap_with_old_n24']) for s in sets])


if __name__=='__main__':main()
