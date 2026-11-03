"""Isolated cold-pipeline control with the original target probe groups removed."""
exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from leo.cli.shared_fast_position import run
import hashlib

destination=Path('/tmp/three-track-investigation/cold-target-excluded-v1')
if destination.exists():raise FileExistsError('Cold attempt namespace already exists; inspect existing process/terminal before any new launch')
destination.mkdir()
held=json.loads((root/'excluded_calibration_fitted-c_from_zero.json').read_text())['held_rows']
keys={(points[i].visit_index,points[i].receiver_id,points[i].probe_index) for i in held}
assert len(keys)==129
payload=Path('/srv/bulk/leo/fast-scan-tracking-inputs/fast-9571943d3dccdf4f327e1346d1bf34b8.json').read_bytes()
document=json.loads(payload)
derived={key:value for key,value in document.items() if key in ['source','clock_anchor','delivery_clocks','last_sample_counter']}
assert 'source' in derived
original_probes=derived['source']['probes']
filtered=[p for p in original_probes if (p['visit_index'],p['receiver_id'],p['probe_index']) not in keys]
assert len(original_probes)-len(filtered)==129
derived['source']['probes']=filtered
newpayload=(json.dumps(derived,sort_keys=True,separators=(',',':'))+'\n').encode()
input_path=destination/'target-excluded-input.json';input_path.write_bytes(newpayload)
manifest=dict(scope='Derived research input; original public export untouched. Remove whole target probe groups before cold discovery, candidate-bank selection, calibration and initialization. No production store publication or RF collection.',scan=source.session_id,parent_input_sha256=hashlib.sha256(payload).hexdigest(),derived_input_sha256=hashlib.sha256(newpayload).hexdigest(),original_probes=len(original_probes),retained_probes=len(filtered),excluded_probe_keys=sorted([list(k) for k in keys]),excluded_original_rows=held,maximum_seconds=480,pinned_tle_root=str(root/'pinned-tle'))
(destination/'derivation.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({key:value for key,value in manifest.items() if not key.startswith('excluded')}),flush=True)
result=run(input_path,destination/'output',maximum_seconds=480,tle_root=root/'pinned-tle')
print(json.dumps({key:result.get(key) for key in ['state','reason','elapsed_seconds','position','selection']}),flush=True)
