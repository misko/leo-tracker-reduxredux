"""Freeze radio-only partitions on all independent tracks of three pilot scans."""
import fcntl
from pathlib import Path
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from check_shared_scale import UNITS
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from radio_segmentation import partition
HERE=Path(__file__).resolve().parent


def main():
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        inputs={};sources={};records=[]
        def read(p):
            d=sealed(p);inputs[str(p)]=digest(p);return d
        overlay=read(HERE/'quality-overlay-v4/overlay.json');verify_sources(overlay['sources']);verify_sources(overlay['inputs'])
        for unit in UNITS:
            quality=read(HERE/'quality-residual-v1'/unit/'result.json');freeze=read(HERE/'quality-residual-v1'/unit/'sources.json')
            verify_sources(freeze['source_sha256']);verify_sources(freeze['inputs']);sources.update(freeze['source_sha256']);inputs.update(freeze['inputs'])
            raw=next(r for r in overlay['results'] if r['unit']==unit.split('-')[0]+'-F001');bytrack={r['track_id']:r['points'] for r in raw['tracks']}
            rows=[]
            for row in sorted(quality['signal_tracks']+quality['background_tracks'],key=lambda r:r['track_index']):
                points=bytrack[row['track_id']];start=points[0]['support_center_utc_ns']
                t=np.array([(p['support_center_utc_ns']-start)/1e9 for p in points]);y=np.array([p['normalized_dealiased_cfo_hz'] for p in points])
                results={}
                for name,sigma,penalty in [('primary',100.,6.),('half_penalty',100.,3.),('double_penalty',100.,12.),('noise300',300.,6.)]:
                    results[name]=partition(t,y,sigma=sigma,penalty_factor=penalty)
                thinned=None
                if unit=='DS10-B01-S1' and row['track_index'] in (16,17):
                    thinned={str(offset):partition(t[offset::2],y[offset::2]) for offset in (0,1)}
                rows.append(dict(track_id=row['track_id'],track_index=row['track_index'],samples=len(t),times_s=t.tolist(),
                    frequencies_hz=y.tolist(),observation_candidates=[p['candidate_id'] for p in points],results=results,thinned=thinned))
            records.append(dict(unit=unit,tracks=rows))
            print(unit,len(rows),{name:sum(len(r['results'][name]['segments'])>1 for r in rows) for name in results},flush=True)
        sources.update({str(HERE/n):digest(HERE/n) for n in ('radio_segmentation.py','check_radio_segmentation.py','test_radio_segmentation.py','SEGMENTATION_PLAN.md')})
        verify_sources(inputs);verify_sources(sources)
        save(HERE/'radio-segmentation-v1.json',dict(scans=records,inputs=inputs,sources=sources,
            qualification='Radio-only segmentation diagnostic on fixed independent membership, not localization or independent predictive validation. Full exported samples precede point cap; every sample preserved.'))


if __name__=='__main__':main()
