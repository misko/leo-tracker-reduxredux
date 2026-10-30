"""Trace an overlapping graph partition to original winning GLRT candidates."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive,track_events
from probe_ds23_frequency_events import cached
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.analysis.research.retained_track_likelihood import PERIOD,projected_receiver_basis


def original_winner(candidates, measured_cfo_hz):
    eligible=[c for c in candidates if c['passed_fractional_margin_gate']]
    if not eligible:raise ValueError('no eligible original candidate')
    winner=max(eligible,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
    if abs(winner['fractional_tracking_cfo_hz']-measured_cfo_hz)>1e-8:
        raise ValueError('original winner mismatch')
    return winner


def run(args):
    inv=read(args.inventory);d=context(inv);pr=read(args.trial/'protocol.json');saved=read(args.trial/'control.json')
    target=next(t for t in inv['tracks'] if t['track_id']==args.track);i=target['track_index'];track=d['scan'].tracks[i]
    root=Path(inv['job']['root'])/inv['job']['case'];observations=read(root/'observations.json');tracking=read(root/'tracking.json')
    evidence,_,_=frequency_evidence(tracking);probes=tracking['source']['probes']
    lookup={'sha256:'+hashlib.sha256(evidence.ids[k].encode()).hexdigest():p for k,p in enumerate(probes)}
    owners={o:t['key'] for t in d['scan'].tracks for o in t['observation_ids']}
    same=[t for t in d['scan'].tracks if (t['receiver'],t['channel'],t['rf_hz'])==(track['receiver'],track['channel'],track['rf_hz'])
        and t['end_s']>=track['start_s'] and t['start_s']<=track['end_s']]
    lane=[o for o in observations if (o['receiver'],o['channel'],o['actual_rf_hz'])==(track['receiver'],track['channel'],track['rf_hz'])
        and track['start_s']-5<=o['time_s']<=track['end_s']+5]
    times=np.array([o['time_s'] for o in lane]);values=np.array([o['measured_cfo_hz'] for o in lane]);rows=[]
    for o in lane:
        probe=lookup[o['observation_id']];winner=original_winner(probe['candidates'],o['measured_cfo_hz'])
        rows.append(dict(o,component=owners.get(o['observation_id'],'outside graph'),
            visit_index=probe['visit_index'],probe_index=probe['probe_index'],valid_start_counter=probe['valid_start_counter'],
            payload_start_sample=probe['payload_start_sample'],winner=winner,all_candidates=probe['candidates']))
    arms=[];synthetic=dict(track,times=times,values=values);synthetic.pop('pieces',None)
    for arm,v in saved['arms'].items():
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],d['means'],d['model'],pr['events'],**kw)
        attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.array(v['endpoint_east_north_km']);c=p.calculate(x);state=p.state(x)
        diff=c['negative_twice_elbo']-v['negative_twice_elbo']
        if abs(diff)>1e-5:raise ValueError('pulse control objective mismatch')
        j=pr['target']['candidate_index'];f,e=family_frequency(p,x,j,times=times);q=track['rf_hz']/11.5e9
        # Radio events are included in scan.hardware; add only family events.
        family=[k for k,event in enumerate(p.events) if event['kind']=='family']
        effect=track_events(synthetic,j,[p.events[k] for k in family])@c['coefficient'][p.event_start+np.array(family,int)] if family else np.zeros(len(times))
        predicted=p.scan.hardware(synthetic,state['beta'])+q*projected_receiver_basis(times)@state['smooth'][track['receiver']-1]+q*f+effect
        residual=(values-predicted+PERIOD/2)%PERIOD-PERIOD/2
        fragments=[];begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)
        for t in same:
            k=next((k for k,r in enumerate(p.rows) if r['component']==t['key']),None)
            fragments.append(dict(component=t['key'],original_graph=t,calibration_points=int(p.keep[p.slices[k]].sum()) if k is not None else 0,
                shared_family=p.rows[k]['candidate_index']==j if k is not None else False,
                fitted_fragment_constant_hz=float(p.constants[p.slices[k]][0,k]*c['coefficient'][begin+k]) if k is not None else None))
        arms.append(dict(arm=arm,objective_replay_difference=diff,position=v['endpoint_latlon'],norad=int(p.scan.norads[j]),
            orbit_plus_receiver_CFO_hz=predicted,residual_without_fragment_constants_hz=residual,
            minimum_elevation_deg=float(e.min()),fragments=fragments))
    paths=[args.inventory,args.trial/'protocol.json',args.trial/'control.json',root/'observations.json',root/'tracks.json',root/'tracking.json']
    write(args.output,dict(job=inv['job'],target=target,observations=rows,arms=arms,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        receiver_and_satellite_fit_excludes_target=True,no_new_association_or_position_fit=True,
        original_GLRT_winners_replayed=True,GPS_used=False,future_TLE=False))
    print('observations',len(rows),'overlapping tracks',len(same),'native winner replay complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','trial','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--track',required=True);run(p.parse_args())
