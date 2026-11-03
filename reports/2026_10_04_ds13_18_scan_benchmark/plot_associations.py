"""Paired all-window/orbit and unassociated-window diagnostic plots."""
import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from cohort import ROOT, digest
from discovery import ARMS, FoldCalibration
from refinement import ALIAS_HZ


def presentation():
    path=ROOT/'src/leo/presentation/orbit_plot.py'
    name='_benchmark_orbit_plot'
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def display_rows(data, assignments):
    """Exactly one point/window: selected alternative, otherwise top margin."""
    by_group={int(data.group[a['row_index']]):int(a['row_index']) for a in assignments}
    if len(by_group)!=len(assignments):
        raise ValueError('duplicate assigned windows')
    rows=[by_group.get(int(data.group[r]),int(r)) for r in np.flatnonzero(data.top_mask)]
    if len(set(data.group[rows]))!=len(rows):
        raise ValueError('display double-counted a window')
    return np.array(rows,int)


def dense_curve(cal, arm, satellite_index, offset, rx, rf):
    from prediction_jacobian import paired_prediction_jacobian
    times=np.arange(0.,300.001,.25)
    output=np.full(len(times),np.nan)
    for fold,(_,template,models) in enumerate(cal.parts):
        mask=(np.floor(times/10).astype(int)%5)==fold
        d=copy.copy(template)
        d.times=times[mask]
        d.receiver=np.full(sum(mask),rx,int)
        d.rf=np.full(sum(mask),rf)
        params,common,_=models[arm]
        if abs(common+offset)>20:
            continue
        trial=params.copy()
        trial[6+satellite_index]=common+offset
        pp,vv,_=paired_prediction_jacobian(d,trial,np.arange(sum(mask)),np.full(sum(mask),satellite_index))
        source=cal.fold_records[fold]
        pp+=source['arms'][arm]['coefficient']*(rf-source['rf_center_hz'])/1e9
        pp+=np.interp(d.times,source['spline_nodes_s'],source['correction_knots_hz'][rx])
        pp[~vv]=np.nan
        output[mask]=pp
    return times,output


def render(directory, selection, output):
    cal=FoldCalibration(directory,permit_warning=True)
    cal.fold_records=[json.loads((directory/'calibration-v2'/f'fold-{i}.json').read_text()) for i in range(5)]
    d=cal.data
    saved=json.loads(selection.read_text())
    pool=json.loads((directory/'discovery/candidate-pool.json').read_text())
    if saved['signature']['pool_sha256']!=digest((directory/'discovery/candidate-pool.json').read_bytes()):
        raise ValueError('selection/pool binding mismatch')
    output.mkdir(parents=True,exist_ok=True)
    module=presentation()
    receipt={}
    for arm in ARMS:
        for method,result in saved['arms'][arm].items():
            final=result['final']
            assignments=final['assignments']
            assigned={a['row_index']:a['catalog_number'] for a in assignments}
            rows=display_rows(d,assignments)
            modes={r['catalog_number']:pool['arms'][arm][r['mode_index']] for r in final['selected']}
            lanes=[]
            for rx in (0,1):
                for ch in sorted(set(d.channel.tolist())):
                    lane=rows[(d.receiver[rows]==rx)&(d.channel[rows]==ch)]
                    if not len(lane):
                        continue
                    frequencies=np.unique(d.rf[lane])
                    if len(frequencies)!=1:
                        raise ValueError('channel has multiple RF centers; split lane first')
                    peaks=tuple(module.OrbitPeak(str(d.original_rows[r]),float(d.times[r]),float(d.measured[r]),
                                                str(assigned[r]) if r in assigned else None) for r in lane)
                    curves=[]
                    for number in sorted({assigned[r] for r in lane if r in assigned}):
                        mode=modes[number]
                        t,p=dense_curve(cal,arm,mode['satellite_index'],mode['offset_s'],rx,frequencies[0])
                        curves.append(module.OrbitCurve(str(number),tuple(t),tuple(p)))
                    lanes.append(module.OrbitLane(f'RX{rx}',f'CH{ch}',peaks,tuple(curves)))
            figure=module.make_orbit_plot(lanes,title=f'{directory.name} · {d.session_id}\n{method} · {arm}',
                alias_period_hz=ALIAS_HZ,time_limits_s=(0,300),observation_label='passing windows',
                subtitle='Conditional known-roof search; fold-specific RX/RF corrections included in curves.\nOne point/window: selected candidate, otherwise highest refined GLRT margin.'
                         + ('\nWARNING: calibration optimizer not converged in '+str(len(cal.warnings))+' folds.' if cal.warnings else ''))
            path=output/f'{method}-{arm}-orbits.png'
            figure.savefig(path,dpi=120)
            receipt[path.name]=digest(path.read_bytes())
            print('PLOT',path,flush=True)
    (output/'orbit-plot-receipt.json').write_text(json.dumps(dict(selection_sha256=digest(selection.read_bytes()),
        sources=cal.sources,figures=receipt),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--selection',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    render(a.directory,a.selection or a.directory/'selection-p10-g600-t1.json',a.output)
