"""Report orchestration: verified caches -> matching -> joined M0/M1 diagnostic."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
import pickle
import sys
import numpy as np
from prepare import HERE, digest
import pairing


def load_inputs():
    inventory = json.loads((HERE/'evaluation_inventory.json').read_text())
    inputs = {}
    for x in inventory:
        if not x['ready']:
            continue
        data = (HERE/'cache'/f"{x['session_id']}.pickle").read_bytes()
        if digest(data) != x['cache_sha256']:
            raise ValueError('cache content differs from verified inventory')
        inputs[x['session_id']] = pickle.loads(data)
    return inventory, inputs


def paired_probes(raw):
    result = defaultdict(dict)
    for p in raw.probes:
        key = (p.visit_index, p.probe_index, p.probe_start_ms, p.channel, p.edge)
        if p.receiver_id in result[key]:
            raise ValueError('duplicate probe')
        result[key][p.receiver_id] = p
    if any(set(v) != {0,1} for v in result.values()):
        raise ValueError('missing paired probe is not a nondetection')
    return result


def summarize_pairs(inventory, inputs):
    cal = {x['session_id'] for x in inventory if x['split']=='calibration' and x['ready']}
    paired = {sid:paired_probes(raw) for sid,raw in inputs.items()}
    fit = pairing.calibration_bias((p[0].candidates,p[1].candidates,inputs[sid].sample_rate_hz)
                                  for sid in sorted(cal) for p in paired[sid].values())
    fit['probe_equal_sensitivity']=pairing.probe_equal_bias(
        ((p[0].candidates,p[1].candidates,inputs[sid].sample_rate_hz)
         for sid in sorted(cal) for p in paired[sid].values()),fit['bias_hz'])
    bias=fit['bias_hz']; summaries=[]
    for entry in inventory:
        sid=entry['session_id']
        if sid not in inputs:
            continue
        raw=inputs[sid]; pairs=paired[sid]; normal=Counter(); shifted=Counter(); lanes=defaultdict(list)
        for k,p in sorted(pairs.items()):
            normal[pairing.classify(p[0].candidates,p[1].candidates,raw.sample_rate_hz,bias)]+=1
            lanes[k[3:]].append(p)
        for lane in lanes.values():
            shift=len(lane)//2
            if min(shift,len(lane)-shift)<100:
                continue
            for i,p in enumerate(lane):
                q=lane[(i+shift)%len(lane)]
                shifted[pairing.classify(p[0].candidates,q[1].candidates,raw.sample_rate_hz,bias)]+=1
        summaries.append(dict(session_id=sid,split=entry['split'],sample_rate_hz=raw.sample_rate_hz,
                              visits=len(pairs),normal=dict(normal),shifted=dict(shifted)))
    out=dict(calibration_fit=fit,epoch_tolerance_us=pairing.EPOCH_TOL_S*1e6,
             cfo_tolerance_hz=pairing.CFO_TOL_HZ,per_scan=summaries)
    (HERE/'pairing_summary.json').write_text(json.dumps(out,indent=2)+'\n')
    return out,paired


def endpoint_rows(inventory, inputs, paired, associations, bias, source_links=None):
    from leo.application.scanner_trajectory import project_scanner_candidates
    by_session={x['session_id']:x for x in inventory}
    output=[]; accounting=[]
    for branch in associations['branches']:
        sid=branch['session_id']; raw=inputs[sid]; joined=Counter()
        track_times=defaultdict(list)
        for row in branch['rows']:
            track_times[row['track_id']].append(row['support_center_utc_ns'])
        spans={tid:(max(t)-min(t))/1e9 for tid,t in track_times.items()}
        projected=defaultdict(list)
        projected_by_id={}
        for c in project_scanner_candidates(raw):
            if c.candidate_id in projected_by_id:
                raise ValueError('duplicate projected candidate ID')
            projected[(*pairing.provenance_key(c),f'rx-{c.receiver_id}')].append(c)
            projected_by_id[c.candidate_id]=c
        links=None
        if source_links is not None:
            src=source_links[sid]
            for name in ('input_manifest_sha256','analysis_manifest_sha256'):
                if src[name]!=by_session[sid][name]:
                    raise ValueError('source-link digest mismatch')
            links={(r['track_id'],r['observation_id']):r['candidate_ids'] for r in src['rows']}
        probes={(p.visit_index,p.probe_index,p.receiver_id):p for p in raw.probes}
        if len(probes)!=len(raw.probes):
            raise ValueError('ambiguous probe key')
        seen=set()
        for a in branch['rows']:
            if a['training']:
                joined['excluded_doppler_training_observations']+=1
                continue
            key=(a['source_group_id'],a['source_sample_start'],a['source_sample_end'],a['support_center_utc_ns'],a['stream_id'])
            if links is None:
                cs=projected.get(key,[])
            else:
                ids=links.get((a['track_id'],a['projected_observation_id']),[])
                cs=[projected_by_id[cid] for cid in ids]
                if any((*pairing.provenance_key(c),f'rx-{c.receiver_id}')!=key for c in cs):
                    raise ValueError('exact candidate link disagrees with observation provenance')
            if len(cs)!=1:
                joined['ambiguous_provenance' if cs else 'missing_provenance']+=1
                continue
            c=cs[0]
            if c.candidate_id in seen:
                raise ValueError('one anchor would enter multiple scored tracks')
            seen.add(c.candidate_id)
            p=probes[(c.visit_index,c.probe_index,c.receiver_id)]
            other=probes[(c.visit_index,c.probe_index,1-c.receiver_id)]
            anchors=[x for x in p.candidates if x.candidate_rank==c.candidate_rank]
            if len(anchors)!=1:
                raise ValueError('ambiguous candidate rank')
            anchor=anchors[0]
            outcome=pairing.counterpart(anchor,other.candidates,c.receiver_id,raw.sample_rate_hz,bias)
            anchor_key=f'{sid}:{c.visit_index}:{c.probe_index}:{c.receiver_id}:{c.candidate_rank}'
            pair_key=None
            if outcome['matched']:
                other_key=f"{sid}:{c.visit_index}:{c.probe_index}:{1-c.receiver_id}:{outcome['counterpart_rank']}"
                pair_key='|'.join(sorted([anchor_key,other_key]))
            output.append(dict(session_id=sid,split='cal' if by_session[sid]['split']=='calibration' else 'holdout',
                track_id=a['track_id'],observation_id=a['projected_observation_id'],
                observation_utc_ns=a['support_center_utc_ns'],receiver_id=f'rx{c.receiver_id}',
                channel=c.channel,edge=c.edge.value,sample_rate_hz=raw.sample_rate_hz,
                anchor_margin=anchor.fractional_margin,east=a['u_east'],up=a['u_up'],
                source_track_span_s=spans[a['track_id']],
                east_variance=a['east_variance'],candidate_probabilities=a['candidate_probabilities'],
                candidate_ids=a.get('candidate_ids',[]),candidate_training_rms_hz=a.get('candidate_training_rms_hz',[]),
                branch=branch['branch'],physical_pair_key=pair_key,anchor_key=anchor_key,**outcome))
            joined['joined']+=1
        accounting.append(dict(session_id=sid,source_tracks=branch['track_count'],counts=dict(joined)))
    return output,accounting


def validate_associations(associations, inventory, manifest):
    expected={x['session_id']:x for x in inventory if x['ready']}
    poses={x['pose']['session_id']:x['pose']['pose_authority'] for x in manifest['sessions']}
    actual=[b['session_id'] for b in associations['branches']]
    if len(actual)!=len(set(actual)) or set(actual)!=set(expected):
        raise ValueError('association branches must cover exactly the frozen ready cohort once')
    for b in associations['branches']:
        sid=b['session_id']; x=expected[sid]; pose=poses[sid]
        if b['branch']!='truth_diagnostic' or b['site'].get('diagnostic_truth') is not True or b['split']!=x['split']:
            raise ValueError('association scope/split mismatch')
        if any(b['site'][k]!=pose[k] for k in ('latitude_deg','longitude_deg')):
            raise ValueError('association location does not bind pose')
        for key in ('input_manifest_sha256','analysis_manifest_sha256'):
            if key not in b or b[key]!=x[key]:
                raise ValueError('association source digest mismatch')
        if len({a['projected_observation_id'] for a in b['rows']})!=len(b['rows']):
            raise ValueError('duplicate association observation')
        for a in b['rows']:
            if 'propagation_utc_ns' not in a or abs(a['propagation_utc_ns']-a['support_center_utc_ns'])>1000:
                raise ValueError('missing or inconsistent propagation timestamp')


def unique_pair_sensitivity(rows, model_eval):
    """Secondary ratio: score each unordered compatible pair once, RX0 preferred."""
    choices={}
    for r in sorted(rows,key=lambda r:(r['receiver_id'],r['anchor_key'])):
        if r['physical_pair_key'] is not None:
            choices.setdefault(r['physical_pair_key'],r)
    unique=list(choices.values()); test=[r for r in unique if r['split']=='holdout']
    if not test or not any(r['split']=='cal' for r in unique):
        return {'status':'insufficient unique pairs'}
    fits=model_eval.fit_continuous_models(unique)
    return dict(rule='One unordered exact candidate pair; RX0 anchor preferred deterministically; refit calibration and score test under same rule',
                matched_anchor_rows=sum(r['matched'] for r in rows),unique_pairs=len(unique),
                removed_reciprocal_rows=sum(r['matched'] for r in rows)-len(unique),
                heldout=model_eval.score_models(fits,test),
                scan_bootstrap=model_eval.scan_bootstrap(fits,test))


def association_diagnostics(rows):
    tracks={}
    pairs=defaultdict(list)
    for r in rows:
        tracks.setdefault((r['session_id'],r['track_id']),r)
        if r['physical_pair_key'] is not None:
            pairs[r['physical_pair_key']].append(r)
    rms=[r['candidate_training_rms_hz'][0] for r in tracks.values() if r['candidate_training_rms_hz']]
    probabilities=[max(r['candidate_probabilities']) for r in tracks.values()]
    reciprocal=[q for q in pairs.values() if len(q)==2 and {r['receiver_id'] for r in q}=={'rx0','rx1'} and all(r['candidate_ids'] for r in q)]
    return dict(
        interpretation='Uncalibrated top3 Doppler weights at known position; same-signal compatibility is not decoded identity. Reciprocal pair statistics are descriptive and correlated within tracks.',
        map_training_rms_hz_quantiles_10_50_90=np.quantile(rms,[.1,.5,.9]).tolist() if rms else None,
        track_fraction_top_weight_above_095=float(np.mean(np.asarray(probabilities)>.95)),
        reciprocal_scored_candidate_pairs=len(reciprocal),
        reciprocal_map_satellite_agreement_fraction=float(np.mean([q[0]['candidate_ids'][0]==q[1]['candidate_ids'][0] for q in reciprocal])) if reciprocal else None,
        reciprocal_absolute_east_difference_median=float(np.median([abs(q[0]['east']-q[1]['east']) for q in reciprocal])) if reciprocal else None)


def main(pairing_only=False):
    inventory,inputs=load_inputs()
    summary,paired=summarize_pairs(inventory,inputs)
    if pairing_only:
        print(json.dumps(summary,indent=2));return
    import model_eval
    associations=json.loads((HERE/'associations.json').read_text())
    validate_associations(associations,inventory,json.loads((HERE/'evaluation_manifest.json').read_text()))
    source_links=json.loads((HERE/'source_links.json').read_text())
    rows,accounting=endpoint_rows(inventory,inputs,paired,associations,summary['calibration_fit']['bias_hz'],source_links)
    (HERE/'model_rows.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
    result=model_eval.evaluate(rows)
    result['association_diagnostics']=association_diagnostics(rows)
    result['unique_pair_continuous_sensitivity']=unique_pair_sensitivity(rows,model_eval)
    long_rows=[r for r in rows if r['source_track_span_s']>=30]
    if {r['split'] for r in long_rows}=={'cal','holdout'}:
        result['long_track_sensitivity']=dict(rule='Source track span >=30 seconds, fixed before scoring; refit same models on eligible calibration tracks',
            rows=len(long_rows),tracks=len({(r['session_id'],r['track_id']) for r in long_rows}),
            evaluation=model_eval.evaluate(long_rows))
    else:
        result['long_track_sensitivity']=dict(status='insufficient eligible calibration/test tracks')
    result.update(scope='Truth-position-conditioned directional feasibility diagnostic, not geographic search or measured location improvement',
                  pairing=summary,join_accounting=accounting,
                  rows=len(rows),tracks=len({(r['session_id'],r['track_id']) for r in rows}),
                  observation_policy='Only observations excluded from Doppler training mask; track construction remains selection-conditioned',
                  row_file_sha256=digest((HERE/'model_rows.json').read_bytes()),
                  association_file_sha256=digest((HERE/'associations.json').read_bytes()))
    result['source_links_sha256']=digest((HERE/'source_links.json').read_bytes())
    result['runtime_python']=sys.version
    result['code_sha256']={p.name:digest(p.read_bytes()) for p in sorted(HERE.glob('*.py'))}
    result['evaluation_manifest_sha256']=digest((HERE/'evaluation_manifest.json').read_bytes())
    result['max_propagation_to_support_delta_ns']=max(abs(a['propagation_utc_ns']-a['support_center_utc_ns']) for b in associations['branches'] for a in b['rows'])
    (HERE/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('scope','rows','tracks','join_accounting')},indent=2))
    for outcome in ('detection','continuous'):
        if outcome in result:
            print(outcome,json.dumps(result[outcome]['heldout']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pairing-only',action='store_true');args=p.parse_args()
    main(args.pairing_only)
