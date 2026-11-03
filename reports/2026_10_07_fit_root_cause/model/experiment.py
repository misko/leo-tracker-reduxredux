"""Exact likelihood decomposition of saved/local alternatives; no fitting."""
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SID='scan-fw-6bf407cfe8158445'

def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.operations.tle_archive import TleArchiveReader
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import PositionObjective,predict_orbits,ALIAS_HZ
    from leo.contracts.regional_position import RegionalPrior,PositionScore
    from leo.contracts.digests import canonical_digest
    from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
    snapshot=json.loads((ROOT/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(c['regional_document'] for c in snapshot['captures'] if c['session_id']==SID);saved=doc['diagnostics']
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try: source=store.load(SID)
    finally:store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256'];assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    prepared=prepare_position_windows(source);obs=prepared.observations
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));tle=next(s for s in archive.list_snapshots() if s.digest==saved['snapshot_sha256'] and s.collected_utc_ns==saved['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(tle));catalogue=parse_element_sets(payload)
    prior=RegionalPrior(**doc['configuration']['prior']);indices=np.asarray([i for i,n in enumerate(catalogue.names) if n.upper().startswith('STARLINK')])
    bank,receipt=build_regional_bank(catalogue,indices,prepared.start_utc_ns,obs,prior,maximum_seconds=60)
    assert list(receipt.retained_numbers)==saved['bank']['retained_numbers']
    checkpoint=RegionalCheckpointStore(Path('/srv/bulk/leo'),SID,saved['checkpoint_binding']);prefix=canonical_digest(doc['configuration']['run'])
    previous=json.loads((ROOT/'2026_10_07_debug_search_gap/results.json').read_text())
    cases=[('near-original-free','point:-87.5:-87.5','fitted-c','saved-incumbent'),('near-original-zero','point:-87.5:-87.5','zero-c','saved-incumbent'),('near-improved-free','point:-87.5:-87.5','fitted-c','saved-zero'),('far-original-free','point:-37.5:212.5','fitted-c','saved-incumbent')]
    output=dict(session_id=SID,verified_input_sha256=source.input_manifest_sha256,verified_analysis_sha256=source.analysis_manifest_sha256,tle_sha256=tle.digest,windows=len(obs.window_ids),cases={},comparisons={});arrays={}
    for label,basin,arm,start in cases:
        row=next(r for r in previous['rows'] if r['basin']==basin and r['arm']==arm and r['start']==start)
        cal=checkpoint.get(prefix+':'+basin+':calibration')['result'];assoc=checkpoint.get(prefix+':'+basin+':association')['result']
        obj=PositionObjective(obs,bank.select(assoc['selected_indices']),prior,PositionScore(**doc['configuration']['scores']['V16']),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
        v=np.asarray(row['vector']);value,gradient,terms=obj.evaluate(v);assert abs(value-row['objective'])<1e-6
        relative=obj.basis@v[8:];prediction,visible,_,_=predict_orbits(obj.bank,obs,prior,v[:2],v[7]+relative,derivatives=False)
        q=np.where(visible,obj.score.detection_budget/len(obj.bank.numbers),0.);logp0=-obj.score.clutter_rate+np.log1p(-q).sum(axis=1)
        normalization=-logp0+np.log(-np.expm1(logp0))
        # Recover exact per-row mixture likelihood from clutter responsibility.
        logh=np.log(obj.score.clutter_rate/ALIAS_HZ)-np.log(terms.clutter_probability)
        nll=normalization-logh;assert abs(nll.sum()-terms.nll)<1e-6
        mass=terms.responsibilities.sum(axis=1);best=terms.responsibilities.argmax(axis=1);assignment=obj.bank.numbers[best];assignment=np.where(mass>=.5,assignment,0)
        groups={**{f'rx-{r}':obs.receiver==r for r in np.unique(obs.receiver)},**{f'channel-{c}':obs.channel==c for c in np.unique(obs.channel)},'early-half':obs.times_s<=obs.time_center_s,'late-half':obs.times_s>obs.time_center_s}
        penalty_common=.5*(v[7]/obj.score.common_sigma_s)**2;penalty_relative=.5*np.sum((relative/obj.score.relative_sigma_s)**2)
        output['cases'][label]=dict(basin=basin,bank_numbers=obj.bank.numbers.tolist(),bank_count=len(obj.bank.numbers),objective=value,selection_score=row['selection_score'],mixture_nll=float((-logh).sum()),normalization_nll=float(normalization.sum()),data_nll=terms.nll,common_timing_penalty=float(penalty_common),relative_timing_penalty=float(penalty_relative),calibration_penalty=row['selection_score']-value,signal_mass=float(mass.sum()),hard_signal_rows=int((mass>=.5).sum()),receiver_offset_and_slope=v[2:6].tolist(),c_hz_per_ghz=float(v[6]),common_timing_s=float(v[7]),relative_timing_s=relative.tolist(),baseline_hz=dict(min=float(obj.baseline.min()),max=float(obj.baseline.max()),mean=float(obj.baseline.mean())),blocks={k:dict(windows=int(m.sum()),nll=float(nll[m].sum()),signal_mass=float(mass[m].sum()),hard_signal_rows=int((mass[m]>=.5).sum())) for k,m in groups.items()},satellites=[dict(number=int(n),signal_mass=float(terms.responsibilities[:,j].sum()),shift_s=float(v[7]+relative[j]),mean_residual_hz=float(np.sum(terms.responsibilities[:,j]*terms.residual_hz[:,j])/max(terms.responsibilities[:,j].sum(),1e-30))) for j,n in enumerate(obj.bank.numbers)])
        arrays[label]=(nll,mass,assignment)
    for target in ('near-original-zero','near-improved-free'):
        bad=arrays['near-original-free'];good=arrays[target];changed=bad[2]!=good[2]
        output['comparisons'][target]=dict(nll_improvement=float((bad[0]-good[0]).sum()),assignment_changes=int(changed.sum()),lost_signal_bad=int(((bad[2]==0)&(good[2]!=0)).sum()),gained_signal_bad=int(((bad[2]!=0)&(good[2]==0)).sum()),changed_satellite=int(((bad[2]!=0)&(good[2]!=0)&changed).sum()),blocks={k:dict(nll_improvement=float((bad[0][m]-good[0][m]).sum()),assignment_changes=int(changed[m].sum()),signal_mass_improvement=float((good[1][m]-bad[1][m]).sum())) for k,m in groups.items()},largest_row_improvements=[dict(window_id=obs.window_ids[i],time_s=float(obs.times_s[i]),rx=int(obs.receiver[i]),channel=int(obs.channel[i]),nll_improvement=float(bad[0][i]-good[0][i]),bad_sat=int(bad[2][i]),good_sat=int(good[2][i])) for i in np.argsort(bad[0]-good[0])[-30:][::-1]])
    (HERE/'results.json').write_text(json.dumps(output,indent=2));print(json.dumps(output['comparisons'],indent=2),flush=True)

if __name__=='__main__':main()
