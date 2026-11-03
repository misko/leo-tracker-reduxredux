"""Full-catalogue causal/following-TLE screens at frozen ALGO02 endpoints.

Screens nominate hypotheses; none change production associations or position.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import numpy as np
from sgp4.api import Satrec

from dbg01_unassociated import ownership, remaining_indices, orphan_blocks, candidate_gates, validate_post_version
from run_dbg01_case import DEFAULT, configure
import debug_algo02_ds23_0268 as engine
from analyze_dsx01_fixed_site import ecef_states
from leo.sky.propagation import ElementSetCatalogue
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import profile, whitening, projected_receiver_basis
from leo.analysis.research.polynomial_satellite_diagnostics import orbit_shape_lower_bounds
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha


@lru_cache(maxsize=2)
def inputs(case, root):
    out = configure(case, root)
    scan, node, keep, base, old = engine.context()
    observations = read(engine.SOURCE / case / 'observations.json')
    graph_ids = {oid for t in scan.tracks for oid in t['observation_ids']}
    audit = read(out / 'audit.json')
    result = {}
    by_key={t['key']:t for t in scan.tracks}
    for arm in engine.ARMS:
        rows = [dict(r,observation_ids=r.get('observation_ids',by_key[r['component']]['observation_ids']))
                for r in audit['arms'][arm]['associations']['tracks']]
        accepted = ownership(rows)
        saved = old['policy_arms'][arm]
        p = engine.build(node, keep, arm, np.array(saved['phase_reference']), engine.entries_for(old))
        x = np.asarray(saved['endpoint_east_north_km'])
        if abs(p.calculate(x)['negative_twice_elbo'] - saved['negative_twice_elbo']) > 1e-5:
            raise ValueError('frozen endpoint does not replay')
        state = p.state(x)
        curves = []
        for i, t in enumerate(scan.tracks):
            ix = remaining_indices(t, accepted)
            if not len(ix):
                continue
            q = t['rf_hz'] / 11.5e9
            corrected = t['values'] - scan.hardware(t, state['beta']) - q * scan.rx_basis[i] @ state['smooth'][t['receiver']-1]
            curves.append(dict(component=t['key'], track_index=i, receiver=t['receiver'], channel=t['channel'],
                rf_hz=t['rf_hz'], times=t['times'][ix], values=corrected[ix],
                observation_ids=[t['observation_ids'][k] for k in ix], original_track_points=len(t['times']),
                active_curvature=i in scan.curved, kind='unassociated_graph_subset'))
        for block in orphan_blocks(observations, graph_ids, accepted):
            rx, ch, rf, tile = block['key']
            obs = block['observations'];times=np.array([o['time_s'] for o in obs])
            temp=dict(receiver=rx, channel=ch, rf_hz=rf, times=times)
            raw=np.array([o['measured_cfo_hz'] for o in obs]);q=rf/11.5e9
            y=raw-scan.hardware(temp,state['beta'])-q*projected_receiver_basis(times)@state['smooth'][rx-1]
            curves.append(dict(component=f'{case}-RX{rx}-CH{ch}-ORPHAN-{tile:02d}',receiver=rx,channel=ch,
                rf_hz=rf,times=times,values=y,observation_ids=[o['observation_id'] for o in obs],
                original_track_points=0,active_curvature=False,kind='orphan_time_block_not_a_track'))
        unknown={o['observation_id'] for o in observations}-accepted
        enumerated=[oid for c in curves for oid in c['observation_ids']]
        if len(enumerated)!=len(set(enumerated)) or set(enumerated)!=unknown:
            raise ValueError('unassociated evidence partition is not exact')
        result[arm]=dict(curves=curves,x=x,accepted=len(accepted),total=len(observations),
            graph_unassociated=len(unknown & graph_ids),outside_graph=len(unknown-graph_ids))
    return scan,result


def prepare(case, root):
    out=configure(case,root);scan,arms=inputs(case,str(root))
    source=(ROOT/'reports/2026_10_20_ds23_0268_remaining_tracks/postscan_tles.json'
            if case=='DS23-0268' else Path('/srv/bulk/leo/research/ds23-0405-postscan-tles-20261021.json'))
    post=read(source);numbers=list(map(int,scan.norads));end=scan.receipt['origin_utc_ns']+300_000_000_000
    if any(not validate_post_version(v,end) for v in post['versions'].values()):
        raise ValueError('following TLE authority outside declared window')
    destination=out/'following_bank.npz'
    if not destination.exists():
        chosen=[post['versions'].get(str(n),scan.elements[str(n)]) for n in numbers]
        catalogue=ElementSetCatalogue(tuple(map(str,numbers)),tuple(numbers),
            tuple(Satrec.twoline2rv(*r['lines']) for r in chosen))
        position,velocity,usable=ecef_states(catalogue,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
        if not usable.all():raise ValueError('following TLE propagation failed')
        np.savez_compressed(destination,time_s=scan.sky['time_s'],position_km=position,velocity_km_s=velocity)
    write(out/'unassociated_protocol.json',dict(case=case,baseline='original ALGO02',
        frozen_RF_position_and_calibration=True,reference_position_not_used=True,
        future_TLEs_diagnostic_only=True,following_selection='earliest epoch and collection within 48 hours after scan',
        post_source=str(source),post_source_sha256=sha(source),post_missing=post['missing'],
        missing_following_elements_use_causal_but_are_labeled=True,same_catalogue_inventory=True,
        catalogue_candidates=len(numbers),phase_grid_s=np.linspace(-15,15,121),
        diagnostic_white_noise_sigma_hz=150,fragment_bias_prior_sigma_hz=300,
        original_gate_limits=dict(RMS_hz=450,bias_hz=3000,mean_z=3,slope_z=3,quadratic_bic_gain=10,step_z=4),
        orphan_blocks_are_fixed_20s_partitions_not_discovered_tracks=True,
        independent_phase_screen_does_not_imply_shared_family_acceptance=True,
        source_sha256={f:sha(ROOT/'tools'/f) for f in ['run_dbg01_unassociated.py','dbg01_unassociated.py']},
        counts={a:{k:v for k,v in d.items() if k not in ['curves','x']} for a,d in arms.items()}))
    write(out/'unassociated_inventory.json',dict(arms={a:d['curves'] for a,d in arms.items()}))
    print(dict(case=case,partition_counts={a:len(d['curves']) for a,d in arms.items()},following=len(post['versions'])),flush=True)


def detail(terms,noise,j,phase,norad,elevation,has_following):
    return dict(norad=int(norad),phase_s=float(phase),rms_hz=float(terms['rms'][j]),
        bias_hz=float(terms['bias'][j]),alias=int(terms['alias'][j]),cost=float(terms['cost'][j]),
        minimum_elevation_deg=float(elevation[j].min()),noise={k:v[j] for k,v in noise.items()},
        residual_hz=terms['residual'][j],real_following_element=bool(has_following))


def screen_job(case, root, kind, arm):
    out=configure(case,root);destination=out/f'unassociated_{kind}_{arm}.json'
    if destination.exists():return dict(case=case,kind=kind,arm=arm,cached=True)
    scan,arms=inputs(case,str(root));d=arms[arm]
    bank=scan.sky if kind=='causal' else dict(np.load(out/'following_bank.npz'))
    protocol=read(out/'unassociated_protocol.json');missing=set(protocol['post_missing'])
    curves=[c for c in d['curves'] if len(c['times'])>=4 and np.all(np.diff(c['times'])>0)]
    all_times=np.unique(np.concatenate([c['times'] for c in curves]))
    store=[dict(best={},passing=set(),best_passing=None) for c in curves]
    for phase in protocol['phase_grid_s']:
        geometry=prepare_phase_geometry(bank,all_times,np.full(len(scan.norads),phase))
        frequency,elevation,_=phase_linear_frequency(geometry,*latlon(d['x']))
        for c,s in zip(curves,store,strict=True):
            ix=np.searchsorted(all_times,c['times'])
            if not np.allclose(all_times[ix],c['times'],atol=1e-8,rtol=0):
                raise ValueError('point times absent from propagation bank')
            predicted=c['rf_hz']/11.5e9*frequency[:,ix];e=elevation[:,ix]
            terms=profile(c['values'],predicted,*whitening(c['times']),bias_sigma=300)
            passed,noise=candidate_gates(terms,e,c['times']);s['passing'].update(map(int,scan.norads[passed]))
            order=np.argsort(np.where(e.min(axis=1)>=0,terms['cost'],np.inf))[:6]
            passing_order=np.flatnonzero(passed)
            if len(passing_order):order=np.union1d(order,passing_order[np.argsort(terms['cost'][passing_order])[:3]])
            for j in order:
                if e[j].min()<0:continue
                n=int(scan.norads[j]);old=s['best'].get(n)
                if old is None or terms['cost'][j]<old['cost']:
                    item=detail(terms,noise,j,phase,n,e,kind=='following' and n not in missing)
                    lower=orbit_shape_lower_bounds(c['values'],c['times'],predicted[[j]])
                    item.update(passing=bool(passed[j]),offset_only_RMS_hz=float(lower['rms_offset_hz'][0]),
                        free_affine_RMS_hz=float(lower['rms_affine_hz'][0]),free_slope_hz_s=float(lower['slope_hz_s'][0]))
                    s['best'][n]=item
                if passed[j] and (s['best_passing'] is None or terms['cost'][j]<s['best_passing']['cost']):
                    s['best_passing']=detail(terms,noise,j,phase,n,e,kind=='following' and n not in missing)
                    s['best_passing']['passing']=True
    rows=[]
    for c,s in zip(curves,store,strict=True):
        candidates=sorted(s['best'].values(),key=lambda z:z['cost'])
        rows.append(dict(component=c['component'],kind=c['kind'],points=len(c['times']),
            receiver=c['receiver'],channel=c['channel'],start_s=float(c['times'][0]),end_s=float(c['times'][-1]),
            active_curvature=c['active_curvature'],candidates=candidates[:5],
            best_passing=s['best_passing'],passing_norads=sorted(s['passing'])))
    write(destination,dict(case=case,arm=arm,kind=kind,rows=rows,
        screened_points=sum(r['points'] for r in rows),
        insufficient_support_points=sum(len(c['times']) for c in d['curves'])-sum(r['points'] for r in rows),
        diagnostic_only_no_associations_adopted=True))
    return dict(case=case,arm=arm,kind=kind,curves=len(rows),passing=sum(r['best_passing'] is not None for r in rows))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=DEFAULT)
    parser.add_argument('--stage',choices=['prepare','screen'],required=True)
    parser.add_argument('--cases',nargs='+',default=['DS23-0268','DS23-0405'])
    args=parser.parse_args()
    if args.stage=='prepare':
        for case in args.cases:prepare(case,args.root)
    else:
        with ProcessPoolExecutor(max_workers=6) as pool:
            futures=[pool.submit(screen_job,case,args.root,kind,arm) for case in args.cases
                     for kind in ['causal','following'] for arm in engine.ARMS]
            for f in as_completed(futures):print(f.result(),flush=True)


if __name__=='__main__':main()
