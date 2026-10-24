"""Verify channel isolation, unchanged physical points, and causal paired fits."""
import hashlib,json
from pathlib import Path
import base_audit

ROOT=Path(__file__).resolve().parent
PARENT=Path('/srv/bulk/leo/research/ds25-20261024')


def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert read(ROOT/'execution.json')['all_terminal']
    protocol=read(ROOT/'protocol.json')
    for path,h in protocol['sources_sha256'].items():
        assert sha(Path(path))==h, path
    groups=('ch1_4','ch5_8')
    for group in groups:
        assert read(ROOT/group/'channels.json')['channels']==([1,2,3,4] if group=='ch1_4' else [5,6,7,8])
        base_audit.OUT=ROOT/group;base_audit.main()
    rows=[]
    for m in read(ROOT/'ch1_4/sample.json')['selected']:
        case=m['dataset_label'];original=read(PARENT/case/'input_receipt.json')
        row=dict(case=case,halves={},source_status=original['status'])
        if original['status']=='exported':
            all_rows=read(PARENT/case/'observations.json')
            original_by_id={r['observation_id']:r for r in all_rows}
            ids={}
            for group in groups:
                root=ROOT/group;selected=read(root/case/'observations.json')
                receipt=read(root/case/'input_receipt.json')
                assert receipt['tracking_sha256']==original['tracking_sha256']
                channels=set(read(root/'channels.json')['channels'])
                expected={i:r for i,r in original_by_id.items() if r['channel'] in channels}
                actual={r['observation_id']:r for r in selected}
                assert len(actual)==len(selected) and actual==expected,(case,group)
                for t in read(root/case/'tracks.json'):
                    assert t['channel'] in channels
                    assert set(t['observation_ids'])<=set(expected)
                prep=read(root/case/'prepared.json')
                if prep['status']=='prepared':
                    assert prep['metadata']['channel_subset']==sorted(channels)
                    assert prep['graph_config_sha256']==read(PARENT/case/'prepared.json')['graph_config_sha256']
                    noise=read(root/case/'radio_noise.json')
                    assert set(noise['per_observation_noise_sigma_hz'])==set(expected)
                    assert noise['no_GPS_TLE_or_satellite_residuals_used'] is True
                    for name in ('anchor_utc_ns','causal_cutoff_utc_ns'):
                        assert prep['metadata'][name]==read(PARENT/case/'prepared.json')['metadata'][name]
                ids[group]=set(actual)
                row['halves'][group]=dict(points=len(selected),tracks=len(read(root/case/'tracks.json')))
            assert not ids['ch1_4']&ids['ch5_8']
            assert ids['ch1_4']|ids['ch5_8']==set(original_by_id)
            row['original_points']=len(all_rows)
            row['exact_partition_verified']=True
        else:
            assert all(read(ROOT/g/case/'input_receipt.json')['status']=='input_unavailable' for g in groups)
        rows.append(row)
    result=dict(passed=True,cases=len(rows),exact_partitions=sum(r.get('exact_partition_verified',False) for r in rows),
                source_code_unchanged=True,all_channel_result_files_sha256={
                    str(p):sha(p) for m in read(ROOT/'ch1_4/sample.json')['selected']
                    for p in [PARENT/m['dataset_label']/'algo02_result.json',
                              PARENT/'family_cavity/position'/(m['dataset_label']+'.json')]
                    if p.exists()},rows=rows)
    (ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','all_channel_result_files_sha256')}))


if __name__=='__main__':main()
