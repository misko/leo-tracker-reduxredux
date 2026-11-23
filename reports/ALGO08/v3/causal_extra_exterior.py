"""Test the released exterior rule on sealed sparse packets with interior endpoints."""

import argparse
import gzip
import json
from pathlib import Path
from time import perf_counter, process_time

from aperture_trial import archive_identity, configuration, machine, write
from causal_extra import choose
from interlaced_lanes import quadratic_run
from paid_graph_trial import prepare_paid
from paid_quadratic import quadratic
from sparse_consensus_trial import CASES, bound_inputs


def inspect_all(endpoints, width_km, score, *, terminal_only=False):
    from tools.pipeline_eval.variants.experimental.regional_bound_guard import bound_arms, evaluate

    arms = bound_arms(endpoints, width_km)
    if arms is None:
        raise ValueError("Invalid endpoint for sparse regional check")
    scored = score()
    diagnostic = scored if terminal_only else evaluate(scored, width_km)
    return dict(bound_arms=arms, evaluated=True, **diagnostic)


def measure(case):
    configuration()
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants.experimental.regional_bound_guard import causal_probes

    saved = Path(__file__).parent / "measurements/causal-extra.json.gz"
    source = json.loads(gzip.decompress(saved.read_bytes()))[case]["causal_extra"]
    native, rows, _, clocks, archive, offer, identity = bound_inputs(case)
    packet, config, _ = prepare_paid(native, rows, clocks, identity, "causal_extra", select_paid=choose)
    if (canonical_digest(packet) != source["identity"]["native_sha256"]
            or offer != source["identity"]["offer"] or source["identity"]["archive"] != archive_identity(archive)):
        raise ValueError("Detector, region or archive changed before the probe")
    cpu = process_time()
    tracks = prepare_tracks(packet, quadratic(config))
    prep = process_time() - cpu
    region = Algo08Region.parse(offer)
    cpu, wall = process_time(), perf_counter()
    score = causal_probes(tracks, TleArchiveReader(archive), SearchRegion(region.center, region.width_km),
                          terminal_only=True)
    return dict(case=case, original=source["attempts"][0]["exterior"], native_sha256=canonical_digest(packet),
                graph_cpu_s=prep, probe_cpu_s=process_time()-cpu, probe_elapsed_s=perf_counter()-wall,
                result=score, machine=machine())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("case", choices=CASES)
    p.add_argument("output", type=Path)
    p.add_argument("--integrated", action="store_true")
    a = p.parse_args()
    if a.integrated:
        quadratic_run(a.case, "causal_extra_checked", choose, a.output, inspect_region=inspect_all)
    else:
        write(a.output, measure(a.case))
