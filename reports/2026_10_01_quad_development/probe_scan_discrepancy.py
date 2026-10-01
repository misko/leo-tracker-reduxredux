"""Reference-free sensitivity of three existing scan-tension quadratic surrogates."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scan_discrepancy_quadratic import solve_discrepancy

HERE=Path(__file__).resolve().parent
SCALES=(0.,.1,.3,1.,3.)  # Diagnostic sensitivity grid; no fitted or selected width.


def digest(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output=HERE/'scan-discrepancy-quadratic-v1.json'
    if output.exists():raise FileExistsError(output)
    inputs={};rows=[]
    for ds in ('DS9','DS10','DS11'):
        directory=HERE/'independent-v2'/(ds+'-B01')
        path=directory/'scan-tension.json'
        assert digest(path)==path.with_suffix('.sha256').read_text().strip()
        data=json.loads(path.read_text());inputs[str(path)]=digest(path)
        for p,h in ((directory/'evaluation.json',data['evaluation_sha256']),
                    (directory/(ds+'-B01-Q.json'),data['receipt_sha256']),
                    (HERE/'diagnose_scan_tension.py',data['source_sha256'])):
            assert digest(p)==h;inputs[str(p)]=h
        h=np.array([r['profiled_irls_information'] for r in data['rows']])
        g=np.array([r['spatial_gradient_per_km'] for r in data['rows']])
        zero=solve_discrepancy(h,g,0.)
        for scale in SCALES:
            fit=solve_discrepancy(h,g,scale)
            rows.append(dict(dataset=ds,sigma_km=scale,
                center_displacement_m=(1000*fit['center']).tolist(),
                displacement_from_zero_m=float(1000*np.linalg.norm(fit['center']-zero['center'])),
                offsets_m=(1000*fit['offsets']).tolist(),
                max_offset_m=float(1000*np.linalg.norm(fit['offsets'],axis=1).max()),
                information_eigenvalues_per_km2=np.linalg.eigvalsh(fit['information']).tolist(),
                local_minima_m=(1000*fit['local_minima']).tolist()))
    sources={str(p):digest(p) for p in (Path(__file__).resolve(),HERE/'scan_discrepancy_quadratic.py',HERE/'test_scan_discrepancy_quadratic.py')}
    result=dict(rows=rows,inputs=inputs,sources=sources,
        qualification='No geographic scoring and no raw-data refit. Exact algebra on existing local IRLS Schur surrogates at three first-block quad solutions. Spatial gradients approximate nuisance-profile gradients only near nuisance stationarity. Not true Hessians, calibrated covariances, single-scan global modes, or a selected discrepancy scale.')
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    for ds in ('DS9','DS10','DS11'):
        r=[x for x in rows if x['dataset']==ds]
        axes[0].plot(SCALES,[x['displacement_from_zero_m'] for x in r],'-o',label=ds)
        axes[1].plot(SCALES,[x['max_offset_m'] for x in r],'-o',label=ds)
    for ax in axes:ax.set_xlabel('Assumed discrepancy standard deviation (km)');ax.legend();ax.grid(alpha=.2)
    axes[0].set_ylabel('Shared-location shift from zero-scale surrogate (m)')
    axes[1].set_ylabel('Largest per-scan offset (m)')
    fig.suptitle('Local quadratic sensitivity only: no geographic scoring or raw-data fit')
    fig.savefig(output.with_suffix('.png'),dpi=160)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
