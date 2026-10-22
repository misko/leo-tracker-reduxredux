"""Longest unused graph tracks, including linear tracks; following TLE is diagnostic."""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from sgp4.api import Satrec
from sgp4.exporter import export_tle

import run_ds23_dbg01_iteration_007 as runner
from probe_ds23_linear_family_groups import group_data
from probe_ds23_family_cavity_nominations import candidate_prediction
from ds23_family_cavity import coarse_phase_scores
from diagnose_ds23_iteration002_curves import phase_profile
from prepare_ds23_dbg01_following import archive_window
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets,ElementSetCatalogue
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from analyze_dsx01_fixed_site import ecef_states
from dbg01_unassociated import validate_post_version
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'all_track_diagnostics'


def choose_targets(ranking):
    return [r for r in ranking if r['points']==r['original_points'] and r['points']>=8][:3]


def following(d,wanted):
    end=int(d['scan'].receipt['origin_utc_ns'])+300_000_000_000;high=end+int(48*3600e9)
    reader=TleArchiveReader(Path('/var/lib/leo/tle'));snapshots,adapter=archive_window(reader,end,high,wanted);versions={}
    for s in snapshots:
        if not s['text'].strip():continue
        c=parse_element_sets(s['text'])
        for name,n,sat,epoch in zip(c.names,c.satellite_numbers,c.satellites,c.element_epoch_utc_ns(),strict=True):
            if n not in wanted or not end<epoch<=high:continue
            previous=versions.get(str(n));key=(epoch,s['collected'])
            if previous is None or key<(previous['element_epoch_utc_ns'],previous['collected_utc_ns']):
                versions[str(n)]=dict(norad=int(n),name=name,lines=list(export_tle(sat)),element_epoch_utc_ns=int(epoch),
                    collected_utc_ns=s['collected'],snapshot_digest=s['digest'])
    assert all(validate_post_version(v,end) for v in versions.values())
    return dict(end_utc_ns=end,versions=versions,missing=sorted(wanted-set(map(int,versions))),archive_adapter=adapter)


def one(case):
    d=runner.engine.current_setup(case);saved=d['arms']['c0'];x=np.asarray(saved['endpoint_east_north_km']);p=runner.engine.baseline.build(d,'c0',saved['phase_reference'])
    ranking=read(runner.RAW/case/'inventory.json')['arms']['c0']['ranking'];targets=choose_targets(ranking)
    rows=[];wanted=set()
    for target in targets:
        i=target['track_index'];data=group_data(d,p,x,[i]);freq,el=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means'])
        plus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']+.01)[0]
        minus=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(x),phase_seconds=d['all_means']-.01)[0]
        coarse=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],data['q']*freq,data['q']*(plus-minus)/.02,d['widths'],data['base_covariance'],data['groups'])
        scores=np.where(el.min(axis=1)>=0,coarse['score'],np.inf);pool=[int(j) for j in np.argsort(scores) if np.isfinite(scores[j])][:7]
        dd=dict(d,x=x);candidates=sorted([candidate_prediction(dd,data,j,coarse['aliases'][j]) for j in pool],key=lambda r:r['score'])[:3]
        wanted.update(r['norad'] for r in candidates);rows.append(dict(target=target,candidates=candidates))
    future=following(d,wanted);write(OUT/(case+'_following.json'),future)
    for row in rows:
        i=row['target']['track_index'];data=group_data(d,p,x,[i]);track=d['scan'].tracks[i]
        residual=np.asarray(track['values']).copy()
        for piece in track['pieces']:
            use=(track['times']>=piece['start_s']-1e-8)&(track['times']<=piece['end_s']+1e-8)
            residual[use]-=np.polynomial.legendre.legval((track['times'][use]-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz'])
        row['graph_residual_hz']=residual;row['graph_RMS_hz']=float(np.sqrt(np.mean(residual**2)));row['times']=track['times']
        for candidate in row['candidates']:
            j=candidate['candidate_index'];bank=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
            profiles=dict(causal=phase_profile(data,bank,x,candidate['aliases']));v=future['versions'].get(str(candidate['norad']))
            if v:
                cat=ElementSetCatalogue((str(candidate['norad']),),(candidate['norad'],),(Satrec.twoline2rv(*v['lines']),))
                pos,vel,good=ecef_states(cat,d['scan'].receipt['origin_utc_ns'],bank['time_s'])
                if not good.all():raise ValueError('following propagation failed')
                profiles['following']=phase_profile(data,dict(bank,position_km=pos,velocity_km_s=vel),x,candidate['aliases'])
            candidate['profiles']=profiles;candidate['real_following_element']=v is not None
        print(case,track['key'],[(r['norad'],{a:v.get('conditional_RMS_hz') for a,v in r['profiles'].items()}) for r in row['candidates']],flush=True)
    write(OUT/(case+'.json'),dict(case=case,rows=rows,all_original_point_IDs_preserved=True,
        longest_three_unused_whole_graph_tracks_including_linear=True,
        all_catalogue_search_is_coarse_then_best7_refined_not_identity_truth=True,
        following_TLEs_diagnostic_only_no_identity_or_position_adopted=True,
        fixed_RF_endpoint_and_causal_receiver_posterior=True,source_sha256=sha(Path(__file__))))
    return dict(case=case,status='complete',targets=len(rows))


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve track diagnostics')
    record=dict(cases=read(runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        scope='three longest wholly unused graph tracks >=8points, any polynomial order',
        no_GPS_or_point_trimming=True,following_elements_never_enter_inference=True)
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,record['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
