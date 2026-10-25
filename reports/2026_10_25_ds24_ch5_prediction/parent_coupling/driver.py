"""Bounded active-parent B(phi) diagnostic: frozen Gaussian, no position fit."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np
from scipy.linalg import solve_triangular

import coupling_math as cm

HERE=Path(__file__).resolve().parent
RESEARCH=HERE.parent.parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE=RESEARCH/'ds25-20261024'
RECOVERY=RESEARCH/'ds24-movement-policy-r01/recovery'
SUPPORT=RESEARCH/'ds24-identity-support-r01/scientific'
CASES=('DS24-0010','DS24-0011')
ARMS=('c0','fitted_c')
OFFSETS=(-.05,-.025,0.,.025,.05)
RULES=(81,161,321)


def read(path):return json.loads(Path(path).read_bytes())


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def encode(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(type(value).__name__)


def write(name,value):
    path=HERE/name;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,indent=2,default=encode,allow_nan=False);stream.write('\n')


def freeze():
    began=time.monotonic();selected=[];bindings={}
    sys.path.insert(0,str(RECOVERY));sys.path.insert(0,str(SUPPORT))
    import recovery
    import support_geometry
    import leo.analysis.research.orbit_uncertainty
    import leo.analysis.research.continuous_curve_fit
    import scipy
    paths=[Path(__file__),HERE/'coupling_math.py',HERE/'summarize.py',HERE/'test_coupling.py',HERE/'test_receipt.json',HERE/'PROTOCOL.md',RECOVERY/'recovery.py',
        SUPPORT/'support_geometry.py',REPO/'tools/ds23_height_problem.py',REPO/'tools/ds23_predictive_linear.py',
        REPO/'tools/dsx01_hierarchical_bound.py',REPO/'tools/ds23_frequency_events.py',
        REPO/'tools/probe_ds23_history_calibrated_phase.py',
        REPO/'src/leo/analysis/research/orbit_uncertainty.py',
        REPO/'src/leo/analysis/research/continuous_curve_fit.py']
    for case in CASES:
        info_path=RESEARCH/'ds24-bottlenecks-20261024/information'/(case+'.json')
        document=read(info_path)['arms']['c0']
        kind='curved_plus_predictive_fixed_Gamma_surrogate' if document['curved_plus_predictive_fixed_Gamma_surrogate'] else 'curved'
        info=document[kind]
        physical={row['norad'] for row in document['physical_orbit_metadata'].values()}
        rows=[r for r in info['correlations']['top_weak_axis_correlates']
              if r['coordinate'].startswith('phase_NORAD') and int(r['coordinate'].split('NORAD')[1]) in physical]
        rows.sort(key=lambda r:(-abs(r['weak_axis_correlation']),int(r['coordinate'].split('NORAD')[1])))
        if not rows:raise ValueError('no existing supported RF-sensitive phase family; no replacement')
        chosen=rows[0];norad=int(chosen['coordinate'].split('NORAD')[1])
        parent_path=SOURCE/'family_cavity/position'/(case+'.json')
        anchor=read(parent_path)['policy_arms']['c0']['endpoint_east_north_km']
        selected.append(dict(case=case,norad=norad,selection_coordinate=chosen['coordinate'],
            archived_weak_correlation=chosen['weak_axis_correlation'],source_information_kind=kind,
            weak=np.asarray(info['correlations']['weak_axis_east_north']),
            weak_precision_per_km2=min(info['all']['eigenvalues_per_km2']),anchor=anchor))
        paths += [info_path,parent_path,SOURCE/case/'preparation_receipt.json']
        for name in read(SOURCE/case/'preparation_receipt.json')['files_sha256']:
            paths.append(SOURCE/name)
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if not name:continue
        path=Path(name).resolve()
        if path.suffix=='.py' and path.is_file() and (path.is_relative_to(REPO) or path.is_relative_to(RESEARCH)):
            if '.venv' not in path.parts:paths.append(path)
    bindings={str(path):sha(path) for path in sorted(set(paths))}
    write('protocol.json',dict(selections=selected,files=bindings,arms=ARMS,offsets_km=OFFSETS,rules=RULES,
        phase_law='Normal(original causal mean, phase_sigma/sqrt(original frozen conditional prior precision)), conditioned[-15,15]',
        selected_phase_is_not_original_Student_marginal=True,original_Gamma_and_other_nuisance_precision_frozen_at_anchor=True,
        centers='same saved c0 RF endpoint for both arms; old c0 weak axis frozen',
        score_tolerance=1e-3,gradient_tolerance_per_km=1e-3,affine_Gaussian_closure_tolerance=1e-5,
        finite_step_gradient_tolerance_absolute_per_km=.01,finite_step_gradient_tolerance_relative=.05,
        material_displacement_km=.025,material_to_numeric_error_ratio=5.,
        maximum_scientific_seconds=300,workers=1,BLAS_threads=1,
        freeze_processing_seconds=time.monotonic()-began,numpy_version=np.__version__,scipy_version=scipy.__version__,
        numerical_scope='resolved modes only; proposal/global grid do not prove absence of remote narrow modes',
        no_GPS=True,position_fits=0,new_noise_or_prior_tuning=False))
    print('protocol_sha256',sha(HERE/'protocol.json'))


def verify(approval=True):
    protocol=read(HERE/'protocol.json')
    for path,digest in protocol['files'].items():
        if sha(path)!=digest:raise ValueError('frozen source/input changed: '+path)
    if approval:
        receipt=read(HERE/'independent_preflight.json')
        if not receipt['all_passed'] or receipt['protocol_sha256']!=sha(HERE/'protocol.json'):
            raise ValueError('matching independent preflight required')
    return protocol


def geometric(data,phases):
    """Same exact nominal f in both branches; full three-mode design is optional."""
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
    from prototype_dsx01_continuous_position import latlon
    phi=np.asarray(phases);count=len(phi);times=data['times'];m=len(times)
    sky=dict(time_s=data['knots'])
    modes=dict(time_s=data['knots'])
    for key in ('position_km','velocity_km_s'):
        sky[key]=np.broadcast_to(data['sky_'+key],(count,*data['sky_'+key].shape[1:]))
        b=data['modes_'+key]
        modes[key]=np.broadcast_to(b[None],(count,*b.shape)).reshape(count*3,*b.shape[1:])
    flat_times=np.tile(times,count);labels=np.repeat(np.arange(count),m)
    coordinates=latlon(data['position'])
    f,e=paired_phase_frequency(sky,flat_times,labels,phi,*coordinates)
    b=paired_frequency_modes(sky,modes,flat_times,labels,phi,*coordinates)
    return (f.reshape(count,m)*data['q'][None],
            b.reshape(count,m,3)*data['q'][None,:,None]/np.sqrt(data['mode_precision'])[None,None,:],
            e.reshape(count,m))


def prepare(protocol):
    sys.path.insert(0,str(RECOVERY));sys.path.insert(0,str(SUPPORT))
    import recovery as r
    import support_geometry as support
    from ds23_height_problem import geometry_features
    from ds23_predictive_linear import linear_geometry
    from prototype_dsx01_continuous_position import latlon
    from leo.sky.frames import geodetic_to_ecef_km,ecef_to_enu_matrix
    artifacts=[]
    for selection in protocol['selections']:
        case=selection['case'];d=r.context(case);anchor=np.asarray(selection['anchor']);weak=np.asarray(selection['weak'])
        j=int(np.flatnonzero(d['scan'].norads==selection['norad'])[0])
        for arm in ARMS:
            p=r.build(d,arm,d['arms'][arm]['phase_reference'])
            if j not in p.supported:raise ValueError('selected existing family lacks original physical modes; no replacement')
            local=p.labels.index(j);phase_slot=p.hardware.shape[1]+p.smooth.shape[1]+local
            mode_slot=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*p.supported.index(j)
            mode_slots=np.arange(mode_slot,mode_slot+3)
            c=dict(p.curved_calculate(anchor) if d['entries'] else p.calculate(anchor))
            if not np.isfinite(c['final_log_precision_change']) or c['final_log_precision_change']>1e-5:
                raise ValueError('anchor Gamma precision did not converge')
            precision=np.asarray(c['coefficient_prior_precision'])
            prior_mean=np.zeros(len(precision));begin=p.hardware.shape[1]+p.smooth.shape[1]
            prior_mean[begin:begin+len(p.labels)]=np.asarray(d['means'])/p.phase_sigma
            groups=p.noise_groups[p.keep]
            variance=p.point_noise[p.keep]**2/(np.asarray(d['powers'])[groups]*c['noise_precision'][groups])
            values=p.values[p.keep];times=p.flat_times[p.keep];labels=p.flat_labels[p.keep];q=p.q[p.keep]
            ids=[oid for i,sl in zip(p.members,p.slices,strict=True)
                 for oid,use in zip(d['scan'].tracks[i]['observation_ids'],p.keep[sl],strict=True) if use]
            view=None;predictive_ids=[]
            if d['entries']:
                view,ey,es,eg,_=linear_geometry(p,d['entries'])
                values=np.r_[values,ey];times=np.r_[times,view.flat_times];labels=np.r_[labels,view.flat_labels];q=np.r_[q,view.q]
                variance=np.r_[variance,2*es**2]
                predictive_ids=[oid for e in d['entries'] for oid in e['observation_ids']]
                ids+=predictive_ids
                precision=np.r_[precision,np.ones(len(d['entries']))]
                prior_mean=np.r_[prior_mean,np.zeros(len(d['entries']))]
            if len(ids)!=len(set(ids)):raise ValueError('duplicate joint physical observation IDs')
            chosen=labels==local
            sky={key:np.asarray(p.sky[key])[[local]] for key in ('position_km','velocity_km_s')}
            modes={key:np.asarray(p.mode_bank[key])[3*local:3*local+3] for key in ('position_km','velocity_km_s')}
            for offset in OFFSETS:
                position=anchor+offset*weak
                geo=geometry_features(p,position,0.)
                h=geo['features'][p.keep];intercept=p.q[p.keep]*geo['intercept'][p.keep]
                if view is not None:
                    egeo=geometry_features(view,position,0.)
                    h=np.vstack((np.column_stack((h,np.zeros((len(h),len(d['entries']))))),
                        np.column_stack((egeo['features'],300*np.eye(len(d['entries']))[eg]))))
                    intercept=np.r_[intercept,view.q*egeo['intercept']]
                reduced=cm.reduce_family(values,intercept,h,precision,variance,prior_mean,chosen,
                    phase_slot,mode_slots,p.phase_sigma[local],d['means'][local])
                data=dict(reduced,position=position,times=times[chosen],q=q[chosen],knots=p.sky['time_s'],
                    mode_precision=precision[mode_slots],reference_phase=float(p.reference[local]),
                    sky_position_km=sky['position_km'],sky_velocity_km_s=sky['velocity_km_s'],
                    modes_position_km=modes['position_km'],modes_velocity_km_s=modes['velocity_km_s'])
                data['covariance_root']=np.linalg.cholesky(data['covariance'])
                ref_f,ref_b,_=geometric(data,[p.reference[local]])
                berror=float(np.max(abs(ref_b[0]-data['frozen_modes'])))
                ferror=float(np.max(abs(ref_f[0]-data['affine_intercept']-data['derivative']*p.reference[local])))
                if max(berror,ferror)>1e-7:raise ValueError('original physical reference features do not replay')
                latitude,longitude=latlon(position)
                certificate=support.support(dict(time_s=p.sky['time_s'],position_km=sky['position_km']),
                    times[chosen],ecef_to_enu_matrix(latitude,longitude)[2],geodetic_to_ecef_km(latitude,longitude,0.))
                full_visibility=certificate['inner_visible_intervals']==[[-15.,15.]] and not certificate['unresolved_intervals'] and not certificate['root_brackets']
                if not full_visibility:raise ValueError('full nominal visibility prerequisite failed; no support-law amendment')
                phase_probes=np.unique(np.clip([p.reference[local],data['prior_mean'],
                    data['prior_mean']-data['prior_sd'],data['prior_mean']+data['prior_sd']],-15,15))
                _,probe_b,_=geometric(data,phase_probes)
                delta=probe_b-data['frozen_modes'][None]
                tag=case+'/'+arm+'/offset'+str(offset)
                path=HERE/(tag+'.npz');path.parent.mkdir(parents=True,exist_ok=True)
                if path.exists():raise FileExistsError(path)
                np.savez_compressed(path,**data)
                metadata=dict(case=case,arm=arm,norad=selection['norad'],offset_km=offset,
                    artifact=str(path),artifact_sha256=sha(path),position=position,
                    original_phase_sigma_s=float(p.phase_sigma[local]),
                    original_phase_prior_precision=float(precision[phase_slot]),
                    phase_prior_mean_s=float(d['means'][local]),conditional_phase_prior_sd_s=float(data['prior_sd']),
                    proposal_phase_mean_s=data['proposal_mean'],proposal_phase_sd_s=data['proposal_sd'],
                    selected_native_IDs=[oid for oid,use in zip(ids,chosen,strict=True) if use],
                    joint_native_IDs=ids,predictive_native_IDs=predictive_ids,
                    Gaussian_closure_error=reduced['Gaussian_closure_error'],
                    reference_B_error_hz=berror,reference_frequency_error_hz=ferror,
                    full_nominal_visibility=True,visibility_certificate=certificate,
                    matrix_probe_phase_s=phase_probes,matrix_B_change_RMS_hz=np.sqrt(np.mean(delta**2,axis=(1,2))),
                    matrix_B_change_max_abs_hz=np.max(abs(delta),axis=(1,2)),
                    original_reference_phase_s=float(p.reference[local]),Gamma_precision_change=float(c['final_log_precision_change']))
                write(tag+'.json',metadata);artifacts.append(metadata)
    return artifacts


def run():
    protocol=verify();began=time.monotonic()
    test_seconds=read(HERE/'test_receipt.json')['seconds']+protocol['freeze_processing_seconds']
    remaining=protocol['maximum_scientific_seconds']-test_seconds
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s scientific worker cap')))
    signal.setitimer(signal.ITIMER_REAL,remaining)
    write('execution_started.json',dict(protocol_sha256=sha(HERE/'protocol.json'),test_seconds=test_seconds,remaining_seconds=remaining))
    rows=[];artifacts=[];failure=None
    try:
        artifacts=prepare(protocol)
        write('preparation.json',dict(rows=artifacts,seconds=time.monotonic()-began))
        for metadata in artifacts:
            with np.load(metadata['artifact'],allow_pickle=False) as archive:data={key:archive[key] for key in archive.files}
            evaluate=lambda phases:geometric(data,phases)
            records={branch:{str(n):cm.integrate(data,evaluate,branch,n) for n in RULES}
                     for branch in ('frozen','dynamic')}
            references={branch:cm.adaptive_reference(data,evaluate,branch) for branch in ('frozen','dynamic')}
            dense_errors=[]
            f,b,_=evaluate([float(data['proposal_mean'])])
            for modes in (data['frozen_modes'],b[0]):
                rank=cm.node_costs(data['raw'],data['covariance'],f,np.asarray(modes)[None],root=data['covariance_root'])[0]
                dense_errors.append(abs(rank-cm.dense_node_cost(data['raw'],data['covariance'],f[0],modes)))
            row=dict(case=metadata['case'],arm=metadata['arm'],offset_km=metadata['offset_km'],
                records=records,adaptive_reference=references,maximum_dense_node_error=float(max(dense_errors)))
            write(metadata['case']+'/'+metadata['arm']+'/score'+str(metadata['offset_km'])+'.json',row)
            rows.append(row)
    except Exception as exc:
        failure=dict(error=repr(exc),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    result=dict(status='complete' if len(rows)==20 and failure is None else 'incomplete',
        rows=rows,failure=failure,selected_probe_count=20,complete_probe_count=len(rows),
        seconds=time.monotonic()-began,cumulative_scientific_seconds=test_seconds+time.monotonic()-began,
        position_fits=0,GPS_used=False,global_mode_certificate=False)
    write('results.json',result)
    files=[p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ('RF_seal.json',)]
    verify(approval=False)
    write('RF_seal.json',dict(files={str(p):sha(p) for p in files},protocol_sha256=sha(HERE/'protocol.json'),position_fits=0))
    print(json.dumps({key:value for key,value in result.items() if key!='rows'},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=('freeze','run'))
    args=parser.parse_args()
    if args.stage=='freeze':freeze()
    else:run()
