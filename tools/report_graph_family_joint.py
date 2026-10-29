"""Document a matched same-satellite joint fit and its remaining gate failures."""
import argparse,csv,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_inventory_experiments import error


def run(args):
    out=args.report;sources={};evidence={}
    def load(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    protocol=load(args.study/'protocol.json');terminal=load(args.study/'terminal.json')
    if terminal['status']!='complete':raise ValueError('joint experiment incomplete')
    combined=load(args.study/'fit/combined.json');control=load(args.study/'fit/control.json');load(args.study/'fit/protocol.json')
    singles=[];rows=[];replay=[]
    for tid in protocol['track_ids']:
        r=load(args.singles/tid/'target_0.json');old=load(args.singles/tid/'control.json');singles.append(r)
        for arm in ('c0','fitted_c'):
            delta=abs(old['arms'][arm]['negative_twice_elbo']-control['arms'][arm]['negative_twice_elbo'])
            if delta>1e-5:raise ValueError('family control replay mismatch')
            replay.append(dict(track_id=tid,arm=arm,objective_delta=delta))
    for name,r in [('first_only',singles[0]),('second_only',singles[1]),('joint',combined)]:
        for arm,v in r['arms'].items():
            for t in v['targets']:
                g=t['gate'];cg=g['conditional_residual_gate']
                rows.append(dict(variant=name,arm=arm,component=t['component'],paired_pass=r['paired_valid'],
                    target_qualified=g['compatible'],conditional_residual_pass=cg['compatible'],conditional_rms_hz=cg['rms_hz'],
                    profile_rms_hz=g['profile_rms_hz'],error_km=error(v),added=v['added_points'],lost=v['lost_points']))
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,(single,entry) in enumerate(zip(singles,combined['target_entries'],strict=True)):
        component=entry['component'];a=single['arms']['fitted_c']['targets'][0]
        b=next(t for t in combined['arms']['fitted_c']['targets'] if t['component']==component)
        axs[0,col].scatter(b['times_s'],np.array(b['CFO_hz'])/1000,s=10,c='black',label='GLRT track CFO')
        for d,label,color in [(a,'Individual fit','#cc3311'),(b,'Joint family fit','#4477aa')]:
            axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,c=color,label=label)
            axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=3,c=color,label=label)
        axs[0,col].set(title=f"RX{entry['receiver']} CH{entry['channel']}",ylabel='CFO (kHz)')
        axs[1,col].set(xlabel='Scan time (s)',ylabel='Conditional residual (Hz)');axs[1,col].axhline(0,c='black',lw=.5)
        for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('AUTO-0c81fa24 / NORAD 59748 — separately nominated curves, jointly refitted\nFitted-c shown; both c arms retained in the table')
    fig.savefig(out/'figures/family_59748_joint.png',dpi=140);plt.close(fig)
    for name,data in [('graph_family_joint.csv',rows),('graph_family_control_replay.csv',replay)]:
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator='\n');w.writeheader();w.writerows(data)
    write(out/'graph_family_sources.json',sources)
    with gzip.open(out/'graph_family_evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    (out/'graph_family_joint.md').write_text(f'''# Can another receiver supply missing orbital support?

The graph gate audit found three targets rejected solely by the multiple-qualified-owner requirement. One has another independently nominated graph curve for the same satellite in the existing assessed ledger: **AUTO-0c81fa24, NORAD 59748**, RX1 CH4 and RX2 CH2. The other curve had failed residual checks alone. This is the only such same-family sibling identified for the three owner-gated targets in this batch; it is not an exhaustive search of every raw GLRT point.

Fit the two together with their separately nominated IDs and aliases, shared satellite parameters, original receiver priors and original gates. The experiment changes only inclusion: no new nuisance term, gate relaxation, future TLE, or GPS-assisted candidate selection. Both c arms start from the same regional center with five phase-refresh rounds ×48 iterations. The matched controls replay exactly within 1e-5 objective units.

{table(rows,['variant','arm','component','paired_pass','target_qualified','conditional_residual_pass','conditional_rms_hz','error_km','added','lost'])}

![Individual and combined fits](figures/family_59748_joint.png)

**The combined fit remains rejected.** RX1 CH4 retains structured conditional residuals around 140 Hz RMS; RX2 CH2 is around 19 Hz and passes its conditional residual screen, but is still unqualified overall. Merely adding a second receiver curve is insufficient when that curve itself fails the residual checks. The 127 proposed points are therefore not counted as recovered. The failure is consistent with the original owner rule requiring qualified, independent evidence rather than just two labels.

The next useful test is whether an independently supported receiver correction can repair the RX1 discrepancy, or whether the RX1 assignment/track is wrong. That correction must be learned from other satellite families and tested with target-family feedback blocked. We should not make the inconsistent RX1 curve an automatic witness for RX2. [Both-arm numerical results](graph_family_joint.csv), [control replays](graph_family_control_replay.csv), and [source hashes](graph_family_sources.json) preserve this unsuccessful experiment. No production change is made.
''')
    print(json.dumps(dict(paired_pass=combined['paired_valid'],maximum_control_replay_delta=max(r['objective_delta'] for r in replay)),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['study','singles','report']:p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
