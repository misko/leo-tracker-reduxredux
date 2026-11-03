"""RF-only check for 15-second scheduling-boundary CFO discontinuities.

Polynomial residual increments are compared across equal gap bins. This reads
existing graph tracks and radio noise contracts only: no orbital state,
satellite identity, inferred position or evaluation coordinate is used.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

from ds23_frame_registration import wrap
from localize_merged_track_catalogue import raw_curvature
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE=ROOT/'reports/2026_10_19_algo02_ds23_full'
OUT=ROOT/'reports/2026_10_19_algo03_fai_residuals'
PHASES=np.arange(15.)
GAP_EDGES=np.linspace(0,3,7)


def accumulate(times,residual,noise,origin_mod_s,phases=PHASES):
    t,r,s=(np.asarray(v,float) for v in (times,residual,noise))
    gap=np.diff(t);use=(gap>0)&(gap<=3)
    value=np.diff(r)**2/(s[:-1]**2+s[1:]**2)
    bins=np.minimum(np.searchsorted(GAP_EDGES,gap,side='right')-1,len(GAP_EDGES)-2)
    # [phase, receiver/target kind handled by caller, crossing, gap bin].
    count=np.zeros((len(phases),2,len(GAP_EDGES)-1),int)
    total=np.zeros_like(count,float);squares=np.zeros_like(total)
    for k,phase in enumerate(phases):
        crossing=np.floor((t[1:]+origin_mod_s-phase)/15)!=np.floor((t[:-1]+origin_mod_s-phase)/15)
        for flag in (0,1):
            sel=use&(crossing==flag)
            count[k,flag]=np.bincount(bins[sel],minlength=count.shape[-1])
            total[k,flag]=np.bincount(bins[sel],weights=value[sel],minlength=count.shape[-1])
            squares[k,flag]=np.bincount(bins[sel],weights=value[sel]**2,minlength=count.shape[-1])
    return count,total,squares,use,value


def run(case):
    directory=SOURCE/case
    needed=['tracks.json','radio_noise.json','receipt.json']
    if not all((directory/name).exists() for name in needed):
        return dict(case=case,status='missing_RF_contract')
    tracks=read(directory/'tracks.json');noise=read(directory/'radio_noise.json')
    receipt=read(directory/'receipt.json');origin_mod=(receipt['origin_utc_ns']%15_000_000_000)/1e9
    count=np.zeros((2,len(PHASES),2,len(GAP_EDGES)-1),int)
    total=np.zeros_like(count,float);squares=np.zeros_like(total)
    largest=[];curves=0;pieces=0
    for track in tracks:
        t=np.asarray(track['times']);y=np.asarray(track['values'])
        if not raw_curvature(dict(times=t,values=y)):
            continue
        curves+=1
        for piece in track['pieces']:
            # Persisted indices are lane indices, not positions in this track.
            lookup={int(v):k for k,v in enumerate(track['indices'])}
            ix=np.array([lookup[int(v)] for v in piece['indices']])
            if len(ix)<6:
                continue
            x=(t[ix]-piece['reference_time_s'])/piece['time_scale_s']
            prediction=np.polynomial.legendre.legval(x,piece['coefficients_hz'])
            residual=wrap(y[ix]-prediction)
            if np.sqrt(np.mean(residual**2))>600:
                raise ValueError('graph polynomial branch/representation replay failed')
            sigma=np.array([noise['per_observation_noise_sigma_hz'][track['observation_ids'][k]]
                if noise['extra_parameter_BIC_gain']>0 else noise['constant_radio_sigma_hz'] for k in ix])
            c,s,ss,use,value=accumulate(t[ix],residual,sigma,origin_mod)
            rx=track['receiver']-1;count[rx]+=c;total[rx]+=s;squares[rx]+=ss;pieces+=1
            for k in np.argsort(value*use)[-3:]:
                if not use[k]:
                    continue
                largest.append(dict(component=track['key'],receiver=rx+1,channel=track['channel'],
                    time_s=t[ix][k:k+2],residual_hz=residual[k:k+2],
                    normalized_increment_square=float(value[k]),
                    midpoint_phase_UTC_s=float((origin_mod+np.mean(t[ix][k:k+2]))%15)))
    result=dict(case=case,status='complete',raw_curved_tracks=curves,polynomial_pieces=pieces,
        counts=count,total=total,squared_totals=squares,
        largest_increments=sorted(largest,key=lambda r:-r['normalized_increment_square'])[:12],
        source_sha256={name:sha(directory/name) for name in needed},
        no_GPS_TLE_satellite_ID_or_position_used=True)
    write(OUT/(case+'.json'),result)
    return dict(case=case,status='complete',pairs=int(count[:,0].sum()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all',action='store_true');parser.add_argument('--workers',type=int,default=30)
    args=parser.parse_args()
    if OUT.exists():
        raise FileExistsError('preserve boundary hypothesis test')
    OUT.mkdir()
    cases=([r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']] if args.all else
           read(ROOT/'reports/2026_10_19_algo03_catalogue72/protocol.json')['cases'])
    write(OUT/'protocol.json',dict(cases=cases,workers=args.workers,UTC_phase_s=PHASES,
        gap_edges_s=GAP_EDGES,source_sha256=sha(Path(__file__)),
        independent_of_orbits_associations_and_position=True,
        original_graph_polynomials_replayed_without_refit_or_point_selection=True,
        statistic='squared residual increments / sum of independently estimated point variances; compare crossing versus noncrossing within gap bin',
        no_new_position_or_calibration_fit=True))
    started=time.monotonic();results=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run,c) for c in cases]):
            r=future.result();results.append(r);print(r,flush=True)
    write(OUT/'execution.json',dict(results=results,seconds=time.monotonic()-started))


if __name__=='__main__':
    main()
