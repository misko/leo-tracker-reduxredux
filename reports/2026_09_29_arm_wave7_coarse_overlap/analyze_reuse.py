#!/usr/bin/env python3
"""Count exact Wave6 coarse-cell reuse without changing the search."""
import argparse,collections,hashlib,json
from pathlib import Path

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def geometry(rate):
    n=round(rate/750);probe=rate//50;stride=rate//100
    starts=[round((2+s*26)*rate*4.4e-6) for s in range(12)]
    stops=[round((3+s*26)*rate*4.4e-6) for s in range(12)]
    offsets=[round(frame*rate/750) for frame in range(16)]
    return n,probe,stride,starts,stops,offsets
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--features',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    selected=json.loads(a.manifest.read_text())['selected'];wanted={(x['session_id'],x['visit_index']) for x in selected}
    grouped=collections.defaultdict(list)
    for line in a.features.read_text().splitlines():
        row=json.loads(line);key=(row['context']['session_id'],row['context']['visit_index'])
        if key in wanted:grouped[key].append(row)
    assert set(grouped)==wanted
    totals=collections.defaultdict(lambda:{'dwells':0,'requests':0,'hits':0,'unique':0,'dwell_hit_fractions':[],'max_unique':0})
    for key in [(x['session_id'],x['visit_index']) for x in selected]:
        rows=grouped[key];rate=rows[0]['context']['rate_hz'];n,probe,stride,starts,stops,offsets=geometry(rate)
        seen=set();requests=hits=0
        for row in sorted(rows,key=lambda x:(x['window'],x['rx'])):
            epochs=set()
            for center in row['ranked_epochs']['combined'][:4]:epochs.update(range(max(0,center-2),min(n,center+3)))
            for symbol,(start,stop) in enumerate(zip(starts,stops)):
                taps=stop-start
                for frame_offset in offsets:
                    for epoch in epochs:
                        if start+frame_offset+epoch+taps>probe:continue
                        absolute=row['window']*stride+start+frame_offset+epoch
                        cache_key=(row['rx'],symbol,absolute);requests+=1
                        if cache_key in seen:hits+=1
                        else:seen.add(cache_key)
        bucket=totals[str(rate)];bucket['dwells']+=1;bucket['requests']+=requests;bucket['hits']+=hits
        bucket['unique']+=len(seen);bucket['max_unique']=max(bucket['max_unique'],len(seen));bucket['dwell_hit_fractions'].append(hits/requests if requests else 0)
    def finish(v):
        fractions=v.pop('dwell_hit_fractions');v['hit_fraction']=v['hits']/v['requests'];v['mean_unique_per_dwell']=v['unique']/v['dwells'];v['min_dwell_hit_fraction']=min(fractions);v['max_dwell_hit_fraction']=max(fractions);v['minimum_payload_bytes_per_unique_entry']=56;v['mean_minimum_payload_bytes']=v['mean_unique_per_dwell']*56;return v
    by_rate={k:finish(v) for k,v in sorted(totals.items())};requests=sum(x['requests'] for x in by_rate.values());hits=sum(x['hits'] for x in by_rate.values());unique=sum(x['unique'] for x in by_rate.values());dwells=sum(x['dwells'] for x in by_rate.values())
    result={'schema':'arm-wave7-coarse-overlap-reuse/v1','manifest':str(a.manifest),'manifest_sha256':sha(a.manifest),'features':str(a.features),'features_sha256':sha(a.features),'key':['receiver','symbol','absolute_sample_position'],'value':'12 normalized FP32 CFO magnitudes','dwells':dwells,'requests':requests,'hits':hits,'unique':unique,'hit_fraction':hits/requests,'maximum_compute_fraction_avoidable':hits/requests,'mean_unique_per_dwell':unique/dwells,'minimum_payload_bytes_per_unique_entry':56,'mean_minimum_payload_bytes':unique/dwells*56,'by_rate':by_rate}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
