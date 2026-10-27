"""Independent metadata/scorer-domain audit; never open IQ payloads."""
import ast
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
INVENTORY=HERE.parent/'ds23_inventory'
SCORER=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/timing/timing_search.py')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    paths=read(INVENTORY/'original_path_inventory.json');rates=read(INVENTORY/'sample_rate_inventory.json')
    assert sha(paths['manifest_path'])==paths['manifest_sha256']
    assert sha(INVENTORY/'original_path_inventory.json')==rates['source_inventory_sha256']
    assert len(paths['rows'])==len(rates['rows'])==207
    binding={r['dataset_label']:r for r in paths['rows']};segments=0;bad=[]
    for row in rates['rows']:
        original=binding[row['case']];expected={s['path']:s['manifest_sha256'] for s in original['raw_segments']}
        assert row['rates_hz']==[2500000]
        for segment in row['segments']:
            assert 'sha256:'+sha(segment['path'])==segment['sha256']==expected[segment['path']]
            meta=read(segment['path']);assert meta['sample_rate_hz']==segment['sample_rate_hz']==2500000
            segments+=1
        if not row['all_original_paths_present']:bad.append(row['case'])
    assert sorted(bad)==['DS23-0012','DS23-0184','DS23-0286']
    frozen=read(SCORER.parent/'protocol.json');assert sha(SCORER)==frozen['files'][str(SCORER)]
    tree=ast.parse(SCORER.read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='scores')
    guard=next(n for n in function.body if isinstance(n,ast.If))
    assert isinstance(guard.test,ast.Compare) and isinstance(guard.test.left,ast.Name) and guard.test.left.id=='rate'
    assert isinstance(guard.test.ops[0],ast.NotEq) and guard.test.comparators[0].value==10000000
    assert isinstance(guard.body[0],ast.Raise)
    result=dict(all_passed=True,fast_recordings=207,adaptive_recordings=paths['format_counts']['starlink_adaptive_hop_iq'],
        all_fast_native_rates_hz=[2500000],segment_manifests_independently_verified=segments,
        original_paths_complete=204,missing_analysis_inputs=sorted(bad),
        scorer_required_rate_hz=10000000,scorer_guard_line=guard.lineno,scorer_sha256=sha(SCORER),
        compatible_fast_recordings_for_unchanged_candidate=0,
        IQ_payload_reads=0,new_fit_calls=0,geographic_errors_opened=False,
        DS23_accuracy_transfer_claim=False,physical_sample_rate_error_cause_claim=False,
        source_inventory_sha256=sha(INVENTORY/'original_path_inventory.json'),rate_inventory_sha256=sha(INVENTORY/'sample_rate_inventory.json'))
    with (HERE/'ds23_compatibility_audit.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result)


if __name__=='__main__':main()
