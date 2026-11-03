"""Finite differences and feasible nuisance descent; no optimization fits."""
import json
from pathlib import Path
from dataclasses import replace
import numpy as np
from leo.analysis.regional_position_score import PositionObjective
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import RegionalPrior,PositionScore
from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from experiment import HERE,REPORTS,controls

def main():
    r=json.loads((HERE/'results.json').read_text());snap=json.loads((REPORTS/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(c['regional_document'] for c in snap['captures'] if c['session_id']==r['session_id'])
    source_store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try: source=source_store.load(r['session_id'])
    finally:source_store.close()
    prep=prepare_position_windows(source);obs=prep.observations
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));ref=next(x for x in archive.list_snapshots() if x.digest==doc['diagnostics']['snapshot_sha256'] and x.collected_utc_ns==doc['diagnostics']['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(ref));cat=parse_element_sets(payload)
    ix=np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]);prior=RegionalPrior(**doc['configuration']['prior'])
    bank,_=build_regional_bank(cat,ix,prep.start_utc_ns,obs,prior,maximum_seconds=60)
    checkpoints=RegionalCheckpointStore(Path('/srv/bulk/leo'),r['session_id'],doc['diagnostics']['checkpoint_binding']);prefix=canonical_digest(doc['configuration']['run'])
    target=next(q['start'] for q in r['runs'] if q['start']['origin']=='inward-1m-probe-start' and q['start']['arm']=='fitted-c' and q['start']['domain']=='original')
    basin=target['basin'];cal=checkpoints.get(prefix+':'+basin+':calibration')['result'];assoc=checkpoints.get(prefix+':'+basin+':association')['result']
    objective=PositionObjective(obs,bank.select(assoc['selected_indices']),prior,replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
    vector=np.asarray(target['vector']);value,g,_=objective.evaluate(vector);j=target['largest_scaled_gradient_index'];h=1e-5
    plus=vector.copy();minus=vector.copy();plus[j]+=h;minus[j]-=h
    numeric=(objective.evaluate(plus)[0]-objective.evaluate(minus)[0])/(2*h)
    trial=vector.copy();direction=g[8:]/np.linalg.norm(g[8:]);trial[8:]-=.0001*direction
    after,gg,_=objective.evaluate(trial);shifts=trial[7]+objective.basis@trial[8:]
    minimum=max(-20.,objective.bank.nodes_s[0]-obs.times_s.min());maximum=min(20.,objective.bank.nodes_s[-1]-obs.times_s.max())
    audit=controls.audit(trial,gg,objective.basis,'fitted-c',250,np.asarray(r['basins'][basin]['center']),r['basins'][basin]['radius_km'],minimum,maximum)
    result={'basin':basin,'parameter_index':j,'analytic_gradient':float(g[j]),'finite_difference_gradient':float(numeric),'starting_objective':float(value),'nuisance_descent_objective':float(after),'delta_objective':float(after-value),'position_unchanged':bool(np.array_equal(trial[:2],vector[:2])),'timing_shift_min_s':float(shifts.min()),'timing_shift_max_s':float(shifts.max()),'global_disk_slack_km2':float(250**2-np.sum(trial[:2]**2)),'local_disk_slack_km2':audit['minimum_constraint_slack'],'trial_feasible':audit['feasible']}
    assert abs(numeric-g[j])<.001 and audit['feasible'] and after<value
    (HERE/'gradient_audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
