"""Bounded full causal-bank native-path diagnostics; no position estimation."""
from pathlib import Path
import argparse
import signal
import time
import numpy as np
import mechanism as m
from ds23_family_cavity import coarse_phase_scores
from probe_ds23_linear_family_groups import group_data,residual_checks
from probe_ds23_family_cavity_nominations import candidate_prediction
from dsx01_inference_audit import validate_elements
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha

OUT=Path(__file__).resolve().parent

def shortlist(scores,target,k=7):
    return list(dict.fromkeys([int(target)]+[int(j) for j in np.argsort(scores) if np.isfinite(scores[j])][:k]))

def qualify(r):
    return bool(r['qualified'] and all(v['compatible'] for v in r['fixed_radio_checks']))

def run(suffix):
    started=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s screen cap')))
    signal.alarm(180)
    result=dict(suffix=suffix,status='failed')
    try:
        parent,kind,fragments,record=m.load('DS23-0259')
        chosen=[f for f in fragments if f['key'].endswith('_'+suffix)]
        assert len(chosen)==1
        fragment=chosen[0];changed=m.append(parent,chosen)
        cutoff=parent['scan'].receipt['cutoff_utc_ns']
        for element in parent['scan'].elements.values():validate_elements(element,cutoff)
        full=read(m.FROZEN/'raw/DS23-0259/native/DS23-0259.json')['methods']['persistent5s']['arms']
        contexts=[];pool={fragment['candidate_index']}
        for location,saved_pair in [('graph_parent',record['ordinary_graph']['arms']),('native_RF_endpoint',full)]:
            for arm in m.ARMS:
                saved=saved_pair[arm];x=np.asarray(saved['endpoint_east_north_km'])
                p=m.exp.paths.build(changed,kind,arm,saved['phase_reference'])
                index=len(parent['scan'].tracks)
                data=group_data(changed,p,x,[index]);data['target']=fragment['candidate_index']
                ids={o for i,sl in zip(p.members,p.slices,strict=True) for o,use in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if use}
                assert not ids.intersection(fragment['observation_ids'])
                d=dict(changed,x=x)
                f,e=phase_frequency_grid(p.scan.sky,data['times'],*latlon(x),phase_seconds=d['all_means'])
                plus=phase_frequency_grid(p.scan.sky,data['times'],*latlon(x),phase_seconds=d['all_means']+.01)[0]
                minus=phase_frequency_grid(p.scan.sky,data['times'],*latlon(x),phase_seconds=d['all_means']-.01)[0]
                coarse=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],data['q']*f,data['q']*(plus-minus)/.02,d['widths'],data['base_covariance'],data['groups'])
                scores=np.where(e.min(axis=1)>=0,coarse['score'],np.inf)
                local=shortlist(scores,data['target']);pool.update(local)
                contexts.append((location,arm,d,data,coarse,scores,x,local))
        rows=[]
        for location,arm,d,data,coarse,scores,x,local in contexts:
            candidates=[]
            for j in sorted(pool):
                r=candidate_prediction(d,data,j,coarse['aliases'][j])
                r['fixed_radio_checks']=residual_checks(data,r)
                r['physical_and_residual_qualified']=qualify(r)
                r['coarse_score']=float(scores[j]) if np.isfinite(scores[j]) else None;r['coarse_rank']=int(np.where(np.argsort(scores)==j)[0][0]+1)
                r['phase_prior_mean_s']=float(d['all_means'][j]);r['phase_prior_width_s']=float(d['widths'][j])
                candidates.append(r)
            candidates.sort(key=lambda r:r['score'])
            rows.append(dict(location=location,arm=arm,position_east_north_km=x,candidates=candidates,local_pool=local,
                visible_catalogue_count=int(np.isfinite(scores).sum()),coarse_scores=[float(v) if np.isfinite(v) else None for v in scores],coarse_aliases=coarse['aliases']))
        result.update(status='complete',fragment=fragment,rows=rows,candidate_pool=sorted(pool),catalogue_count=len(parent['scan'].norads),
            catalogue_norads=parent['scan'].norads,causal_cutoff_utc_ns=cutoff,all_element_epochs_and_collections_causal=True,
            active_families=sorted({int(p.scan.norads[r['candidate_index']]) for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}),
            inference='fixed calibration posterior; all path points held predictive; no GPS; no position refit; original plus union of top7 visible coarse candidates across matched arms and RF endpoints',
            limits='Gaussian moment phase proposals; at most union32 exact candidates, not exhaustive nonlinear catalogue fit; original curved identity remains calibration-conditioned; no multiple-search significance or identity posterior claimed',
            source_sha256=sha(Path(__file__)))
    except Exception as exc:
        import traceback
        result.update(error=repr(exc),traceback=traceback.format_exc())
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started
    write(OUT/(suffix+'.json'),result)
    return dict(status=result['status'],suffix=suffix,seconds=result['seconds'],error=result.get('error'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('suffix');args=parser.parse_args();print(run(args.suffix))
