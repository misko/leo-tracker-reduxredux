"""Geographic reporting only, after all held-family fits/scores are sealed."""
from pathlib import Path
import csv
import hashlib
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OLD = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
TRUTH = np.array([37.849061591561885, -122.48574968092912])
CENTER = np.array([37.906, -122.545])
CASES = ('DS24-0017','DS24-0095')
ARMS = ('c0','fitted_c')


def read(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def coordinates(x):
    return np.array([CENTER[0]+x[1]/111., CENTER[1]+x[0]/(111.32*np.cos(np.radians(CENTER[0])))])


def error_km(latlon):
    a,b = np.radians(np.array([latlon,TRUTH]))
    h = np.sin((a[0]-b[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((a[1]-b[1])/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(h,0,1))))


def main():
    out = HERE/'report'; out.mkdir(exist_ok=True)
    assert read(HERE/'audit/artifact_audit.json')['status'] == 'passed'
    rows = []; bindings = {}
    for case in CASES:
        previous = OLD/'evaluation/models/receiver_fast_rx1_rf50'/f'{case}.json'
        saved = read(previous); bindings[str(previous)] = digest(previous)
        for arm in ARMS:
            for model, r in [('baseline',saved['baseline'][arm]),('sharedRF50',saved['arms'][arm])]:
                np.testing.assert_allclose(coordinates(r['endpoint_east_north_km']),r['endpoint_latlon'],atol=1e-12,rtol=0)
                rows.append(dict(case=case,arm=arm,scope='original_full_data',fold=-1,model=model,
                    east_km=r['endpoint_east_north_km'][0],north_km=r['endpoint_east_north_km'][1],
                    error_km=error_km(r['endpoint_latlon']),phase_change_s=r.get('final_phase_change_s')))
        for fold in range(3):
            path=HERE/'heldout/results'/f'{case}_fold{fold}.json'
            raw=read(path);bindings[str(path)]=digest(path)
            assert raw['status']=='complete' and raw['GPS_used'] is False
            for arm in ARMS:
                for model,r in raw['arms'][arm]['fits'].items():
                    x=np.array(r['endpoint_east_north_km'])
                    rows.append(dict(case=case,arm=arm,scope='train_only_fold',fold=fold,model=model,
                        east_km=x[0],north_km=x[1],error_km=error_km(coordinates(x)),
                        phase_change_s=r['final_phase_change_s']))
    with (out/'position_errors.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    truth_xy=np.array([(TRUTH[1]-CENTER[1])*111.32*np.cos(np.radians(CENTER[0])),(TRUTH[0]-CENTER[0])*111.])
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(11,9),sharex=True,sharey=True)
    colors=['#0072B2','#D55E00','#009E73']
    for i,case in enumerate(CASES):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j]
            for fold in [-1,0,1,2]:
                pair={r['model']:r for r in rows if (r['case'],r['arm'],r['fold'])==(case,arm,fold)}
                a=np.array([pair['baseline']['east_km'],pair['baseline']['north_km']])-truth_xy
                b=np.array([pair['sharedRF50']['east_km'],pair['sharedRF50']['north_km']])-truth_xy
                color='#222222' if fold==-1 else colors[fold]
                ax.annotate('',xy=b,xytext=a,arrowprops=dict(arrowstyle='->',color=color,lw=2 if fold==-1 else 1.2))
                ax.scatter(*a,color=color,marker='o',s=48,facecolors='none')
                ax.scatter(*b,color=color,marker='^',s=48,label='Full data' if fold==-1 else f'Family fold {fold+1}')
            ax.scatter(0,0,color='black',marker='*',s=120,label='Evaluation site')
            ax.axhline(0,color='gray',lw=.5);ax.axvline(0,color='gray',lw=.5);ax.grid(alpha=.2)
            ax.set_title(f'{case} · '+('c = 0' if arm=='c0' else 'Fitted c'))
            ax.set_aspect('equal',adjustable='box')
            ax.set(xlim=(-2.6,2.6),ylim=(-3.3,1.9))
            if i==1:ax.set_xlabel('East of evaluation site (km)')
            if j==0:ax.set_ylabel('North of evaluation site (km)')
    axes[0,0].legend(fontsize=8,loc='lower right')
    axes[1,1].text(.02,.02,'Fold 3 baseline: phase change exceeds criterion',transform=axes[1,1].transAxes,fontsize=8)
    fig.suptitle('Position changes: baseline ○ → shared RX1 △\nArrows join estimates; they are not descent trajectories. GPS used only for this report.')
    fig.tight_layout();fig.savefig(out/'position_changes.png',dpi=180);plt.close(fig)
    result=dict(rows=rows,evaluation_only_GPS=TRUTH.tolist(),source_bindings=bindings,
        source_sha256=digest(Path(__file__)),no_new_estimator_or_policy=True,
        caveat='Post-hoc two-case diagnosis; train-only folds overlap in training data and are not new independent scans')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([r for r in rows if r['scope']=='original_full_data'],indent=2))


if __name__=='__main__':main()
