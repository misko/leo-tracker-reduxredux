"""Archive adapter for the pure orbit-plot module; no new fitting or selection.

Use the saved top-response greedy+replacement memberships and saved calibration.
These curves retain the historical restaurant reference coordinates; plotting
does not silently change them to the capture-bound roof. Geometry auditing is
separate. This adapter is analysis-specific, not a production storage interface.
"""
import copy
import json
import sys
from pathlib import Path

import numpy as np

REPO=Path(__file__).resolve().parents[2]
BULK=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
sys.path[:0]=[str(REPO/'src'),str(BULK)]
from replay import NAMESPACE,ROOT,digest,corrected_prediction
from gap_allfold_summary import location
from leo.presentation.orbit_plot import OrbitPeak,OrbitCurve,OrbitLane,make_orbit_plot

OUT=Path(__file__).resolve().parent
ALIAS=1/4.4e-6


def load(scan):
    import greedy_pool_two_scans as g
    g.SCAN=scan
    if scan=='A':
        from top_one_scan_A import TopOneCalibration
        cal=TopOneCalibration();folder=BULK/'full-scan-A-refinement/top-one'
    else:
        from position_top_2km_inputs import calibration
        cal=calibration()();folder=BULK/'position-top-2km/B-top'
    source=folder/'fitted-c.json'
    result=json.loads(source.read_text())
    return cal,result,source


class DenseModel:
    def __init__(self,cal,result,scan):
        self.cal=cal;self.scan=scan
        self.selected={r['catalog_number']:r['offset_s'] for r in result['final']['selected']}
        self.number_to_index={int(n):i for i,n in enumerate(cal.d.numbers)}
        self.folds=[];self.sources={}
        for fold,(_,models) in enumerate(cal.parts):
            sp=location(fold,'corrected')/'training-union'/f'fold-{fold}'/f'{scan}.json'
            saved=json.loads(sp.read_text())
            cp=BULK/('gap-discovery' if fold==4 else 'gap-campaign/discovery')/'fitted-c/training-calibration'/f'fold-{fold}'/f'{scan}.json'
            correction=json.loads(cp.read_text())['correction']
            rf=cal.data.rf[np.array(saved['original_test_rows'],int)]
            params=models['fitted-c'][0].copy()
            for number,offset in self.selected.items():
                params[6+self.number_to_index[number]]=offset
            self.folds.append(dict(parameters=params,center=float(np.mean(np.unique(rf))),
                coefficient=float(saved['arms']['fitted-c']['coefficient'][0]),correction=correction))
            self.sources.update({str(p):digest(p) for p in (sp,cp)})

    def predict(self,times,rx,rf,numbers,fold):
        from prediction_plan import SharedPredictionPlan
        d=copy.copy(self.cal.data);d.times=np.array(times);d.receiver=np.array(rx,int);d.rf=np.array(rf)
        ids=np.array([self.number_to_index[n] for n in numbers],int)
        model=self.folds[fold];p,v,_=SharedPredictionPlan(d,ids).predict(model['parameters'])
        c=model['correction']
        p=corrected_prediction(p,d.times,d.receiver,c['nodes_s'],c['correction_knots_hz'])
        p=p.reshape(len(times),len(numbers))
        p+=(d.rf[:,None]-model['center'])/1e9*model['coefficient']
        return p,v.reshape(p.shape)


