"""Compare causal catalogue epochs and exact predicted CFO at frozen locations."""
import json
import hashlib
import sys
from pathlib import Path
import numpy as np
from catalogue import HERE,REPORTS,catalogues,TleArchiveReader
from run_baseline import site,propagate_candidate_states,REFERENCE_RF_HZ,LIGHT_KM_S


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol=json.loads((REPORTS/'2026_09_27_ds6_full_cfo/protocol.json').read_text())
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));cache={};rows=[];inputs={}
    for session in protocol['sessions']:
        data_path=REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json'
        base_path=REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json'
        assignment_path=REPORTS/'2026_09_27_ds6_clock_curvature_converged'/f'{session}.json'
        for p in [data_path,base_path,assignment_path]:inputs[str(p.relative_to(REPORTS))]=digest(p)
        data=json.loads(data_path.read_text());base=json.loads(base_path.read_text())
        assignments={t['track_id']:t['candidate_index'] for t in json.loads(assignment_path.read_text())['assignments']}
        old,new,provenance=catalogues(archive,data['start_utc_ns'],data['snapshot_digest'],cache)
        old_epochs=old.element_epoch_utc_ns();new_epochs=new.element_epoch_utc_ns()
        rec,_=site(base['best']['latitude'],base['best']['longitude']);tau=base['best']['x'][2];tracks=[]
        for t in data['tracks']:
            if t['track_id'] not in assignments:continue
            idx=assignments[t['track_id']];mask=np.array(t['training_mask'],dtype=bool);times=np.array(t['times_s'])
            changed=idx in provenance['changed_rows'];rms=maximum=displacement=0.
            if changed:
                predictions=[];positions=[]
                for cat in [old,new]:
                    p,v,ids=propagate_candidate_states(cat,[idx],data['start_utc_ns'],times,np.array([tau]))
                    assert ids.tolist()==[idx]
                    unit=p[0,0]-rec;unit/=np.linalg.norm(unit,axis=-1)[:,None]
                    predictions.append(-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*v[0,0],axis=-1));positions.append(p[0,0])
                difference=predictions[1]-predictions[0];difference-=difference[mask].mean()
                rms=float(np.sqrt(np.mean(difference**2)));maximum=float(np.max(np.abs(difference)))
                displacement=float(np.max(np.linalg.norm(positions[1]-positions[0],axis=-1)))*1000
            tracks.append(dict(track_id=t['track_id'],candidate_index=idx,satellite_number=old.satellite_numbers[idx],changed=changed,
                old_age_h=(data['start_utc_ns']-old_epochs[idx])/3.6e12,new_age_h=(data['start_utc_ns']-new_epochs[idx])/3.6e12,
                centered_cfo_difference_rms_hz=rms,centered_cfo_difference_max_hz=maximum,maximum_state_displacement_m=displacement))
        row=dict(session_id=session,baseline_digest=provenance['baseline_digest'],providers=provenance['providers'],
            changed_catalogue_rows=len(provenance['changed_rows']),tracks=tracks)
        rows.append(row);print(json.dumps(dict(session=session,changed_tracks=sum(t['changed'] for t in tracks),
            max_centered_cfo_difference_hz=max(t['centered_cfo_difference_max_hz'] for t in tracks))),flush=True)
    result=dict(source_sha256=digest(Path(__file__)),catalogue_source_sha256=digest(HERE/'catalogue.py'),inputs=inputs,
        policy='Latest strictly causal snapshot per provider; newest element epoch per satellite; baseline row membership preserved; no geographic scoring',results=rows)
    with (HERE/'audit.json').open('x') as f:json.dump(result,f,indent=2)


if __name__=='__main__':main()
