"""Pure support-authority conversion for the native location track port."""
import math


def graph_authority(observations, supports, projection_receipt, orbit_authority):
    if projection_receipt['capture_digest'] != orbit_authority['capture_digest']:
        raise ValueError('orbit and observations belong to different captures')
    origin=orbit_authority['start_utc_ns']
    if type(origin) is not int or origin<=0:
        raise ValueError('invalid orbit time origin')
    if len(supports)!=len(observations):
        raise ValueError('support inventory differs from observations')
    support_map={s['candidate_id']:s for s in supports}
    if len(support_map)!=len(supports) or support_map.keys()!=observations.keys():
        raise ValueError('support candidate identity mismatch')
    lo=orbit_authority['knot_start_s']
    hi=lo+(orbit_authority['knot_count']-1)*orbit_authority['knot_step_s']
    lines=['\t'.join(['META',orbit_authority['session_id'],orbit_authority['capture_digest'],str(origin)]),
           'candidate_id\tstart_utc_ns\tcenter_utc_ns\tend_utc_ns\tm0\tm1\tm2\tm3']
    for cid,o in observations.items():
        relative=(o.center_ns-origin)/1e9
        if relative-5<lo or relative+5>hi:
            raise ValueError('orbit authority does not cover observation plus time-offset search')
        if not o.start_ns<=o.center_ns<o.end_ns:
            raise ValueError('invalid half-open observation support')
        s=support_map[cid]
        if s['source_start_counter']>=s['source_end_counter']:
            raise ValueError('empty sample support')
        moments=s['factorial_support_moments_s']
        if len(moments)!=4 or not all(math.isfinite(v) for v in moments) or moments[0]!=1 or moments[1]!=0 or moments[2]<0:
            raise ValueError('invalid support moments')
        lines.append('\t'.join(map(str,[cid,o.start_ns,o.center_ns,o.end_ns,*moments])))
    return '\n'.join(lines)+'\n'


def overlap_audit(tracks):
    """Exact reused candidate memberships; does not claim independent families."""
    owners={}
    for tr in tracks.values:
        for p in tr.points:owners.setdefault(p.candidate,[]).append(tr.index)
    reused={cid:ids for cid,ids in owners.items() if len(ids)>1}
    return {'reused_candidate_count':len(reused),'extra_memberships':sum(len(ids)-1 for ids in reused.values()),
            'independent_evidence_claimed':False,'reused_candidates':reused,
            'warning':'Raw hypotheses are preserved. Aggregate scoring is diagnostic until conflicts are resolved.'}