def build(scan):
    cal,result,source=load(scan);d=cal.d;model=DenseModel(cal,result,scan)
    aa=result['final']['assignments'];ownership={a['row_index']:a['catalog_number'] for a in aa}
    expected={a['row_index']:a['residual_hz'] for a in aa}
    assert len(ownership)==len(aa)==result['final']['assigned']
    assert len(set(d.group))==len(d.times)
    # Verify arbitrary-time adapter at the exact original observation times first.
    largest=0.
    for fold,(part,_) in enumerate(cal.parts):
        numbers=sorted(model.selected)
        p,v=model.predict(part.times,part.receiver,part.rf,numbers,fold)
        ni={n:i for i,n in enumerate(numbers)}
        for i,original in enumerate(part.original_rows):
            if int(original) not in ownership:continue
            col=ni[ownership[int(original)]]
            residual=(part.measured[i]-p[i,col]+ALIAS/2)%ALIAS-ALIAS/2
            largest=max(largest,abs(residual-expected[int(original)]))
            assert v[i,col]
    assert largest<1e-6,largest
    lanes=[];dense_times=np.arange(0.,300.0001,.25)
    # Last endpoint belongs to the preceding calibration block, not a new fold.
    block=np.minimum((dense_times/10).astype(int),29)
    folds=block%5
    for rx in (0,1):
        for ch in sorted(set(d.channel)):
            rows=np.flatnonzero((d.receiver==rx)&(d.channel==ch))
            peaks=tuple(OrbitPeak(str(int(d.original_rows[i])),float(d.times[i]),float(d.measured[i]),
                       str(ownership[int(d.original_rows[i])]) if int(d.original_rows[i]) in ownership else None)
                        for i in rows)
            numbers=sorted({ownership[int(d.original_rows[i])] for i in rows if int(d.original_rows[i]) in ownership})
            curves=[]
            if numbers:
                frequencies=np.unique(d.rf[rows]);assert len(frequencies)==1
                prediction=np.full((len(dense_times),len(numbers)),np.nan)
                for fold in range(5):
                    mask=folds==fold;times=dense_times[mask]
                    p,v=model.predict(times,np.full(len(times),rx),np.full(len(times),frequencies[0]),numbers,fold)
                    p[~v]=np.nan;prediction[mask]=p
                # Avoid implying continuity across changes in fold-specific calibration.
                boundaries=np.flatnonzero(np.diff(block)!=0)+1;prediction[boundaries]=np.nan
                curves=[OrbitCurve(str(n),tuple(dense_times),tuple(prediction[:,j])) for j,n in enumerate(numbers)]
            lanes.append(OrbitLane(f'RX{rx}',f'CH{int(ch)}',peaks,tuple(curves)))
    assert sum(len(l.peaks) for l in lanes)==len(d.times)
    assert sum(p.satellite_id is not None for l in lanes for p in l.peaks)==result['final']['assigned']
    outputs=[]
    for suffix,chosen in [('all',lanes),('RX0',[l for l in lanes if l.receiver=='RX0']),('RX1',[l for l in lanes if l.receiver=='RX1'])]:
        figure=make_orbit_plot(chosen,title=f'DS13 scan {scan} · orbit plot · {suffix}',
            alias_period_hz=ALIAS,time_limits_s=(0,300),lane_height_inches=2.1,
            subtitle='Refined highest-response candidate/window · saved greedy + replacement · fitted c\n'
                     'Calibrated orbit curves retain the historical fit reference; no refitting or reassignment.')
        path=OUT/f'orbit-{scan}-{suffix}.png';figure.savefig(path,dpi=145);figure.clear();outputs.append(str(path))
    receipt=dict(scan=scan,assigned=len(aa),total=len(d.times),unassociated=len(d.times)-len(aa),
        observation_definition='One highest refined GLRT response per receiver/channel/20 ms probe from the original passing cohort.',
        model_reference_lat_lon=[37.858988,-122.478103],
        coordinate_warning='Historical fit reference is a display preset, NOT the capture-bound operator roof. Curves intentionally unchanged.',
        maximum_reproduced_residual_error_hz=largest,outputs=outputs,
        lanes=[dict(receiver=l.receiver,channel=l.channel,total=len(l.peaks),associated=sum(p.satellite_id is not None for p in l.peaks),
                    unassociated=sum(p.satellite_id is None for p in l.peaks)) for l in lanes],
        sources={**cal.sources,**model.sources,str(source):digest(source),str(Path(__file__)):digest(Path(__file__)),
                 str(REPO/'src/leo/presentation/orbit_plot.py'):digest(REPO/'src/leo/presentation/orbit_plot.py')})
    (OUT/f'orbit-{scan}-receipt.json').write_text(json.dumps(receipt,indent=2))
    print(scan,receipt['assigned'],receipt['total'],receipt['unassociated'],'residual error',largest,flush=True)


if __name__=='__main__':
    for scan in ('A','B'):build(scan)
