"""Bounded reuse of existing native-path recovery on the frozen 0326 reference."""
from pathlib import Path
import signal
from probe_ds23_worst_association_bottleneck import setup,inventory
import probe_ds23_graph_seeded_paths as paths
from run_algo01_ds23_sample import write,sha

OUT=Path(__file__).resolve().parents[1]/'evidence/native_recovery_v2'


def parent(case):
    d=setup(case)
    d['original_protected']={r['candidate_index'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}
    d['original_protected'].update(e['candidate_index'] for e in d['entries'])
    coverage={a:inventory(d,a) for a in ('c0','fitted_c')}
    return d,coverage,'default',None


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve native recovery run')
    write(OUT/'protocol.json',dict(case='DS23-0326',parent='published family-cavity reference',
        unchanged_existing_temporal_path_rules=True,original_curve_calibration_fixed=True,
        candidates='both incumbent causal families; this is NOT a full-catalogue discovery',
        primary='persistent5s',control='independent',new_paths_predictive_only=True,
        no_GPS_future_TLE_new_RF_or_point_deletion=True,job_cap_seconds=180,
        source_sha256={p.name:sha(p) for p in (Path(__file__),Path(paths.__file__),Path(paths.native.__file__),Path(paths.temporal.__file__))}))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180 second native recovery cap')))
    signal.alarm(180);paths.OUT=OUT;paths.parent=parent;paths.runner.configure=lambda:None
    try:
        result=paths.one('DS23-0326');write(OUT/'execution.json',result)
    finally:signal.alarm(0)


if __name__=='__main__':main()
