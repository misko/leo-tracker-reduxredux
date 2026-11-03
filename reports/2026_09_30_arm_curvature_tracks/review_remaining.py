"""Explicit ref-10 exception and read-only review of all other discrepancies."""
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
DEST = HERE/'longest-missing'
BASE = HERE.parent/'2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0, str(HERE/'evaluation'))
import compare_membership as m


def main():
    so=m.read_observations(BASE/'server-observations.tsv')
    ao=m.read_observations(BASE/'arm-observations.tsv')
    ss=m.read_sources(BASE/'server-candidate-map.tsv',so)
    ass=m.read_sources(BASE/'arm-candidate-map.tsv',ao)
    refs=m.read_tracks(BASE/'server-tracks.tsv',so)
    arm=m.read_tracks(HERE/'physical-arm-a250.tsv',ao)
    settings=json.loads((HERE/'evaluation/thresholds.json').read_text())
    diagnoses=json.loads((DEST/'diagnosis.json').read_text())
    remaining=[d for d in diagnoses if d['reference_index'] != 10]
    assert len(remaining)==16
    comparisons={}
    for name,path in [('coarse',HERE/'hybrid-v1/seeds/arm.tsv'),
                      ('expanded',HERE/'hybrid-v1/host/arm-a250-v2.tsv')]:
        out=m.read_tracks(path,ao)
        report=m.compare(refs,out,so,ao,ss,ass,settings)
        report['diagnostic_input']={'path':str(path),'sha256':m.digest(path),
            'scope':'Previously executed host hypothesis bank; not a new physical ARM execution'}
        (DEST/f'{name}-diagnostic.json').write_text(json.dumps(report,indent=2)+'\n')
        comparisons[name]=report
    original=json.loads((HERE/'host-v2/arm-a250.membership.json').read_text())
    seeds=json.loads((DEST/'arm-seed-audit/audit.json').read_text())
    seed_by_ref={d['reference_track_index']:d for d in seeds['references']}
    rows=[]
    for d in remaining:
        index=d['reference_index']
        rows.append({**d,'seed_audit':seed_by_ref[index],
            'diagnostic_alternative_has_complete_match':{name:index in report['primary'][
                'reference_segments_with_any_complete_output_indexes']
                for name,report in comparisons.items()}})
    exception={'schema':'leo-reviewed-server-segmentation-exceptions/v1',
        'scope':'This frozen scan and server segmentation only; original metrics unchanged',
        'reference_tracks_sha256':m.digest(BASE/'server-tracks.tsv'),
        'physical_arm_tracks_sha256':m.digest(HERE/'physical-arm-a250.tsv'),
        'exceptions':[{'reference_index':10,'authorization':'User explicitly requested exception',
            'reason':'Pre-divergence curvature predicts ref16 branch followed by ARM; server ref10 tail likely misassigned',
            'evidence':'ref10-continuation.json','treatment':'Excluded from reviewed server-agreement denominator; not counted as a new recovered track'}],
        'original_reference_segments':63,'reviewed_reference_segments':62,
        'represented_reference_segments':original['primary']['reference_segments_with_any_complete_output_count'],
        'remaining_discrepancies':len(rows),
        'limits':'Server agreement is not physical tracking accuracy. Ref35 remains included pending review.'}
    (DEST/'exceptions.json').write_text(json.dumps(exception,indent=2)+'\n')
    (DEST/'remaining-review.json').write_text(json.dumps(rows,indent=2)+'\n')
    origin=min(o.start_ns for o in so.values())
    for page in range(2):
        fig,axes=plt.subplots(4,2,figsize=(15,14),layout='constrained')
        for ax,d in zip(axes.flat,rows[page*8:(page+1)*8]):
            ref=refs.values[d['reference_index']]
            pts=d['points']
            t=np.array([p['time_s'] for p in pts]);f=np.array([p['server_cfo_hz'] for p in pts])
            ax.plot(t,f/1000,'.-',color='#1764a0',lw=.9,label='Server reference points')
            yes=np.array([p['arm_consistent']>0 for p in pts])
            ax.scatter(t[yes],f[yes]/1000,s=35,facecolors='none',edgecolors='#23935a',label='Matching ARM input exists')
            ax.scatter(t[~yes],f[~yes]/1000,s=25,marker='x',color='#bd2040',label='No matching ARM input')
            if d['best_metrics']['consistent_source_count']:
                out=arm.values[d['best_output_index']]
                p=sorted(((ao[q.candidate].center_ns-origin)*1e-9,q.dealiased_cfo_hz)
                    for q in out.points if ref.start_ns<=ao[q.candidate].center_ns<=ref.end_ns)
                tt,ff=np.array(p).T
                spacing=11.2e9/ref.lane.rf_hz/4.4e-6
                ff+=np.round((np.interp(tt,t,f)-ff)/spacing)*spacing
                ax.plot(tt,ff/1000,'.--',color='#d76a10',lw=.9,label='Best physical ARM output')
            ax.set_title(f'Ref #{ref.index} · Ch{ref.lane.channel}/RX{ref.lane.receiver} · {d["duration_s"]:.1f}s\n'
                         f'Input {d["input_consistent"]}/{d["reference_sources"]}; output {d["best_metrics"]["consistent_source_count"]}/{d["reference_sources"]}')
            ax.set_xlabel('Seconds from first projected observation')
            ax.set_ylabel('Alias-aligned CFO (kHz)')
            ax.grid(alpha=.2)
        axes[0,0].legend(fontsize=7)
        fig.suptitle(f'Remaining ARM/server discrepancies, page {page+1}/2 · ref #10 excluded\n'
                     'Sorted by duration; measured points, with lines to show membership')
        fig.savefig(DEST/f'remaining-{page+1}.png',dpi=150)
        fig.savefig(DEST/f'remaining-{page+1}.pdf')
        plt.close(fig)


if __name__=='__main__':
    main()
