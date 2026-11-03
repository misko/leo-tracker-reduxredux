"""Oracle-seeded retained-catalogue timing ONLY; no discovery/recall claim."""
import json
import numpy as np
from arm import HERE,ROOT,remote,upload
from check import pack,compare

def main():
    m=json.loads((HERE/'inputs.json').read_text());local=HERE/'local';nk=(m['knots']-1)//10+1
    # Intentional oracle seeding isolates compute after identity hypotheses
    # exist. Do not use it as a shortlist-selection or recovery experiment.
    retained=sorted({int(x['candidate_id']) for p in m['points'] for x in p['expected_tracks'] if x['candidate_id'] is not None})
    indexes=[m['satellite_ids'].index(x) for x in retained]
    states=np.fromfile(local/'arm-states.bin',dtype='<f8').reshape(len(m['satellite_ids']),nk,6)
    fixture=local/'oracle-seeded-warm.bin';pack(fixture,m,states[indexes],10,ids=retained);upload(fixture)
    result=json.loads(remote('ulimit -v 180000; '+ROOT+'/score-arm '+ROOT+'/'+fixture.name,30))
    result['scope']='Timing only: 49 saved winning satellite identities seeded from both published final locations; no independent discovery, recovery or online transfer claim'
    result['retained_ids']=retained
    result['comparison']=compare(m,result)
    (HERE/'oracle-seeded-warm-timing.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['scope'],result['wall_seconds'],'seconds for two points',result['peak_rss_kib'],'KiB',flush=True)

if __name__=='__main__':main()
