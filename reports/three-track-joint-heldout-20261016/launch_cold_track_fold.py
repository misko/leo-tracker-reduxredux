"""Fresh pipeline on a declared training fold, with held probe groups absent."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
from leo.cli.shared_fast_position import load_input,run
from leo.application.scanner_trajectory import project_scanner_candidates

fold=sys.argv[1];assert fold in ['early_to_late','late_to_early']
destination=Path('/tmp/three-track-investigation')/('cold-fold-'+fold+'-v1')
if destination.exists():raise FileExistsError('Attempt namespace exists; inspect its live handle or terminal before relaunch')
payload=Path('/srv/bulk/leo/fast-scan-tracking-inputs/fast-9571943d3dccdf4f327e1346d1bf34b8.json').read_bytes();document=json.loads(payload);source=load_input(document)
winners={}
for p in project_scanner_candidates(source):
    old=winners.get(p.source_group_id)
    if old is None or (-p.margin,p.candidate_rank,p.candidate_id)<(-old.margin,old.candidate_rank,old.candidate_id):winners[p.source_group_id]=p
points=sorted(winners.values(),key=lambda p:(p.support_center_utc_ns,p.source_group_id));origin=source.timing.first_sample_estimate_utc_ns
times=np.array([(p.support_center_utc_ns-origin)/1e9 for p in points]);assert len(points)==4797
held=[];targets=[]
for name,path in [('early_ch2','/tmp/rx1-ch2-50-75'),('ch4','/tmp/rx1-ch4-40-100'),('late_ch2','/tmp/rx1-ch2-170-190')]:
    rows=np.load(path+'/arrays.npz')['rows']
    if name=='early_ch2':rows=rows[np.isin(times[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
    early=times[rows]<=np.median(times[rows]);train=early if fold=='early_to_late' else ~early
    held.extend(rows[~train].tolist());targets.append(dict(track=name,training_rows=rows[train].tolist(),test_rows=rows[~train].tolist()))
keys={(points[i].visit_index,points[i].receiver_id,points[i].probe_index) for i in held};assert len(keys)==len(held)
derived={key:value for key,value in document.items() if key in ['source','clock_anchor','delivery_clocks','last_sample_counter']}
old_probes=derived['source']['probes'];filtered=[p for p in old_probes if (p['visit_index'],p['receiver_id'],p['probe_index']) not in keys]
assert len(old_probes)-len(filtered)==len(held)
derived['source']['probes']=filtered;newpayload=(json.dumps(derived,sort_keys=True,separators=(',',':'))+'\n').encode()
destination.mkdir();input_path=destination/'training-input.json';input_path.write_bytes(newpayload)
manifest=dict(scope='Fresh training-fold discovery, bank selection, calibration and initialization. Declared held probe groups absent. Original public input untouched; isolated existing-data analysis, no production publication.',recording='fast8-auto-20261016-161535-99008d35-1-lower',session_id=source.session_id,fold=fold,parent_input_sha256=hashlib.sha256(payload).hexdigest(),derived_input_sha256=hashlib.sha256(newpayload).hexdigest(),original_observations=len(points),withheld_count=len(held),withheld_original_rows=held,targets=targets,maximum_seconds=480)
(destination/'derivation.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({k:v for k,v in manifest.items() if k not in ['targets','withheld_original_rows']}),flush=True)
result=run(input_path,destination/'output',maximum_seconds=480,tle_root=Path('/tmp/three-track-investigation/space-track-pipeline-rerun/pinned-tle'))
print(json.dumps({key:result.get(key) for key in ['state','reason','elapsed_seconds','position','selection']}),flush=True)
