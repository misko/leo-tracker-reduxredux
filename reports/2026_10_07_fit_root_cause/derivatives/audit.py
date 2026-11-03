"""Read-only numerical audit of frozen original objectives; no optimizer runs."""
import json,time
from pathlib import Path
from dataclasses import asdict
import numpy as np
from leo.application.regional_position_inputs import prepare_position_windows
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior,POSITION_SCORES
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import PositionObjective,predict_orbits,zero_sum_basis

HERE=Path(__file__).resolve().parent;SID='scan-fw-6bf407cfe8158445'
def ser(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    raise TypeError(type(x).__name__)

def geometry(o,v):
    shifts=v[7]+o.basis@v[8:]
    q=(o.observations.times_s[:,None]+shifts-o.bank.nodes_s[0])/.25
    p,visible,_,_=predict_orbits(o.bank,o.observations,o.prior,v[:2],shifts,derivatives=False)
    return np.floor(q),visible,float(np.min(np.minimum(q%1,1-q%1))*.25)

def main():
    begun=time.monotonic();deadline=begun+115
    frozen=json.loads((HERE.parents[1]/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(x for x in frozen['captures'] if x['session_id']==SID)['regional_document']
    root=Path('/srv/bulk/leo');store=ScannerTrackingInputStore(root)
    try:source=store.load(SID)
    finally:store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256'];assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    prepared=prepare_position_windows(source);obs=prepared.observations;prior=RegionalPrior()
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snap=next(x for x in archive.list_snapshots() if x.digest==doc['diagnostics']['snapshot_sha256'] and x.collected_utc_ns==doc['diagnostics']['snapshot_collected_utc_ns'])
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    bank,receipt=build_regional_bank(cat,np.array([i for i,n in enumerate(cat.names) if n.upper().startswith('STARLINK')]),prepared.start_utc_ns,obs,prior,maximum_seconds=30)
    ck=RegionalCheckpointStore(root,SID,doc['diagnostics']['checkpoint_binding']);prefix=canonical_digest(doc['configuration']['run'])+':'
    out=dict(session_id=SID,input_hash=source.input_manifest_sha256,analysis_hash=source.analysis_manifest_sha256,tle_digest=snap.digest,bank=asdict(receipt),points=[],paths=[])
    rng=np.random.default_rng(731)
    for basin in ('point:-87.5:-87.5','point:-37.5:212.5'):
        cal=ck.get(prefix+basin+':calibration')['result'];assoc=ck.get(prefix+basin+':association')['result'];subset=bank.select(assoc['selected_indices'])
        o=PositionObjective(obs,subset,prior,POSITION_SCORES['V16'],receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
        scales=np.r_[1,1,200,2,200,2,200,np.ones(o.size-7)]
        saved=[r for r in doc['diagnostics']['final_starts'] if r['basin']==basin and r['method']=='V16']
        points=[dict(label='saved:'+r['arm']+':'+r['start'],vector=np.asarray(r['fit']['vector']),saved=r['fit']) for r in saved]
        for arm in ('fitted-c','zero-c'):
            for mode in ('associated','zero-timing'):
                v=np.asarray(assoc['initial_vector']).copy()
                if arm=='zero-c':v[6]=0
                if mode=='zero-timing':v[7:]=0
                points.append(dict(label='original-start:'+arm+':'+mode,vector=v,saved=None))
        for p in points:
            if time.monotonic()>deadline:raise TimeoutError('115s audit budget')
            v=p['vector'];value,g,terms=o.evaluate(v);cells,visible,knot=geometry(o,v)
            dirs=[np.eye(o.size)[i] for i in (0,1,6,7,8)]
            dirs += [d/np.linalg.norm(d) for d in rng.normal(size=(2,o.size))]
            rows=[]
            for j,d in enumerate(dirs):
                direction=d*scales;analytic=float(g@direction)
                for h in (1e-3,1e-4,1e-5):
                    plus=v+h*direction;minus=v-h*direction
                    fp=o.evaluate(plus)[0];fm=o.evaluate(minus)[0]
                    cp,vp,_=geometry(o,plus);cm,vm,_=geometry(o,minus)
                    fd=(fp-fm)/(2*h)
                    rows.append(dict(direction=j,h=h,analytic=analytic,finite_difference=fd,absolute_error=abs(fd-analytic),normalized_error=abs(fd-analytic)/(1+abs(analytic)),knot_crossings=int(np.sum(cp!=cm)),visibility_crossings=int(np.sum(vp!=vm))))
            free_coordinates=np.array([i for i in range(o.size) if i!=6 or 'zero-c' not in p['label']])
            item=dict(basin=basin,label=p['label'],objective=value,archived_delta=None if p['saved'] is None else value-p['saved']['objective'],scaled_gradient_max=float(np.max(abs(g*scales))),free_scaled_gradient_max=float(np.max(abs((g*scales)[free_coordinates]))),max_absolute_timing_shift_s=float(np.max(abs(v[7]+o.basis@v[8:]))),local_disk_margin_km=float(12.5-np.linalg.norm(v[:2]-np.asarray(assoc['initial_vector'][:2]))),knot_distance_s=knot,checks=rows,vector=v,signal_mass=float(terms.responsibilities.sum()))
            # Near associated solutions are interior: curvature in all free coordinates.
            if basin=='point:-87.5:-87.5' and p['label'] in ('saved:fitted-c:associated','saved:zero-c:associated'):
                for h in (1e-4,1e-5):
                    columns=[]
                    for i in range(o.size):
                        d=np.eye(o.size)[i]*scales
                        gp=o.evaluate(v+h*d)[1]*scales;gm=o.evaluate(v-h*d)[1]*scales
                        columns.append((gp-gm)/(2*h))
                    matrix=np.column_stack(columns);symmetric=(matrix+matrix.T)/2
                    free=np.arange(o.size) if 'fitted-c' in p['label'] else np.array([i for i in range(o.size) if i!=6])
                    eigen=np.linalg.eigvalsh(symmetric[np.ix_(free,free)])
                    item.setdefault('curvature',[]).append(dict(h=h,eigenvalues=eigen,max_asymmetry=float(np.max(abs(matrix-matrix.T)))))
            out['points'].append(item)
        if basin=='point:-87.5:-87.5':
            a=next(p['vector'] for p in points if p['label']=='saved:fitted-c:associated');b=next(p['vector'] for p in points if p['label']=='saved:zero-c:associated')
            t0=o.evaluate(a)[2];t1=o.evaluate(b)[2]
            for fraction in np.linspace(0,1,21):
                v=(1-fraction)*a+fraction*b;value,_,t=o.evaluate(v)
                out['paths'].append(dict(fraction=fraction,objective=value,signal_mass=float(t.responsibilities.sum()),top_satellite_changes_from_bad=int(np.sum(np.argmax(t.responsibilities,axis=1)!=np.argmax(t0.responsibilities,axis=1))),responsibility_l1_from_bad=float(np.sum(abs(t.responsibilities-t0.responsibilities)))))
            out['near_endpoint_support']=dict(numbers=subset.numbers,bad= t0.responsibilities.sum(axis=0),better=t1.responsibilities.sum(axis=0),delta_vector=b-a)
            ra=o.basis@a[8:];rb=o.basis@b[8:];delta=rb-ra
            branches=[dict(number=n,bad_relative_s=ra[i],better_relative_s=rb[i],delta_relative_s=delta[i],bad_mass=t0.responsibilities[:,i].sum(),better_mass=t1.responsibilities[:,i].sum()) for i,n in enumerate(subset.numbers)]
            out['timing_branch']=sorted(branches,key=lambda x:abs(x['delta_relative_s']),reverse=True)
            out['near_branch_summary']=dict(bad_relative_rms_s=float(np.sqrt(np.mean(ra**2))),better_relative_rms_s=float(np.sqrt(np.mean(rb**2))),bad_absolute_shift_max_s=float(max(abs(ra+a[7]))),better_absolute_shift_max_s=float(max(abs(rb+b[7]))),delta_relative_norm_s=float(np.linalg.norm(delta)),delta_vector=b-a)
    out['elapsed_s']=time.monotonic()-begun
    (HERE/'results.json').write_text(json.dumps(out,default=ser,indent=2));print('Audit completed',out['elapsed_s'],flush=True)

if __name__=='__main__':main()
