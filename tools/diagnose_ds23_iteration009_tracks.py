"""Longest whole unused curves, with following elements isolated as diagnostics."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import repair_ds23_iteration009_targets as repair
import diagnose_ds23_iteration007_tracks as diagnostic
from run_algo01_ds23_sample import read,write,sha

OUT=repair.runner.RAW/'all_track_diagnostics'


def configure():
    repair.configure();diagnostic.runner=repair.runner;diagnostic.OUT=OUT


def main():
    configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve all-track diagnosis')
    write(OUT/'protocol.json',dict(cases=read(repair.runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        diagnostic_source_sha256=sha(Path(diagnostic.__file__)),
        three_longest_wholly_unused_tracks_at_least8points_including_linear=True,
        partial_suffix_examined_separately_without_discarding_or_renominating_its_active_prefix=True,
        following_TLEs_only_for_diagnosis_never_for_inference=True,no_GPS_or_new_RF=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(diagnostic.one,read(OUT/'protocol.json')['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
