"""Bounded complete host search using compact C scoring and the server frontier."""
import json
import struct
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
import numpy as np
from leo.analysis.adaptive_tle_position import adaptive_best_first_search,AdaptivePointScore,AdaptiveTrackScore
from leo.cli.adaptive_tle_position import _coordinates,_point_factory,PRIORS

HERE=Path(__file__).resolve().parent

def main():
    started=time.monotonic();m=json.loads((HERE/'inputs.json').read_text());local=HERE/'local'
    # Orbit states below were generated on ARM from the archived TLE.
    original=(local/'ephemeris-arm-generated.bin').read_bytes()
    tail=original[36+len(m['points'])*48:];header=list(struct.unpack('<5I2d',original[:36]))
    output={}
    for name,(lat,lon,radius) in PRIORS.items():
        points_done=0;native_seconds=0;makepoint=_point_factory(lat,lon)
        def evaluate(coordinates):
            nonlocal points_done,native_seconds
            rows=[]
            for offset in range(0,len(coordinates),8):
                assert time.monotonic()-started<600,'bounded search exceeded ten minutes'
                batch=coordinates[offset:offset+8];header[4]=len(batch)
                sites=[]
                for east,north in batch:
                    point=makepoint(float(east),float(north));sites.extend([*point.ecef_km,*point.up])
                fixture=local/'search-batch.bin'
                fixture.write_bytes(struct.pack('<5I2d',*header)+np.array(sites,dtype='<f8').tobytes()+tail)
                result=json.loads(subprocess.check_output([str(local/'score-host'),str(fixture)],text=True,timeout=30))
                native_seconds+=result['cpu_seconds']
                for (east,north),r in zip(batch,result['points'],strict=True):
                    tracks=[];qualifying=0;matched=0;qualified_tracks=0
                    for tr,score in zip(m['tracks'],r['tracks'],strict=True):
                        ids=tuple(tr['observation_ids']) if score['held_hz'] is not None and score['held_hz']<200 else ()
                        qualifying+=len(ids);qualified_tracks+=bool(ids);matched+=score['candidate_id']>=0
                        tracks.append(AdaptiveTrackScore(tr['track_id'],score['held_hz'],len(np.unique(np.floor(tr['times_s']))),str(score['candidate_id']) if score['candidate_id']>=0 else None,score['tau_s'],score['fit_hz'],score['offset_hz'],ids))
                    rows.append(AdaptivePointScore(float(east),float(north),r['score_hz']**2,r['score_hz'],qualifying,qualified_tracks,matched,len(tracks)-matched,tuple(tracks)))
                points_done+=len(batch)
                if points_done%40<8:print(name,points_done,'points',round(native_seconds,2),'native CPU s',flush=True)
            return tuple(rows)
        result=adaptive_best_first_search(evaluate,radius_km=radius)
        expected=next(x for x in m['points'] if x['name']==name)
        selected=result.global_incumbent;actual_lat,actual_lon=_coordinates(lat,lon,selected.east_km,selected.north_km)
        output[name]=dict(selected=asdict(selected),latitude_deg=actual_lat,longitude_deg=actual_lon,expected_latitude_deg=expected['latitude_deg'],expected_longitude_deg=expected['longitude_deg'],same_selected_location=abs(actual_lat-expected['latitude_deg'])<1e-10 and abs(actual_lon-expected['longitude_deg'])<1e-10,expected_score_hz=expected['expected_score_hz'],score_delta_hz=selected.residual_rmse_hz-expected['expected_score_hz'],evaluated_points=len(result.all_evaluations),search_complete=result.complete,stop_reason=result.stop_reason,native_cpu_seconds=native_seconds,trace=result.trace)
        (HERE/'host-search.json').write_text(json.dumps(output,indent=2)+'\n')
        print(name,'complete',output[name]['same_selected_location'],output[name]['score_delta_hz'],flush=True)
    print('total wall seconds',time.monotonic()-started,flush=True)

if __name__=='__main__':main()
