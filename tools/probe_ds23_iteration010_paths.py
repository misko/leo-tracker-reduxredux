"""Transfer the existing graph-seeded orphan search without changing its rules."""

from pathlib import Path

import run_ds23_dbg01_iteration_010 as runner
import probe_ds23_graph_seeded_paths as paths
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'graph_seeded_paths'


def configure():
    runner.configure();paths.runner=runner;paths.OUT=OUT


def main():
    configure()
    if not read(runner.RAW/'support_aware_reentry/finalization_audit.json')['all_passed']:
        raise ValueError('finish graph parent qualification before temporal recovery')
    OUT.mkdir(exist_ok=True)
    if (OUT/'binding.json').exists():raise FileExistsError('preserve temporal binding')
    write(OUT/'binding.json',dict(source_sha256=sha(Path(__file__)),reused_driver_sha256=sha(Path(paths.__file__)),
        cases=read(runner.RAW/'protocol.json')['cases'],
        unchanged_independent_and_persistent5s_rules=True,unchanged19permutations_and_thresholds=True,
        graph_parent_frozen_by_RF_gates_before_temporal_search=True,
        no_GPS_following_TLE_or_RF_collection=True,no_new_ALGO_version=True))
    paths.main()
    if any(r['status']!='complete' for r in read(OUT/'execution.json')['rows']):raise RuntimeError('temporal worker failed')


if __name__=='__main__':main()
