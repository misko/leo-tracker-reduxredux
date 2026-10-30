"""Compare original polynomial residuals with orbital residuals, without refits."""
import argparse,csv,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_omitted_predictive_recovery import target_diagnostic
from report_predictive_track_annotation import table


def original_polynomial(track):
    indices=track['indices'];times=np.asarray(track['times']);values=np.asarray(track['values'])
    if len(set(indices))!=len(indices) or len(indices)!=len(times) or len(times)!=len(values):
        raise ValueError('unique matching native indices required')
    byindex={v:k for k,v in enumerate(indices)};pred=np.empty(len(times));seen=set()
    for piece in track['pieces']:
        ids=piece['indices']
        if len(set(ids))!=len(ids) or seen.intersection(ids) or not set(ids)<=set(indices):
            raise ValueError('polynomial pieces overlap or leave native scope')
        seen.update(ids);sel=np.array([byindex[i] for i in ids]);scale=piece['time_scale_s']
        if scale<=0:raise ValueError('positive polynomial time scale required')
        pred[sel]=np.polynomial.legendre.legval((times[sel]-piece['reference_time_s'])/scale,piece['coefficients_hz'])
    if seen!=set(indices):raise ValueError('polynomial pieces do not cover all points')
    return values-pred


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};rows=[];data=[];gallery=[]
    def load(path):hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return read(path)
    execution=load(args.trials/'execution.json')
    for case in execution:
        if case['status']!='complete':raise ValueError('trial did not complete')
        tid=case['job']['track_id'];trial=args.trials/tid/'trial';pr=load(trial/'protocol.json')
        if pr.get('measurement_refinements') or pr.get('inactive_fragment_sources') or pr.get('graph_bundle_sources'):
            raise ValueError('original graph audit requires unchanged complete native targets')
        tracks=load(Path(pr['job']['root'])/pr['job']['case']/'tracks.json')
        result=load(trial/('target_0.json' if case['shared_family'] else 'new_family.json'))
        if len(pr['targets'])!=1:raise ValueError('one complete target per inventory trial required')
        target=pr['targets'][0];track=tracks[target['track_index']]
        if track['observation_ids']!=target['observation_ids']:raise ValueError('target identity or order differs')
        residual=original_polynomial(track);rms=float(np.sqrt(np.mean(residual**2)))
        if not np.isclose(rms,track['residual_rms_hz'],atol=1e-5,rtol=1e-6):raise ValueError('original polynomial did not replay')
        fig,axes=plt.subplots(1,2,figsize=(13,4),layout='constrained')
        for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
            diag=target_diagnostic(result['arms'][arm]);orbital=np.asarray(diag['residual_hz'])
            if not np.array_equal(diag['times_s'],track['times']):raise ValueError('orbital target times differ')
            gap=orbital-residual
            row=dict(scan=pr['job']['label'],track_id=tid,component=track['key'],arm=arm,points=len(residual),
                pieces=len(track['pieces']),degrees=' '.join(str(p['degree']) for p in track['pieces']),
                graph_quality=track['quality_status'],polynomial_RMS_hz=rms,orbit_RMS_hz=float(np.sqrt(np.mean(orbital**2))),
                polynomial_orbit_correlation=float(np.corrcoef(residual,orbital)[0,1]),model_gap_centered_RMS_hz=float(np.std(gap)))
            rows.append(row);data.append(dict(**row,times_s=track['times'],polynomial_residual_hz=residual,orbital_residual_hz=orbital,model_gap_hz=gap))
            ax.plot(track['times'],residual,'.-',lw=.6,label='Original polynomial residual')
            ax.plot(track['times'],orbital,'.-',lw=.6,label='Satellite residual')
            ax.plot(track['times'],gap,'-',lw=1,label='Difference between predictions')
            ax.axhline(0,c='k',lw=.5);ax.grid(alpha=.2);ax.legend(fontsize=7)
            ax.set(title=pr['job']['label']+' / '+arm,xlabel='Scan time (s)',ylabel='Residual (Hz)')
        fig.suptitle(track['key']+' / '+track['quality_status']);fig.savefig(out/'figures'/f'{tid}.png',dpi=140);plt.close(fig)
        gallery.append(f"![{pr['job']['label']}](figures/{tid}.png)")
    with (out/'metrics.csv').open('x') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    write(out/'result.json',dict(rows=data,source_hashes=hashes,original_polynomials_replayed=True,refitted=False,acceptance_changed=False,
        caveat='In-sample descriptive decomposition; a flexible polynomial can absorb model error or a bad join. No identity correctness or independent noise calibration inferred.'))
    (out/'README.md').write_text('# Are new recovery failures already present in the graph measurements?\n\n'
        'All supported identities in the third reassessment batch were audited, including every failed inclusion. The original graph polynomials are replayed on their exact point sets without refitting or deleting points. Differences between polynomial and satellite predictions help prioritize measurement versus physical-model investigations; they do not prove either cause.\n\n'
        +table([r for r in rows if r['arm']=='fitted_c'],['scan','component','points','pieces','degrees','graph_quality','polynomial_RMS_hz','orbit_RMS_hz','polynomial_orbit_correlation','model_gap_centered_RMS_hz'])
        +'\n\n'+'\n\n'.join(gallery)+'\n\nThe polynomial fits use these same observations and can absorb smooth receiver/orbit mismatch or source mixing. A low polynomial residual is not independent validation, and a multi-piece graph is not proof of an incorrect join. Every arm and source hash is preserved in [result.json](result.json). This audit changes no position, model or acceptance decision.\n')
    print('audited',len(execution),'complete targets',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('trials','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
