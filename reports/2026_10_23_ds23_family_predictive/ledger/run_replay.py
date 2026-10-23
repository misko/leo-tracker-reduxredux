from pathlib import Path
import hashlib,json,time
from coverage_ledger import enforce_rejected_ids
OUT=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/algo04-native-qualification-20261023')
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    inputs=[OLD/'raw'/case/'result.json' for case in ['DS23-0232','DS23-0365']]
    protocol=dict(cases=['DS23-0232','DS23-0365'],arms=['c0','fitted_c'],
        policy='explicit rejected physical IDs; refuse parent overlap; remove whole intersecting association records; recompute coverage IDs/counts/percent/track count',
        fits_unchanged=True,global_helpers_unchanged=True,no_GPS=True,no_new_RF=True,no_production_adoption=True,
        source_hashes={str(p):sha(p) for p in [OUT/'coverage_ledger.py',Path(__file__)]},input_hashes={str(p):sha(p) for p in inputs})
    if (OUT/'protocol.json').exists():assert json.loads((OUT/'protocol.json').read_text())==protocol
    else:write(OUT/'protocol.json',protocol)
    start=time.monotonic();rows=[]
    for path in inputs:
        saved=json.loads(path.read_text());rejected={o for e in saved['excluded_entries'] for o in e['observation_ids']}
        for arm in protocol['arms']:
            cov=saved['policy_final']['coverage'][arm];protected=saved['graph_parent']['coverage'][arm]['accepted_observation_ids']
            strict=enforce_rejected_ids(cov,rejected,protected)
            assert strict==enforce_rejected_ids(strict,rejected,protected)
            assert not set(strict['accepted_observation_ids'])&rejected
            removed=set(cov['accepted_observation_ids'])-set(strict['accepted_observation_ids'])
            row=dict(case=saved['case'],arm=arm,before=cov['associated'],after=strict['associated'],removed_readmitted_ids=sorted(removed),
                collateral_removed_ids=sorted(removed-rejected),tracks_before=cov['associated_tracks'],tracks_after=strict['associated_tracks'],
                original_parent_preserved=True,position_fit_unchanged=True,coverage=strict)
            rows.append(row)
    assert [len(r['removed_readmitted_ids']) for r in rows]==[0,9,0,0]
    write(OUT/'results.json',dict(status='complete',seconds=time.monotonic()-start,rows=rows))
    print([(r['case'],r['arm'],r['before'],r['after']) for r in rows])
if __name__=='__main__':main()
