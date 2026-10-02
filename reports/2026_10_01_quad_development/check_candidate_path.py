"""Radio-only candidate-path ablations on the outlier-selected DS10 pair."""
import fcntl
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from candidate_path import solve,score
HERE=Path(__file__).resolve().parent


def main():
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        inputs={}
        def read(p):
            d=sealed(p);inputs[str(p)]=digest(p);return d
        exported=read(HERE/'pair-candidates-v1/candidates.json');verify_sources(exported['sources']);verify_sources(exported['inputs'])
        overlay=read(HERE/'quality-overlay-v4/overlay.json')
        old=read(HERE/'ds10-pair-inspection-v1/result.json')
        config=read(HERE/'ds10-pair-summary-v1.json')['public_projection']['config']
        allgroups={}
        for p in exported['candidates']:allgroups.setdefault(p['source_group_id'],[]).append(p)
        oldtracks=next(r for r in overlay['results'] if r['unit']=='DS10-F001')['tracks']
        records=[];fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True)
        for ax,track in zip(axes,old['tracks']):
            originals=next(t['points'] for t in oldtracks if t['track_id']==track['track_id'])
            origin=originals[0]['support_center_utc_ns'];groups=[];original_path=[]
            for original in originals:
                group=[]
                for p in sorted(allgroups[original['source_group_id']],key=lambda p:p['candidate_id']):
                    scale=config['canonical_rf_hz']/p['actual_rf_hz'];spacing=config['alias_spacing_hz']*scale
                    raw=p['measured_cfo_hz']*scale;alias=int(np.rint((raw-original['normalized_dealiased_cfo_hz'])/spacing))
                    group.append(dict(candidate_id=p['candidate_id'],source_group_id=p['source_group_id'],rank=p['candidate_rank'],margin=p['margin'],
                        t=(p['support_center_utc_ns']-origin)/1e9,y=raw-alias*spacing,alias=alias))
                selected=next(i for i,p in enumerate(group) if p['candidate_id']==original['candidate_id'])
                assert abs(group[selected]['y']-original['normalized_dealiased_cfo_hz'])<1e-7
                groups.append(group);original_path.append(selected)
            paths=dict(original=(original_path,100.,100.))
            for name,sigma,a in [('primary',100.,100.),('noise300',300.,100.),('acceleration300',100.,300.)]:
                path,value=solve(groups,sigma,a);paths[name]=(path,sigma,a)
            paths['margin_only']=([int(np.argmax([p['margin'] for p in g])) for g in groups],100.,100.)
            baseline=np.array([[g[k]['t'],g[k]['y']] for g,k in zip(groups,original_path)])
            polynomial=np.polyfit(baseline[:,0],baseline[:,1],2)
            for g in groups:ax.scatter([p['t'] for p in g],[p['y']-np.polyval(polynomial,p['t']) for p in g],color='grey',s=8,alpha=.25)
            results={}
            for name,(path,sigma,a) in paths.items():
                t=np.array([g[k]['t'] for g,k in zip(groups,path)]);y=np.array([g[k]['y'] for g,k in zip(groups,path)])
                coeff=np.polyfit(t,y,2);r=y-np.polyval(coeff,t)
                value=score(groups,path,sigma,a);baseline_value=score(groups,original_path,sigma,a)
                results[name]=dict(candidate_ids=[g[k]['candidate_id'] for g,k in zip(groups,path)],
                    source_group_ids=[g[k]['source_group_id'] for g,k in zip(groups,path)],times_s=t.tolist(),frequencies_hz=y.tolist(),
                    changed_candidates=sum(a!=b for a,b in zip(path,original_path)),quadratic_rms_hz=float(np.sqrt(np.mean(r*r))),
                    score=float(value) if np.isfinite(value) else None,original_score_same_rule=float(baseline_value) if np.isfinite(baseline_value) else None,
                    sigma_hz=sigma,acceleration_hz_s2=a)
                if name in ('original','primary','margin_only'):ax.plot(t,y-np.polyval(polynomial,t),'.-',label=name)
            ax.set_title(f"RX{track['receiver_id']} (selected outlier-pair study)");ax.set_ylabel('Hz minus original quadratic');ax.grid(alpha=.2);ax.legend()
            records.append(dict(receiver_id=track['receiver_id'],track_id=track['track_id'],groups=len(groups),results=results))
        axes[-1].set_xlabel('Seconds from first original candidate');fig.suptitle('Radio-only path search: grey dots are available candidates in the original coarse band')
        fig.tight_layout();fig.savefig(HERE/'candidate-path-v1.png',dpi=160);plt.close(fig)
        sources={str(HERE/name):digest(HERE/name) for name in ('check_candidate_path.py','candidate_path.py','test_candidate_path.py','CANDIDATE_PATH_PLAN.md')}
        verify_sources(inputs);verify_sources(sources)
        save(HERE/'candidate-path-v1.json',dict(tracks=records,inputs=inputs,sources=sources,
            qualification='Outlier-selected radio-only heuristic, conditional coarse band. No satellite prediction/GPS in path objective; smoother is not verified correct. No localization or frozen input changes.'))
        print([{k:v for k,v in r.items() if k!='results'}|dict(results={n:{k:v for k,v in a.items() if k not in ('candidate_ids','source_group_ids','times_s','frequencies_hz')} for n,a in r['results'].items()}) for r in records])


if __name__=='__main__':main()
