"""Read-only field coverage audit of all64 prepared exports and bound pose copies."""
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources

HERE=Path(__file__).resolve().parent


def main():
    selection=sealed(HERE/'selection.json');reference=sealed(HERE/'reference-admission-v1.json')
    verify_sources(reference['source_sha256']);assert reference['selection_sha256']==digest(HERE/'selection.json')
    refs={r['unit']:r for r in reference['rows']};inputs={str(HERE/n):digest(HERE/n) for n in ('selection.json','reference-admission-v1.json')}
    rows=[]
    quality_fields=('snr','snr_db','amplitude','power','coherence','coherence_margin','peak_width_hz','standard_uncertainty_hz','variance_hz2')
    for capture in selection['captures']:
        unit=capture['unit_id'];directory=HERE/'prepared'/unit
        paths={n:directory/n for n in ('observations.json','evidence.json','orbits.json')}
        documents={n:json.loads(p.read_text()) for n,p in paths.items()}
        obs=documents['observations.json'];evidence=documents['evidence.json'];orbits=documents['orbits.json']
        assert obs['session_id']==evidence['session_id']==capture['session_id']
        assert obs['manifest_sha256']==capture['manifest_sha256']
        assert evidence['source']['sha256']==orbits['observation_sha256']==digest(paths['observations.json'])
        inputs.update({str(p):digest(p) for p in paths.values()})
        companion=refs[unit]['companion'];assert companion['manifest_sha256']==capture['manifest_sha256']
        pose=companion['pose_authority'];receivers=pose['receivers']
        exported=obs['tracks'];tracks=evidence['tracks']
        assert {t['track_id'] for t in exported}=={t['track_id'] for t in tracks}
        rows.append(dict(unit=unit,dataset=capture['dataset'],tracks=len(tracks),samples=sum(len(t['measured_hz']) for t in tracks),
            covariance_available=sum(t.get('uncertainty',{}).get('covariance_hz2') is not None for t in tracks),
            quality_fields_present={k:sum(k in t for t in exported) for k in quality_fields},
            export_track_keys=sorted({k for t in exported for k in t}),
            pose_revision=pose['revision'],receiver_records=len(receivers),
            azimuth_recorded=sum(r.get('azimuth_deg') is not None for r in receivers),
            elevation_recorded=sum(r.get('elevation_deg') is not None for r in receivers),
            roll_recorded=sum(r.get('roll_deg') is not None for r in receivers),
            provisional_mapping=sum(r.get('mapping_status')=='provisional' for r in receivers),
            nominal_outward_tilt_deg=pose.get('nominal_outward_tilt_deg'),
            phase_center_baseline_recorded=pose.get('phase_center_baseline_enu_m') is not None,
            altitude_recorded=pose.get('altitude_m') is not None))
    assert len(rows)==64
    summary={ds:dict(scans=len(local),tracks=sum(r['tracks'] for r in local),samples=sum(r['samples'] for r in local),
        covariance_available=sum(r['covariance_available'] for r in local),
        receiver_records=sum(r['receiver_records'] for r in local),
        azimuth_recorded=sum(r['azimuth_recorded'] for r in local),elevation_recorded=sum(r['elevation_recorded'] for r in local),
        roll_recorded=sum(r['roll_recorded'] for r in local),provisional_mapping=sum(r['provisional_mapping'] for r in local))
        for ds in ('DS9','DS10','DS11') for local in [[r for r in rows if r['dataset']==ds]]}
    source_paths=[Path(__file__).resolve(),HERE/'window_inputs.py',HERE.parents[1]/'tools/ds7_export_baseline.py',
        HERE.parent/'2026_09_30_gaussian_sum_64_scan/physics.py',HERE.parent/'2026_09_30_rx_sky_coverage/README.md',
        HERE.parent/'2026_09_28_rx_nominal_beam_cv/README.md',HERE.parent/'2026_09_28_rx_beam_crossing/REPORT.md']
    sources={str(p):digest(p) for p in source_paths};verify_sources(inputs);verify_sources(sources)
    save(HERE/'physical-evidence-inventory-v1.json',dict(rows=rows,summary=summary,inputs=inputs,sources=sources,
        qualification='Inventory of exported tracks before independent-track filtering and eight-point retention. Absence from export does not imply absence from archived source or IQ. Pose fields are recorded operator evidence, not calibration.'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    axes[0].bar(['DS9','DS10','DS11'],[summary[ds]['tracks'] for ds in ('DS9','DS10','DS11')]);axes[0].set_ylabel('Exported tracks');axes[0].set_title('All64 development scans')
    fractions=[sum(r['azimuth_recorded'] for r in rows)/128,sum(r['elevation_recorded'] for r in rows)/128,
               sum(r['roll_recorded'] for r in rows)/128,sum(r['covariance_available'] for r in rows)/sum(r['tracks'] for r in rows)]
    axes[1].bar(['Azimuth','Elevation','Roll','Track\ncovariance'],fractions);axes[1].set_ylim(0,1.1);axes[1].set_ylabel('Recorded fraction');axes[1].set_title('Pose records / exported uncertainty')
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.savefig(HERE/'physical-evidence-inventory-v1.png',dpi=160)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
