"""Read-only comparison and time-reversal diagnostic for four long misses."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_30_arm_fast_tracks/server-baseline/output'
PREV=HERE.parent/'2026_09_30_arm_curvature_tracks'
sys.path.insert(0,str(PREV/'evaluation'))
import compare_membership as m


def main():
    dest=HERE/'long-four';dest.mkdir(exist_ok=True)
    so=m.read_observations(BASE/'server-observations.tsv')
    ao=m.read_observations(BASE/'arm-observations.tsv')
    ss=m.read_sources(BASE/'server-candidate-map.tsv',so)
    ass=m.read_sources(BASE/'arm-candidate-map.tsv',ao)
    refs=m.read_tracks(BASE/'server-tracks.tsv',so)
    rolling=m.read_tracks(HERE/'qualification/rolling/arm-0.tsv',ao)
    hybrid=m.read_tracks(PREV/'hybrid-v1/host/arm-a250-v2.tsv',ao)
    settings=json.loads((PREV/'evaluation/thresholds.json').read_text())
    origin=min(o.start_ns for o in so.values())
    # Reverse chronology only. CFOs, source identity, scores and tracker settings stay fixed.
    constant=min(o.start_ns for o in ao.values())+max(o.end_ns for o in ao.values())
    lines=(BASE/'arm-observations.tsv').read_text().splitlines()
    transformed=[lines[0]]
    for line in lines[1:]:
        f=line.split('\t');start,center,end=map(int,f[6:9])
        f[6:9]=map(str,(constant-end,constant-center,constant-start))
        transformed.append('\t'.join(f))
    reverse_input=dest/'reverse-observations.tsv'
    reverse_input.write_text('\n'.join(transformed)+'\n')
    binary=HERE/'rolling/artifacts/leo-streaming-rolling'
    run=subprocess.run([str(binary.resolve()),str(reverse_input.resolve())],
                       capture_output=True,text=True,check=True,timeout=60)
    (dest/'reverse-raw.tsv').write_text(run.stdout)
    (dest/'reverse.stderr').write_text(run.stderr)
    restored=[]
    for line in run.stdout.splitlines():
        f=line.split('\t')
        if f[0]=='TRACK':
            start,end,ref=map(int,f[8:11])
            f[8:11]=map(str,(constant-end,constant-start,constant-ref))
            f[11]=format(-float(f[11]),'.17g')
        restored.append('\t'.join(f))
    reverse_output=dest/'reverse-restored.tsv'
    reverse_output.write_text('\n'.join(restored)+'\n')
    backwards=m.read_tracks(reverse_output,ao)
    reverse_score=m.compare(refs,backwards,so,ao,ss,ass,settings)
    (dest/'reverse-evaluation.json').write_text(json.dumps(reverse_score,indent=2)+'\n')
    rows=[]
    fig,axes=plt.subplots(2,2,figsize=(15,10),layout='constrained')
    for ax,index in zip(axes.flat,[12,48,51,52]):
        ref=refs.values[index]
        expected=sorted(ref.points,key=lambda p:so[p.candidate].center_ns)
        t=np.array([(so[p.candidate].center_ns-origin)/1e9 for p in expected])
        f=np.array([p.dealiased_cfo_hz for p in expected])
        spacing=11.2e9/ref.lane.rf_hz/4.4e-6
        record={'reference':index,'channel':ref.lane.channel,'receiver':ref.lane.receiver,
                'duration_s':(ref.end_ns-ref.start_ns)/1e9,'reference_points':len(expected)}
        ax.plot(t,f/1000,'o-',ms=4,mfc='none',color='#1764a0',lw=.7,label='Server assigned points')
        for label,bank,color in [('rolling',rolling,'#d76a10'),('hybrid',hybrid,'#23935a'),
                                 ('reverse_diagnostic',backwards,'#953fa4')]:
            choices=[(m.membership_metrics(ref,track,so,ao,ss,ass,settings),track)
                     for track in bank.values if track.lane==ref.lane]
            met,track=max(choices,key=lambda q:(q[0]['consistent_source_count'],q[0]['in_span_output_purity']))
            shared=set(met['consistent_sources'])
            times=[(so[p.candidate].center_ns-origin)/1e9 for p in expected
                   if ':'.join(map(str,ss[p.candidate])) in shared]
            record[label]={'track':track.index,'coverage_count':met['consistent_source_count'],
                           'coverage':met['reference_source_coverage'],'purity':met['in_span_output_purity'],
                           'matching_time_range_s':[min(times),max(times)] if times else [],
                           'complete':m.complete(met,settings)}
            if label!='reverse_diagnostic':
                pts=sorted(((ao[p.candidate].center_ns-origin)/1e9,p.dealiased_cfo_hz)
                           for p in track.points if ref.start_ns<=ao[p.candidate].center_ns<=ref.end_ns)
                tt,ff=np.array(pts).T
                ff+=np.round((np.interp(tt,t,f)-ff)/spacing)*spacing
                ax.plot(tt,ff/1000,'.--',ms=4,lw=.9,color=color,label=label)
        record['input_support']=next(d for d in reverse_score['reference_input_support']
                                     if d['reference_track_index']==index)
        ax.axvspan(record['hybrid']['matching_time_range_s'][0],
                   record['rolling']['matching_time_range_s'][0],
                   color='#d76a10',alpha=.12,label='Initial portion omitted by rolling')
        rows.append(record)
        ax.set_title(f'Ref #{index}: Ch{ref.lane.channel}/RX{ref.lane.receiver} · {record["duration_s"]:.1f}s\n'
                     f'Rolling {record["rolling"]["coverage_count"]}/{len(expected)}; hybrid {record["hybrid"]["coverage_count"]}/{len(expected)}')
        ax.set_xlabel('Seconds from first projected observation')
        ax.set_ylabel('Alias-aligned normalized CFO (kHz)')
        ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=9)
    fig.suptitle('Four long tracks: rolling output omits initial detections\nMeasured points; the hybrid extends back to include earlier matching evidence')
    fig.savefig(dest/'comparison.png',dpi=160);fig.savefig(dest/'comparison.pdf')
    plt.close(fig)
    report={'rows':rows,'diagnostic':'Same rolling binary/config on time-reversed detections, restored to original coordinates; offline diagnostic, not a streaming implementation',
            'binary_sha256':m.digest(binary),'input_sha256':m.digest(BASE/'arm-observations.tsv'),
            'reverse_total_represented_excluding_ref10':len(set(reverse_score['primary']['reference_segments_with_any_complete_output_indexes'])-{10})}
    (dest/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
