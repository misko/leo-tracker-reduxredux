"""Time complete saved-GLRT-to-coordinate work in one process, with no encoded figures."""

import hashlib
import json
import os
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig

import cold_replay as cold
sys.path.insert(0,str(cold.ROOT/"stream"))
from winner_to_fix import track_document, winners as native_winners


def timed(case, config, mode):
    begin = time.perf_counter()
    cpu = time.process_time()
    raw = cold.read(cold.INPUT/case/"native.json")
    parsed = time.perf_counter()
    if mode == "batch":
        doc = prepare_tracks(raw, config)
        point_count = len(doc["observations"])
    else:
        winners, meta, half = native_winners(raw)
        winners = [r for r in winners if r[4]+half <= meta["duration_s"]+1e-8]
        doc, _ = track_document(winners)
        doc["metadata"] = meta
        point_count = len(winners)
    del raw
    graphed = time.perf_counter()
    bank, receipt = cold.build_bank(case,doc["metadata"],check_approximation=False)
    staged = time.perf_counter()
    d = cold.descriptors(doc,bank)
    bias = cold.bias_vote(d)
    _, start, winners, losses = cold.grid_vote(d,bias)
    selected = np.flatnonzero(losses<12.)
    arms = {arm:cold.solve(d,selected,winners,bias,start,fitted_c=(arm=="fitted_c"))
            for arm in ("c0","fitted_c")}
    end = time.perf_counter()
    return dict(case=case, mode=mode,wall=end-begin,cpu=time.process_time()-cpu,
                json_s=parsed-begin, graph_s=graphed-parsed, sky_s=staged-graphed,
                match_and_solve_s=end-staged, post_graph_s=end-graphed,
                max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                points=point_count,curved=len(d["ti"]),sky=receipt,arms=arms)


def main():
    panel = cold.read(cold.ROOT/"cold-panel.json")
    cases = cold.panel()[::8]
    ref = {r["case"]:r for r in panel["rows"]}
    sref = {r["case"]:r for r in cold.read(cold.ROOT/"stream/winner-positions-32.json")["rows"]
            if r["deadline"]=="full"}
    config = TrackConfig(**cold.read(cold.INPUT/"config.json")["config"])
    start_load = os.getloadavg()
    rows = []
    for repetition in range(5):
        for case in (cases if repetition%2==0 else cases[::-1]):
            for mode in (("stream","batch") if (repetition+cases.index(case))%2 else ("batch","stream")):
                row = timed(case,config,mode)
                expected = ref[case]["results"]["joint"] if mode=="batch" else sref[case]["arms"]
                count = ref[case]["winner_points"] if mode=="batch" else sref[case]["winners"]
                assert row["points"]==count
                for arm,fit in row["arms"].items():
                    assert fit["status"]==expected[arm]["status"]=="estimate"
                    assert np.allclose(fit["xy"],expected[arm]["xy"],rtol=0,atol=1e-7)
                rows.append(dict(repetition=repetition,**row))
    out = dict(cases=cases,architecture=platform.machine(),affinity=sorted(os.sched_getaffinity(0)),
               host_load_at_start=start_load,host_load_at_end=os.getloadavg(),
               source_sha256=hashlib.sha256(Path(cold.__file__).read_bytes()).hexdigest(),rows=rows)
    (cold.ROOT/"paired-native-timing.json").write_text(json.dumps(out))


if __name__=="__main__":
    main()
