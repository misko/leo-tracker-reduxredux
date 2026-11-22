"""Check an exact terminal-only veto on stored probes and time one saved guard stage."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from tools.pipeline_eval.variants.experimental import regional_reassignment
from tools.pipeline_eval.variants.experimental.regional_exterior_veto import evaluate
from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

from .regional_exterior_veto_trial import PINS, saved_offers


def replay(row):
    points, width = row["points"], row["offer"]["width_km"]
    result = evaluate_terminal(points, width, lambda point: point["receiver_scores"])
    reference = evaluate(points, width)
    if (result["would_withhold"] != reference["would_withhold"]
            or (result["complete"] and any(result[key] != value for key, value in reference.items()))):
        raise ValueError("Terminal veto differs from the full archived solver rule")
    return result


def time_north(row, native, archive, config):
    from leo.analysis.localization_v3.elements import ElementParser
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import _json_value
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader

    raw = native.read_bytes()
    if sha256(raw).hexdigest() != row["native_sha256"].removeprefix("sha256:"):
        raise ValueError("Expected the original northern saved detections")
    config_bytes = config.read_bytes()
    settings = TrackConfig(**json.loads(config_bytes)["config"])
    prepared = prepare_tracks(json.loads(raw), settings)
    prepared = json.loads(json.dumps(prepared, default=_json_value, allow_nan=False))
    catalogue = causal_catalogue(
        TleArchiveReader(archive), prepared["metadata"]["causal_cutoff_utc_ns"],
        element_parser=ElementParser(),
    )
    snapshots = sorted({r["snapshot_digest"] for r in catalogue.provenance})
    if snapshots != row["snapshots"]:
        raise ValueError("Causal catalogue differs from the archived guard")
    width = row["offer"]["width_km"]
    region = SearchRegion(tuple(row["offer"]["center"]), width)
    start = process_time()
    full = regional_reassignment.evaluate(prepared, catalogue.catalogue, region)
    reference = evaluate(full["points"], width)
    full_cpu = process_time() - start
    start = process_time()
    fast = regional_reassignment.evaluate_veto(prepared, catalogue.catalogue, region)
    fast_cpu = process_time() - start
    if any(value != row[key] for key, value in json.loads(json.dumps(full)).items()):
        raise ValueError("Full score rows differ from published evidence")
    archived = replay(row)
    if fast["would_withhold"] != reference["would_withhold"] or any(
            fast[key] != value for key, value in archived.items()):
        raise ValueError("The live short-circuit differs from the archived test")
    meta = {key: value for key, value in full.items() if key != "points"}
    if any(fast[key] != value for key, value in meta.items()):
        raise ValueError("The two scorers differ on the all-location catalogue and track support")
    return dict(full_cpu_s=full_cpu, terminal_cpu_s=fast_cpu, full_probes=len(full["points"]),
                terminal_probes=fast["probes_evaluated"], metadata=meta, snapshots=snapshots,
                native_sha256=row["native_sha256"], track_config_sha256=sha256(config_bytes).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time-north", nargs=3, type=Path, metavar=("DETECTIONS", "TLE", "TRACK_CONFIG"))
    args = parser.parse_args()
    saved = saved_offers()
    output = dict(input_pins=PINS, results={name: replay(row) for name, row in saved.items()})
    if args.time_north is not None:
        output["north_inside_stage"] = time_north(saved["north-edge"], *args.time_north)
    print(json.dumps(output, indent=2, allow_nan=False))
