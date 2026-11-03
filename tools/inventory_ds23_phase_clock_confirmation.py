"""Freeze additional saved scans using native two-component evidence only."""

from pathlib import Path
import json
import numpy as np

from inventory_ds23_paired_component_cycles import AUTHORITY,FS,paired_cycles
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_phase_clock_confirmation'


def main():
    OUT.mkdir(exist_ok=True);target=OUT/'inventory.json'
    if target.exists():raise FileExistsError('preserve frozen new-scan RF selection')
    authority=read(AUTHORITY);records=[];bindings={}
    for filename,digest in authority['saved_panel_sha256'].items():
        panel=Path(filename)
        if sha(panel)!=digest:raise ValueError('saved IQ panel changed')
        with np.load(panel,allow_pickle=False) as archive:metadata=json.loads(str(archive['metadata_json']))
        case=metadata['case']
        if case in ['DS23-0154','DS23-0216']:continue
        tracking=ROOT/'reports/2026_10_19_algo02_ds23_full'/case/'tracking.json'
        if not tracking.exists():continue
        doc=read(tracking);probes={(p['visit_index'],p['receiver_id']):p for p in doc.get('source',doc)['probes']}
        bindings[str(tracking)]=sha(tracking)
        for point in metadata['points']:
            rx=[probes.get((point['visit_index'],r)) for r in [0,1]]
            if any(r is None for r in rx):continue
            cycles=paired_cycles(rx[0]['candidates'],rx[1]['candidates'],minimum_margin=.1)
            if not cycles:continue
            best=max(cycles,key=lambda c:(c['minimum_native_margin'],min(c['epoch_separation_samples'])))
            records.append(dict(case=case,panel=str(panel),window_key=point['window_key'],visit_index=point['visit_index'],
                sample_counter=point['sample_counter'],channel=point['lane'][1],rf_hz=point['lane'][2],edge=point['edge'],
                sample_rate_hz=FS,raw_window_sha256=point['raw_window_sha256'],**best))
    selected=[max([r for r in records if r['case']==case],key=lambda r:(r['minimum_native_margin'],-r['visit_index']))
        for case in sorted({r['case'] for r in records})]
    write(target,dict(selected=selected,available_windows=len(records),minimum_each_native_margin=.1,
        previous_two_scan_cohort_excluded=True,selection='one strongest native minimum-margin pair per additional saved scan',
        authority_sha256=sha(AUTHORITY),panel_sha256=authority['saved_panel_sha256'],tracking_sha256=bindings,
        tools_sha256={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'inventory_ds23_paired_component_cycles.py']},
        previously_studied_saved_cases_not_new_geographic_locations=True,
        no_GPS_TLE_satellite_labels_clock_outcomes_or_position_errors_used=True,no_new_RF_collection=True))
    print([(r['case'],r['window_key'],r['minimum_native_margin']) for r in selected],flush=True)


if __name__=='__main__':main()
