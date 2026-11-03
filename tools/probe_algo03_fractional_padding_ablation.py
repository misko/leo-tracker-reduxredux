"""Separate fractional-frame timing from isolated-template padding effects."""

from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json
import time

import numpy as np

from decoupled_pilot_clocks import IsolatedRoundedCoupledWorkspace
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/'reports/2026_10_19_algo03_fractional_pilot_benchmark'
OUT=ROOT/'reports/2026_10_19_algo03_fractional_padding_ablation'


def main():
    if OUT.exists():
        raise FileExistsError('preserve padding ablation')
    OUT.mkdir();r=read(SOURCE/'results.json');names=sorted({z['entry']['panel'] for z in r['rows']})
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/decoupled_pilot_clocks.py'),
        original_comparison_sha256=sha(SOURCE/'results.json'),
        panel_sha256={p:sha(ROOT/p) for p in names},
        only_isolated_template_padding_changes_from_rounded_legacy=True,
        same_three_parameters_frame_gains_DC_sample_support_and_frequency_scout=True,
        no_GPS_or_position_used=True,workers=8))
    panels={p:np.load(ROOT/p,allow_pickle=False) for p in names}
    def one(row):
        e=row['entry'];point=e['point'];panel=panels[e['panel']]
        fs=json.loads(str(panel['metadata_json']))['sample_rate_hz']
        values=panel[point['window_key']][:,point['receiver_offset']]
        y=values[:,0].astype(float)+1j*values[:,1]
        epoch=point['peak']['integer_epoch_sample']+point['peak']['fractional_epoch_offset_samples']
        work=IsolatedRoundedCoupledWorkspace(y,fs,point['edge'],epoch)
        fit=work.fast_joint_fit(point['peak']['fractional_tracking_cfo_hz'])
        return dict(index=row['index'],observation_id=point['observation_id'],entry=e,
            legacy_score=row['legacy_fit']['score'],fractional_score=row['fractional_fit']['score'],
            isolated_rounded_fit=fit,padding_only_score_ratio=fit['score']/row['legacy_fit']['score'],
            fractional_over_isolated_rounded_score_ratio=row['fractional_fit']['score']/fit['score'])
    rows=[];started=time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            for future in as_completed([executor.submit(one,row) for row in r['rows']]):
                rows.append(future.result())
        write(OUT/'results.json',dict(rows=sorted(rows,key=lambda v:v['index']),seconds=time.monotonic()-started,
            protocol_sha256=sha(OUT/'protocol.json'),no_position_or_calibration_updated=True))
        print('probes',len(rows),'median padding ratio',np.median([v['padding_only_score_ratio'] for v in rows]),
              'median fractional ratio',np.median([v['fractional_over_isolated_rounded_score_ratio'] for v in rows]),flush=True)
    finally:
        for p in panels.values():p.close()


if __name__=='__main__':main()
