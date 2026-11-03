"""Render independent-scan position evidence without hiding failed fits."""
import argparse
import json
from pathlib import Path

import numpy as np
from cohort import digest


def validate(summary):
    for arm in ('fitted-c','zero-c'):
        records=summary['arms'][arm]['records']
        if not records or any(np.linalg.norm(r['point_km'])>2.000001 for r in records):
            raise ValueError('missing or out-of-disk position evidence')
        if not all(np.isfinite(r['objective']) for r in records):
            raise ValueError('nonfinite position score')
    return summary


def scan_label(source):
    for parent in source.parents:
        if parent.name.startswith('seed-timing-'):
            return parent.parent.name
    return source.parents[3].name


def render(source,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    summary=validate(json.loads(source.read_text()))
    signature=summary['signature']
    for path,expected in signature['inputs']['sources'].items():
        if digest(Path(path).read_bytes())!=expected:
            raise ValueError('position input changed')
    output.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,2,figsize=(13,6.8),sharex=True,sharey=True)
    extent=max(abs(r['objective']-a['roof']['objective']) for a in summary['arms'].values() for r in a['records'])
    norm=TwoSlopeNorm(vmin=-max(extent,1e-6),vcenter=0.,vmax=max(extent,1e-6))
    metrics=[]
    for ax,arm in zip(axes,('fitted-c','zero-c')):
        result=summary['arms'][arm]
        records=result['records']
        for success,marker in ((True,'o'),(False,'x')):
            rows=[r for r in records if r['success']==success]
            if rows:
                artist=ax.scatter([r['point_km'][0] for r in rows],[r['point_km'][1] for r in rows],
                                  c=[r['objective']-result['roof']['objective'] for r in rows],cmap='RdBu_r',norm=norm,
                                  marker=marker,s=35,label='Converged' if success else 'Not converged')
        best=result['best_found']
        ax.plot(*best['point_km'],marker='*',ms=16,mfc='none',mec='black',label='Lowest saved score')
        ax.plot(0,0,'k+',ms=15,mew=2,label='Known roof')
        ax.add_patch(plt.Circle((0,0),2,fill=False,ls=':',color='#777777'))
        ax.set(xlim=(-2.15,2.15),ylim=(-2.15,2.15),aspect='equal',xlabel='East of roof (km)',ylabel='North of roof (km)',
               title=f'{arm} · best saved {result["radius_m"]:.0f} m\nConverged: {best["success"]}; boundary: {result["boundary"]}')
        ax.grid(alpha=.15)
        ax.legend(fontsize=8,loc='upper right')
        metrics.append(dict(arm=arm,error_m=result['radius_m'],best_converged=best['success'],
                            roof_converged=result['roof']['success'],boundary=result['boundary'],
                            score_change=best['objective']-result['roof']['objective'],
                            failed_points=sum(not r['success'] for r in records)))
    fig.subplots_adjust(bottom=.19,top=.82,left=.07,right=.87,wspace=.25)
    cax=fig.add_axes([.90,.24,.015,.52])
    fig.colorbar(artist,cax=cax,label='Score − rechecked roof score (lower is better)')
    name=scan_label(source)
    optimizer=next((p.name for p in source.parents if p.name.startswith(('position-fisher-','position-polish-','position-direct-'))),'position search')
    warning=' · CALIBRATION WARNING' if signature['inputs'].get('calibration_warnings') else ''
    fig.suptitle(f'{name} · independent 2 km position search{warning}\n{optimizer} · fixed roof-conditioned associations; nuisance refitted',fontsize=14)
    fig.text(.5,.025,'Crosses remain visible: their scores are not certified profile minima. Star = best saved score, not a global optimum.\nAt fixed locations, convergence checks nuisance parameters only. Different parameter basins remain possible.\nBoth RF arms share observations, satellite bank, priors and search budgets. Known-roof selections are diagnostic.',ha='center',fontsize=10)
    stem=source.parent.name
    # Preserve older optimizer evidence when both are rendered for one scan.
    for parent in source.parents:
        if parent.name.startswith(('position-fisher-','position-polish-')):
            stem+=f'-{parent.name}'
            break
    fig.savefig(output/f'position-{stem}.png',dpi=150)
    plt.close(fig)
    (output/f'position-{stem}.json').write_text(json.dumps(dict(metrics=metrics,optimizer=optimizer,
            calibration_warnings=signature['inputs'].get('calibration_warnings',[]),source=str(source),source_sha256=digest(source.read_bytes())),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('summary',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    render(a.summary,a.output)
