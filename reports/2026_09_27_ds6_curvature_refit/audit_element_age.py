"""Descriptive age audit of training-MAP orbit elements; not an orbit-error test."""
import json
import sys
from pathlib import Path
import numpy as np

from run_refit import HERE,REPORTS,digest,TleArchiveReader,exclude_labelled_starlink_debris,parse_element_sets


def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));cache={};rows=[];sources={}
    for session in protocol['development_sessions']:
        source=REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json'
        assignment_path=REPORTS/'2026_09_27_ds6_clock_curvature_converged'/f'{session}.json'
        data=json.loads(source.read_text())
        assignments=json.loads(assignment_path.read_text())['assignments']
        sources[str(source.relative_to(REPORTS))]=digest(source)
        sources[str(assignment_path.relative_to(REPORTS))]=digest(assignment_path)
        snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000)
        assert snap.digest==data['snapshot_digest']
        if snap.digest not in cache:
            payload,_=exclude_labelled_starlink_debris(archive.read(snap));cache[snap.digest]=parse_element_sets(payload)
        cat=cache[snap.digest];epochs=cat.element_epoch_utc_ns()
        tracks=[dict(track_id=t['track_id'],candidate_index=t['candidate_index'],
            satellite_number=cat.satellite_numbers[t['candidate_index']],
            age_h=(data['start_utc_ns']-epochs[t['candidate_index']])/3.6e12) for t in assignments]
        ages=[t['age_h'] for t in tracks]
        rows.append(dict(session=session,snapshot_digest=snap.digest,tracks=tracks,
            minimum_age_h=min(ages),median_age_h=float(np.median(ages)),maximum_age_h=max(ages)))
    result=dict(source_sha256=digest(Path(__file__)),inputs=sources,
        scope='Descriptive development-set element ages at training-MAP identities; does not establish ephemeris error, confirmed identity, or justify a geographic correction',results=rows)
    with (HERE/'element_ages.json').open('x') as f:json.dump(result,f,indent=2)
    for row in rows:print(json.dumps({k:v for k,v in row.items() if k!='tracks'}))


if __name__=='__main__':main()
