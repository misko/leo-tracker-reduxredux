"""Replay existing rejected trials and inspect simultaneous residual witnesses.

No optimization or new associations; nearest pairs are descriptive only.
"""
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from leo.analysis.research.retained_track_likelihood import profile


def unique_time_pairs(witness_times,target_times,maximum_separation_s=.5):
    """Greedy closest pairs, with neither observation reused within a track."""
    distance=abs(np.asarray(witness_times)[:,None]-np.asarray(target_times)[None,:])
    eligible=np.argwhere(distance<=maximum_separation_s)
    ordered=sorted((float(distance[i,j]),int(i),int(j)) for i,j in eligible)
    used_witness=set();used_target=set();pairs=[]
    for _,i,j in ordered:
        if i in used_witness or j in used_target:continue
        used_witness.add(i);used_target.add(j);pairs.append((i,j))
    return sorted(pairs)


def run(base):
    records=[]
    fig,axes=plt.subplots(3,1,figsize=(15,11),layout='constrained')
    for ax,path in zip(axes,sorted(base.glob('*/result.json'))[1:4],strict=True):
        diag=read(path);row=diag['row'];saved=diag['actual_pipeline_trial'];source=read(saved['path'])
        d=context(read(row['inventory_path']));scan=d['scan'];arms={}
        for arm,v in source['arms'].items():
            kwargs={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            p=make_event_problem(scan,d['node'],d['keep'],arm,np.array(v['phase_reference']),d['powers'],d['means'],d['model'],v['events'],**kwargs)
            entries=d['entries']+source['target_entries'];attach_event_predictive(p,entries,d['powers']);cached(p)
            x=np.array(v['endpoint_east_north_km']);calc=p.calculate(x)
            difference=calc['negative_twice_elbo']-v['negative_twice_elbo']
            assert abs(difference)<1e-5,(row['case'],arm,difference)
            target=v['target_diagnostics'][0];tt=np.array(target['times_s']);tr=np.array(target['residual_hz'])
            target_ids=np.array(scan.tracks[row['track_index']]['observation_ids'])
            assert len(target_ids)==len(tt)
            curves=[]
            for r,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                if not p.keep[sl].any():continue
                track=scan.tracks[i];use=p.keep[sl]
                curves.append((r,i,track['times'][use],calc['conditional_residual_hz'][sl][use],'curved_conditional',np.array(track['observation_ids'])[use]))
            for entry,sl in zip(p.linear_entries,p.linear_slices,strict=True):
                i=entry['track_index'];track=scan.tracks[i];raw=calc['linear_raw_prediction_residual_hz'][sl]
                terms=profile(raw,np.zeros(len(raw)),*scan.white[i],bias_sigma=300.)
                residual=terms['residual'][0]
                if entry['component']==row['component']:
                    assert np.max(abs(residual-tr))<1e-5
                curves.append((entry,i,track['times'],residual,'predictive_constant_profile',np.array(track['observation_ids'])))
            witnesses=[]
            for r,i,t,residual,kind,ids in curves:
                track=scan.tracks[i]
                if track['key']==row['component']:continue
                norad=int(r.get('norad',r.get('candidate_norad')))
                same_family=norad==target['norad'];same_rx=track['receiver']==row['receiver']
                if not same_family and not same_rx:continue
                mask=(t>=tt.min())&(t<=tt.max())
                if mask.sum()<3:continue
                t=t[mask];residual=residual[mask];ids=ids[mask]
                unique=unique_time_pairs(t,tt)
                pairs=[];corr=None
                wi=np.array([a for a,b in unique],dtype=int);ti=np.array([b for a,b in unique],dtype=int)
                if len(unique)>=8:
                    normalized=residual[wi]/(track['rf_hz']/11.5e9)
                    target_normalized=tr[ti]/(row['rf_hz']/11.5e9)
                    corr=float(np.corrcoef(normalized,target_normalized)[0,1])
                pairs=[dict(witness_observation_id=str(ids[a]),target_observation_id=str(target_ids[b]),
                            witness_time_s=float(t[a]),target_time_s=float(tt[b]),
                            witness_residual_hz=float(residual[a]),target_residual_hz=float(tr[b])) for a,b in unique]
                assert len(pairs)<=len(target_ids)
                assert len({p['witness_observation_id'] for p in pairs})==len(pairs)
                assert len({p['target_observation_id'] for p in pairs})==len(pairs)
                witnesses.append(dict(component=track['key'],norad=norad,receiver=track['receiver'],channel=track['channel'],
                    same_family=same_family,same_receiver=same_rx,kind=kind,overlap_points=len(t),times_s=t,residual_hz=residual,
                    nearest_pairs_within_0_5s=len(pairs),descriptive_pair_correlation=corr,nearest_pairs=pairs,
                    causal_attribution=False))
            arms[arm]=dict(objective_replay_difference=difference,target=target,witnesses=witnesses)
            if arm=='fitted_c':
                ax.plot(tt,tr,'k.-',ms=3,lw=1.2,label=f"Target {target['norad']} RX{row['receiver']} CH{row['channel']}")
                selected=[]
                for same in (True,False):
                    selected+=sorted([w for w in witnesses if w['same_family']==same],key=lambda w:-w['overlap_points'])[:3]
                for w in selected:
                    label=f"{'Same family' if w['same_family'] else 'Other family, same RX'} {w['norad']} RX{w['receiver']} CH{w['channel']} ({w['overlap_points']} pts)"
                    ax.plot(w['times_s'],w['residual_hz'],'.-',ms=3,lw=.8,alpha=.8,label=label)
                ax.set_title(row['case']+' — existing rejected trial, fitted_c; same conditioned model, no refit')
                ax.axhline(0,c='.5',lw=.6);ax.set_xlabel('Device time (s)');ax.set_ylabel('Residual (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2)
        records.append(dict(case=row['case'],source=saved['path'],arms=arms))
        print(row['case'],'replayed witnesses',[(a,len(v['witnesses'])) for a,v in arms.items()],flush=True)
    fig.suptitle('Simultaneous retained evidence for three rejected shared-satellite trials\nDescriptive residual witnesses; overlap/correlation alone does not identify receiver, orbit, or target-specific cause')
    fig.savefig(base/'witnesses-unique.png',dpi=150);fig.savefig(base/'witnesses-unique.pdf');plt.close(fig)
    write(base/'witnesses-unique.json',dict(records=records,no_refits=True,no_new_associations=True,
        supersedes='witnesses.json (previous nearest-neighbor statistics reused target observations)',
        matching='Greedy closest-time one-to-one pairs within 0.5 s; each original ID used at most once per witness track; at least eight pairs for descriptive correlation; postselected, no inferential p-values or independent validation claim.',
        caution='Witness overlap alone does not attribute discrepancies. Curved conditional residuals and predictive profiled residuals preserve their original likelihood roles.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);run(p.parse_args().base)
