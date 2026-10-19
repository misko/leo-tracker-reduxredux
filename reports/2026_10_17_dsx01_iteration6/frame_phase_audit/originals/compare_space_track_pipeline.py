import json,hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.cli.shared_fast_position import load_input
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.application.shared_orbit_replay import selected_model
from leo.contracts.regional_position import PositionObservations,RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import circular,zero_sum_basis
from leo.analysis.hard60_score import predict_orbits
root=Path('/tmp/three-track-investigation/space-track-pipeline-rerun');output=root/'output';new=json.loads((output/'terminal.json').read_text());assert new['state']=='complete',new
store=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2');_,doc,old,oldstages=store.plot_evidence('dd9c84a33648a347de303cb8345336df');source=load_input(doc);origin=source.timing.first_sample_estimate_utc_ns;winners={}
for p in project_scanner_candidates(source):
 prev=winners.get(p.source_group_id)
 if prev is None or (-p.margin,p.candidate_rank,p.candidate_id)<(-prev.margin,prev.candidate_rank,prev.candidate_id):winners[p.source_group_id]=p
points=sorted(winners.values(),key=lambda p:(p.support_center_utc_ns,p.source_group_id));obs=PositionObservations(tuple(p.source_group_id for p in points),np.array([(p.support_center_utc_ns-origin)/1e9 for p in points]),np.array([p.measured_cfo_hz for p in points]),np.array([p.actual_rf_hz for p in points]),np.array([p.receiver_id for p in points]),np.array([p.channel for p in points]),np.array([p.margin for p in points]))
archive=TleArchiveReader(Path('/var/lib/leo/tle'));snapshots=archive.list_snapshots();result={};arrays={}
for label,terminal in [('original',old),('space_track',new)]:
 stages=oldstages if label=='original' else {}
 if label!='original':
  for binding in terminal['stage_receipts']:
   path=Path(binding['path']);data=path.read_bytes();assert 'sha256:'+hashlib.sha256(data).hexdigest()==binding['sha256'];stages[path.stem]=json.loads(data)
 assert terminal['input_sha256']==old['input_sha256']
 snap=next(s for s in snapshots if s.digest==terminal['provenance']['tle_sha256']);cat=parse_element_sets(archive.read(snap));lookup={int(n):i for i,n in enumerate(cat.satellite_numbers)};nums=terminal['candidate_numbers'];prior=RegionalPrior(**terminal['provenance']['prior']);bank,_=build_regional_bank(cat,[lookup[n] for n in nums],origin,obs,prior);look={int(n):i for i,n in enumerate(bank.numbers)};bank=bank.select([look[n] for n in nums]);model,fit,audit=selected_model({'all':SimpleNamespace(observations=obs)},bank,prior,np.array(terminal['provenance']['clock_nodes_s']),terminal,stages)
 v=np.array(fit['vector']);n=np.array(fit['nuisance']);terms=model.evaluate_joint(v,n)[3];best=terms.responsibilities.argmax(axis=1);associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability;correction=model.original.correction(v,n[:model.clock_count]);shifts=v[7]+zero_sum_basis(len(nums))@v[8:];pred=predict_orbits(bank,obs,prior,v[:2],shifts,derivatives=False)[0];r=circular(obs.measured_hz[:,None]-correction[:,None]-pred);matched_r=r[np.arange(len(best)),best][associated]
 summary=dict(provider=snap.provider,position=terminal['position'],satellites=len(nums),observations=len(best),associated=int(associated.sum()),associated_fraction=float(associated.mean()),associated_rms_hz=float(np.sqrt(np.mean(matched_r**2))),selection=terminal['selection'],elapsed_seconds=terminal['elapsed_seconds'],tracks=[])
 for track,path in [('CH2 170–190 s','/tmp/rx1-ch2-170-190'),('CH2 50–75 s','/tmp/rx1-ch2-50-75'),('CH4 40–100 s','/tmp/rx1-ch4-40-100')]:
  a=np.load(path+'/arrays.npz');rows=a['rows'];assert np.allclose(obs.times_s[rows],a['times'])
  if '50–75' in track:rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
  assigns={str(num):int(np.sum(associated[rows]&(best[rows]==k))) for k,num in enumerate(nums)};assigns={k:v for k,v in assigns.items() if v};raw=np.sqrt(np.mean(r[rows]**2,axis=0));j=int(np.argmin(raw));summary['tracks'].append(dict(track=track,count=len(rows),associated=int(associated[rows].sum()),assignments=assigns,best_raw_satellite=nums[j],best_raw_rms_hz=float(raw[j]),best_raw_offset_hz=float(np.mean(r[rows,j])),best_raw_offset_removed_rms_hz=float(np.std(r[rows,j]))))
 result[label]=summary
 arrays[label+'_nearest_residual']=np.min(abs(r),axis=1);arrays[label+'_associated']=associated
 arrays[label+'_assigned_residual']=np.where(associated,abs(r[np.arange(len(best)),best]),np.inf)
(root/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');np.savez(root/'comparison_arrays.npz',**arrays);print(json.dumps(result,indent=2))
