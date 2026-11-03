"""Reuse the longest-track causal/following diagnostic on iteration008."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import run_ds23_dbg01_iteration_008 as runner
import diagnose_ds23_iteration007_tracks as diagnostic
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'all_track_diagnostics'


def configure():
    runner.configure();diagnostic.runner=runner;diagnostic.OUT=OUT


def main():
    configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve diagnostic protocol')
    record=dict(cases=read(runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        diagnostic_source_sha256=sha(Path(diagnostic.__file__)),
        scope='three longest wholly unused graph tracks >=8points, including linear tracks',
        same_original_RF_endpoints_and_causal_receiver_posteriors=True,
        following_elements_diagnostic_only_never_enter_inference=True,
        no_GPS_point_trimming_or_new_RF=True)
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(diagnostic.one,record['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
