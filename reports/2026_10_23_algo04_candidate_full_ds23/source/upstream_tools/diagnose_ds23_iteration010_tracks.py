"""Existing whole-track causal/following diagnostic on the iteration010 cases."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import run_ds23_dbg01_iteration_010 as runner
import diagnose_ds23_iteration007_tracks as diagnostic
from ds23_supported_curvature import curvature_evidence
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'all_track_diagnostics'


def configure():
    runner.configure();diagnostic.runner=runner;diagnostic.OUT=OUT


def curvature_inventory(case):
    d=runner.engine.current_setup(case);inventory=read(runner.RAW/case/'inventory.json')['arms']['c0'];rows=[]
    for target in inventory['ranking']:
        if target['points']!=target['original_points']:continue
        track=d['scan'].tracks[target['track_index']]
        rows.append(dict(target=target,short_duration_evidence=curvature_evidence(track)))
    return dict(case=case,rows=rows,diagnostic_only_no_classification_changed=True,
        existing20s_classifier_versus_existing10s_jackknife_ablation=True)


def main():
    configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve iteration010 track diagnostics')
    cases=read(runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        reused_diagnostic_sha256=sha(Path(diagnostic.__file__)),
        three_longest_wholly_unused_tracks_at_least8points_including_linear=True,
        following_TLEs_are_diagnostic_only_never_inference=True,
        frozen_original_endpoint_and_causal_radio_posterior=True,no_GPS_or_new_RF=True))
    for c in cases:write(OUT/(c+'_curvature.json'),curvature_inventory(c))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(diagnostic.one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
