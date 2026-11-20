"""Read authenticated native factors and stop the frozen receiver after its region gate."""

import hashlib
import json
import sys
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import process_time
from unittest.mock import patch

from tools.pipeline_eval.variants import portable_gate, portable_v5, tile_region_empirical, v5_core


def run(packet):
    start = process_time()
    raw = Path("/input/native").read_bytes()
    if hashlib.sha256(raw).hexdigest() != packet["native_sha256"]:
        raise ValueError("native factor digest differs from the bound roof recording")
    document = json.loads(raw)
    cutoff = document["clock_anchor"]["before"]["realtime_ns"]
    archive = portable_v5.SnapshotArchive(packet["history"], cutoff, "/history")
    extract = portable_gate.make_arcs
    arc_digests = []

    def bind_arcs(document):
        arcs, counts = extract(document)
        record = [
            dict(
                channel=a.channel,
                rf_scale=a.scale,
                time_bin=a.time_bin,
                train_time=a.train_time.tolist(),
                train_y=a.train_y.tolist(),
                held_time=a.held_time.tolist(),
                held_y=a.held_y.tolist(),
            )
            for a in arcs
        ]
        arc_digests.append(
            hashlib.sha256(json.dumps(record, separators=(",", ":")).encode()).hexdigest()
        )
        return arcs, counts

    def before_cavity(prepared, _region, _bound, stages):
        return dict(status=prepared["status"], metrics=dict(stage_s=stages))

    with (
        patch.object(v5_core, "infer", before_cavity),
        patch.object(portable_gate, "retain_only", lambda _m, f: (f(), {})),
        patch.object(portable_gate, "make_arcs", bind_arcs),
    ):
        result = tile_region_empirical.run(
            document,
            tile=packet["tile"],
            archive=archive,
            bound=None,
            library=Path("/kernel/projector.so"),
        )
    gate = result["metrics"].get("geographic_gate")
    if gate is not None and len(arc_digests) != 1:
        raise ValueError("the frozen held-arc extraction was not captured exactly once")
    return dict(
        gate=gate,
        held_arc_sha256=arc_digests[0] if arc_digests else None,
        prior_result_status=result["status"],
        prior_result_reason=result.get("reason"),
        stages=result["metrics"].get("stage_s", {}),
        worker_cpu_s=process_time() - start,
        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
    )


if __name__ == "__main__":
    json.dump(run(json.load(sys.stdin)), sys.stdout, allow_nan=False, sort_keys=True)
