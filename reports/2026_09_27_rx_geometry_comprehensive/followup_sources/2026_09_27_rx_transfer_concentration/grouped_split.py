"""Session-wide seeded assignment of provenance-joined time blocks.

Only acquisition metadata enter the assignment. This is not an assertion that
separate blocks have zero temporal correlation.
"""
import hashlib
import json


def randomized_groups(rows, session_id, seed=20260927, block_ns=10_000_000_000):
    if not rows or not isinstance(session_id,str) or not session_id:
        raise ValueError('rows and session required')
    if isinstance(seed,bool) or not isinstance(seed,int): raise ValueError('integer seed required')
    if isinstance(block_ns,bool) or not isinstance(block_ns,int) or block_ns<=0:
        raise ValueError('positive block width required')
    rows=sorted(rows,key=lambda r:(r['track_id'],r['observation_id']))
    keys=[(r['track_id'],r['observation_id']) for r in rows]
    if len(set(keys))!=len(keys): raise ValueError('duplicate observation')
    for r in rows:
        for field in ('utc_ns','sample_start','sample_end'):
            if isinstance(r[field],bool) or not isinstance(r[field],int): raise ValueError('integer provenance required')
        if r['sample_end']<=r['sample_start'] or not r['source_group_id']:
            raise ValueError('invalid source interval')
    parent=list(range(len(rows)))
    def root(i):
        while parent[i]!=i: parent[i]=parent[parent[i]];i=parent[i]
        return i
    def join(i,j): parent[root(j)]=root(i)
    owners={}; sources={}
    for i,r in enumerate(rows):
        group_keys=[('time_block',r['utc_ns']//block_ns)]
        for name in ('opportunity_key','physical_pair_key'):
            if r.get(name) is not None:
                group_keys.append((name,json.dumps(r[name],sort_keys=True,separators=(',',':'))))
        for key in group_keys:
            if key in owners:join(i,owners[key])
            else:owners[key]=i
        sources.setdefault(r['source_group_id'],[]).append(i)
    for members in sources.values():
        # Interval sweep joins all transitively overlapping half-open windows.
        members.sort(key=lambda i:(rows[i]['sample_start'],rows[i]['sample_end']))
        leader=members[0];end=rows[leader]['sample_end']
        for i in members[1:]:
            if rows[i]['sample_start']<end:
                join(leader,i);end=max(end,rows[i]['sample_end'])
            else:leader=i;end=rows[i]['sample_end']
    components={}
    for i in range(len(rows)):components.setdefault(root(i),[]).append(i)
    result=[]
    for members in components.values():
        # Group signature excludes measured frequency, RX outcomes, old labels,
        # and candidate scores. Session namespace prevents cross-scan coupling.
        blocks=sorted({rows[i]['utc_ns']//block_ns for i in members})
        signature=json.dumps([seed,session_id,block_ns,blocks],separators=(',',':')).encode()
        digest=hashlib.sha256(signature).hexdigest()
        bucket=int(digest[:16],16)%4
        label=('train','train','A','B')[bucket]
        result.append({'group_id':digest,'time_blocks':blocks,'partition':label,
                       'observations':[{'track_id':rows[i]['track_id'],
                                        'observation_id':rows[i]['observation_id']} for i in members]})
    result.sort(key=lambda r:r['group_id'])
    return {'seed':seed,'session_id':session_id,'block_ns':block_ns,
            'assignment':'sha256 group hash modulo 4: train/train/A/B',
            'groups':result}
