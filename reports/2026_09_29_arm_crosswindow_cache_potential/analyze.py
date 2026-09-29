#!/usr/bin/env python3
"""Read-only final-GLRT frame-key reuse estimate for fused V4 host704 rows."""
import json,math,struct
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ROWS=ROOT.parent/'2026_09_29_arm_fused_pipeline/host704-v4/rows.jsonl'
QUANTA=(None,100,500,1000)

def nearby(value): return int(round(value))
def cfo_key(value,quantum):
    if quantum is None:return struct.pack('>d',value).hex()
    return nearby(value/quantum)*quantum
def frame_geometry(rate,window,epoch,frame,diverse=False):
    """Match glrt's final-scoring start/region and terminal late-to-early rule."""
    count=rate*120//1000
    start=window*rate//100+epoch+nearby(frame*rate/750)
    region=1 if diverse and frame&1 else 0
    first=nearby((2+150*region)*rate/150000)
    stop=nearby((66+150*region)*rate/150000)
    if region and start+stop-1>=count:
        region=0;first=nearby(2*rate/150000);stop=nearby(66*rate/150000)
    return None if start+stop-1>=count else (start,region)
def main():
    entries=[];within_duplicates=0;visible=0;frame_units=0
    by_rate=defaultdict(list)
    for record in map(json.loads,ROWS.read_text().splitlines()):
        rate=record['context']['rate_hz']
        for row in record['rows']:
            assert row['candidate_count']==len(row['candidates'])==8
            seen=set()
            for candidate in row['candidates']:
                assert candidate['glrt_complete']==1
                visible+=1;cfo=candidate['acquired_cfo_hz']
                call=(candidate['refined_epoch'],struct.pack('>d',cfo).hex())
                if call in seen:
                    within_duplicates+=1;continue
                seen.add(call)
                frames=[]
                for frame in range(16):
                    geometry=frame_geometry(rate,row['probe_index'],candidate['refined_epoch'],frame)
                    if geometry is None:break
                    frames.append(geometry)
                assert frames
                frame_units+=len(frames)
                entries.append((rate,row['receiver_id'],cfo,frames));by_rate[rate].append(entries[-1])
    def measure(items,quantum):
        keys=[]
        for rate,receiver,cfo,frames in items:
            keys.extend((rate,receiver,start,region,cfo_key(cfo,quantum)) for start,region in frames)
        counts=Counter(keys);hits=sum(n-1 for n in counts.values());reused=sum(n for n in counts.values() if n>1)
        return {'unique_frame_keys':len(counts),'cross_window_frame_hits':hits,
                'reused_frame_evaluations':reused,'cross_window_hit_fraction':hits/len(keys) if keys else 0}
    output={'schema':'cross-window-final-glrt-frame-cache-potential/v1','input_rows_sha256':__import__('hashlib').sha256(ROWS.read_bytes()).hexdigest(),
        'scope':'visible final GLRT candidate results only; unrecorded initial boundary-fallback calls excluded; no speed or quality claim',
        'geometry':{'absolute_frame_start':'probe_index*Fs/100 + refined_epoch + nearbyint(frame*Fs/750)','final_frames':16,'symbol_region':'early 64 symbols; frozen V4 diversity macro is 0','late_terminal_rule':'implemented for diversity geometry: a late frame crossing dwell end switches to early before support test'},
        'visible_final_candidate_calls':visible,'within_window_duplicate_final_calls_removed':within_duplicates,
        'candidate_calls_after_within_window_cache':visible-within_duplicates,'frame_evaluations_after_within_window_cache':frame_units,
        'hypotheses':{},'by_rate':{}}
    for quantum in QUANTA:
        label='exact_cfo_bits' if quantum is None else f'rounded_{quantum}_hz'
        output['hypotheses'][label]=measure(entries,quantum)
        output['by_rate'][label]={str(rate):measure(items,quantum) for rate,items in sorted(by_rate.items())}
    (ROOT/'potential.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
if __name__=='__main__':main()
