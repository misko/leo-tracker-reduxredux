"""Calibrate only independently curved recoveries from corrected RF metadata."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

from probe_algo03_frame_peak_recovery import run
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/'reports/2026_10_19_algo03_frame_predictive_v2'
OUT=ROOT/'reports/2026_10_19_algo03_frame_curved_cohort'


def main():
    if OUT.exists():
        raise FileExistsError('preserve curved-only recovery calibration trial')
    OUT.mkdir();cases=read(SOURCE/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,workers=30,source_sha256=sha(Path(__file__)),
        recovery_engine_sha256=sha(ROOT/'tools/probe_algo03_frame_peak_recovery.py'),
        recovery_helper_sha256=sha(ROOT/'tools/ds23_frame_peak_recovery.py'),
        source_selection_protocol_sha256=sha(SOURCE/'protocol.json'),
        corrected_per_scan_sample_rates_used=True,
        selection='only frozen recovered fragments whose own samples independently satisfy active curvature, BIC and noise gates',
        no_new_hyperparameter_or_GPS_selection=True,
        no_original_curved_point_removed=True,linear_tracks_never_calibration_anchors=True,
        matched_c0_fitted_c_inputs_priors_and_cold_start_budgets=True,
        physical_cross_RX_support_can_enable_original_orbit_modes=True))
    selected=[]
    for case in cases:
        source_path=SOURCE/(case+'_selection.json');s=read(source_path);methods={}
        for method,m in s['methods'].items():
            fragments=[f for f in m['fragments'] if f['polynomial']['active_curvature']]
            methods[method]=dict(fragments=fragments,receipt=dict(
                added_original_winners=sum(r['kind']=='unretained_original_winner' for f in fragments for r in f['peak_ownership']),
                added_native_secondary_peaks=sum(r['kind']=='additional_native_peak' for f in fragments for r in f['peak_ownership'])))
        write(OUT/(case+'_selection.json'),dict(s,methods=methods,
            inherited_predictive_selection_sha256=sha(source_path),new_selections_or_position_input=False))
        selected.append(dict(case=case,methods={m:len(v['fragments']) for m,v in methods.items()}))
    write(OUT/'selection_inventory.json',selected)
    results=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=30) as executor:
        for future in as_completed([executor.submit(run,c,output_dir=OUT) for c in cases]):
            r=future.result();results.append(r);print(r,flush=True)
    write(OUT/'execution.json',dict(results=results,seconds=time.monotonic()-started))


if __name__=='__main__':main()
