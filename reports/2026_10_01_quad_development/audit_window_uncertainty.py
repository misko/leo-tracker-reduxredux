"""Local IRLS ellipse coverage diagnostic on a frozen baseline snapshot."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from regression_batch import digest, verify_sources
from leo.analysis.localization_uncertainty import profiled_position_covariance

HERE = Path(__file__).resolve().parent


def covariance(unit, receipt):
    binding, scans, columns, precision, ports = prepare_window(unit)
    assert binding == receipt['binding']
    assert precision.tolist() == receipt['precision']
    assert [c.tolist() for c in columns] == receipt['columns']
    assert receipt['inputs'] == {k:v for scan,_,_ in scans for k,v in scan.inputs.items()}
    state = np.asarray(receipt['best']['mean'])
    assignments = [int(np.argmax(p.score_all(state))) for p in ports]
    assert assignments == receipt['best']['associations']
    active = {0,1,*np.flatnonzero(state).tolist()}; predictions = []
    for port,index in zip(ports,assignments):
        if index < port.candidate_count:
            prediction = port.predict_selected(state,index)
            assert prediction.eligible
            predictions.append((port,prediction))
            active.update(np.flatnonzero(np.any(prediction.jacobian != 0,axis=0)).tolist())
    active = np.array(sorted(active)); information = np.diag(precision[active])
    for port,prediction in predictions:
        residual = port.observation-prediction.mean
        solved = np.linalg.solve(prediction.covariance,residual)
        weight = (4+len(residual))/(4+float(residual@solved))
        jacobian = prediction.jacobian[:,active]
        information += weight*jacobian.T@np.linalg.solve(prediction.covariance,jacobian)
    return state[:2], profiled_position_covariance(information)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('snapshot',type=Path);parser.add_argument('--name',required=True)
    args=parser.parse_args();assert Path(args.name).name == args.name
    out=HERE/(args.name+'.json');assert not out.exists()
    snapshot=args.snapshot
    assert digest(snapshot) == snapshot.with_suffix('.sha256').read_text().strip()
    document=json.loads(snapshot.read_text());verify_sources(document['source_sha256'])
    rows=[]; bindings={str(snapshot.resolve()):digest(snapshot)}
    log=HERE/(args.name+'.progress.jsonl')
    with log.open('x') as progress:
        for original in document['rows']:
            if original.get('pending'): continue
            row=dict(unit=original['unit'],size=original['size'],block_id=original['block_id'],
                     scans=original['scans'],fit_accepted=original['accepted'],shape_available=False)
            if original['accepted']:
                path=HERE/'independent-v2'/original['block_id']/(original['unit']+'.json')
                assert digest(path) == original['receipt_sha256'] == path.with_suffix('.sha256').read_text().strip()
                receipt=json.loads(path.read_text());verify_sources(receipt['source_sha256']);verify_sources(receipt['inputs'])
                bindings[str(path)]=digest(path)
                try:
                    position,shape=covariance(original['unit'],receipt)
                    eigenvalues=np.linalg.eigvalsh(shape);assert np.all(eigenvalues>0)
                    row.update(shape_available=True,position_km=position.tolist(),covariance_km2=shape.tolist(),
                        nominal95_major_radius_m=float(1000*np.sqrt(5.991464547107979*eigenvalues[-1])))
                except (ValueError,AssertionError,np.linalg.LinAlgError) as error:
                    row['shape_failure']=type(error).__name__+': '+str(error)
            rows.append(row);progress.write(json.dumps(row)+'\n');progress.flush()
            print(json.dumps(dict(unit=row['unit'],shape_available=row['shape_available'])),flush=True)
    # All state-dependent geometry is fixed before accessing reference coordinates.
    reference_path=HERE/'reference-admission-v1.json'
    assert digest(reference_path) == reference_path.with_suffix('.sha256').read_text().strip()
    references=json.loads(reference_path.read_text());verify_sources(references['source_sha256'])
    reference={r['unit']:r['reference_latlon'] for r in references['rows']}
    helper=HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper)=='sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec=importlib.util.spec_from_file_location('offline_geo',helper);geo=importlib.util.module_from_spec(spec);spec.loader.exec_module(geo)
    for row in rows:
        if not row['shape_available']: continue
        location=reference[row['scans'][0]];assert all(reference[s]==location for s in row['scans'])
        lat1,lon1=map(math.radians,geo.CENTER);lat2,lon2=map(math.radians,location)
        bearing=math.atan2(math.sin(lon2-lon1)*math.cos(lat2),math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(lon2-lon1))
        distance=geo.distance_m(geo.CENTER,location)/1000
        reference_position=np.array([distance*math.sin(bearing),distance*math.cos(bearing)])
        assert geo.distance_m(geo.latlon_from_enu(*reference_position),location)<1e-5
        delta=np.asarray(row['position_km'])-reference_position;shape=np.asarray(row['covariance_km2'])
        row['mahalanobis_squared']=float(delta@np.linalg.solve(shape,delta))
        row['inside_nominal95']=row['mahalanobis_squared']<=5.991464547107979
    summary={}
    for size in [1,2,4]:
        chosen=[r for r in rows if r['size']==size];shaped=[r for r in chosen if r['shape_available']]
        summary[str(size)]=dict(evaluated=len(chosen),fit_accepted=sum(r['fit_accepted'] for r in chosen),
            shape_available=len(shaped),inside_nominal95=sum(r['inside_nominal95'] for r in shaped),
            median_nominal95_major_radius_m=float(np.median([r['nominal95_major_radius_m'] for r in shaped])) if shaped else None)
    result=dict(rows=rows,summary=summary,input_sha256=bindings,reference_sha256=digest(reference_path),
        source_sha256={str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])},
        qualification='Inverse local IRLS curvature with nuisance profiling and fixed fitted associations. Not exact posterior covariance or calibrated confidence. Coverage is descriptive on correlated development windows with an unsurveyed reference; no scale is tuned here.')
    with out.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    out.with_suffix('.sha256').write_text(digest(out)+'\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
