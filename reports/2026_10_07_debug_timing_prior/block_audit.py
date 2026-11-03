"""Postselection time-block repricing; blocks participated in fitting."""
from experiment import *
from leo.analysis.regional_position_score import predict_orbits,singleton_likelihood

def main():
    result=json.loads((HERE/'results.json').read_text())
    frozen=json.loads((HERE.parent/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(x for x in frozen['captures'] if x['session_id']==SID)['regional_document']
    root=Path('/srv/bulk/leo');store=ScannerTrackingInputStore(root)
    try:source=store.load(SID)
    finally:store.close()
    prepared=prepare_position_windows(source);obs=prepared.observations;prior=RegionalPrior()
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=next(x for x in archive.list_snapshots() if x.digest==doc['diagnostics']['snapshot_sha256'] and x.collected_utc_ns==doc['diagnostics']['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    bank,_=build_regional_bank(cat,np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]),prepared.start_utc_ns,obs,prior,maximum_seconds=100)
    ck=RegionalCheckpointStore(root,SID,doc['diagnostics']['checkpoint_binding']);prefix=canonical_digest(doc['configuration']['run'])+':'
    out=[]
    for basin in ('point:-56.25:-68.75','point:-93.75:-81.25'):
        cal=ck.get(prefix+basin+':calibration')['result'];assoc=ck.get(prefix+basin+':association')['result'];subset=bank.select(assoc['selected_indices'])
        saved=min((r for r in doc['diagnostics']['final_starts'] if r['basin']==basin and r['method']=='V16' and r['arm']=='fitted-c'),key=lambda r:r['fit']['objective'])
        trials=[dict(label='saved',sigma=.15,arm='fitted-c',fit=saved['fit'])]
        for sigma in (.15,.5,1.):
            for arm in ('zero-c','fitted-c'):
                trials.append(dict(min((r for r in result['fits'] if r['basin']==basin and r['sigma']==sigma and r['arm']==arm),key=lambda r:r['total']),label='optimized'))
        for row in trials:
            score=replace(POSITION_SCORES['V16'],relative_sigma_s=row['sigma']);o=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
            v=np.asarray(row['fit']['vector']);relative=o.basis@v[8:];prediction,visible,_,_=predict_orbits(subset,obs,prior,v[:2],relative+v[7])
            prediction+=(o.design@v[2:7]+o.baseline)[:,None]
            terms=singleton_likelihood(obs.measured_hz,prediction,visible,score)
            blocks=[];ids=np.floor((obs.times_s-obs.times_s.min())/60).astype(int)
            for b in np.unique(ids):
                mask=ids==b;t=singleton_likelihood(obs.measured_hz[mask],prediction[mask],visible[mask],score)
                blocks.append(dict(block=int(b),count=int(mask.sum()),data_nll=t.nll,signal_fraction=float(t.responsibilities.sum()/mask.sum())))
            assert abs(sum(b['data_nll'] for b in blocks)-terms.nll)<1e-7
            out.append(dict(basin=basin,label=row['label'],sigma=row['sigma'],arm=row['arm'],data_nll=terms.nll,blocks=blocks,numbers=subset.numbers,relative_s=relative,common_s=v[7],satellite_signal_mass=terms.responsibilities.sum(axis=0)))
    (HERE/'block_audit.json').write_text(json.dumps(out,default=serialize,indent=2))

if __name__=='__main__':main()
