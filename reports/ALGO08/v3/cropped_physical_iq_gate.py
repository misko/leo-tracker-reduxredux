"""Screen the fixed dense crop at the deployed Graph and curvature boundary."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

SOURCE = Path("/tmp/ds30-v2-stage-all-6cdbac/DS30-0008/candidate/fast-scan-automatic-work/") / (
    "algo08-v2-3dce9426edd1831eade2003d69a00297/detections.json")
SOURCE_SHA256 = "2df28e68ea845576ea5e8a02057bce32983dbafb469fa2c4f710a3d89729fa85"
DETECTOR = "sha256:2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
INVENTORY = "sha256:3f08c51c74fa878e0b5993311a840172c2b06d2d0be02988d13f0c29f502034b"
AUTHORITY = "sha256:0dae376992a498e155dfb306761d56619e647eb5532050e9d7ffed36a7793d48"
MEMBER_VISITS = 64


def project(native, members, canonical_digest, inventories, select_document):
    provenance, source = native["provenance"], native["source"]

    def signature(rows):
        return canonical_digest(["cancellation", AUTHORITY, DETECTOR[7:], rows])

    if (provenance["detector_sha256"] != DETECTOR or source["raw_recording_authority_digest"] != AUTHORITY
            or source["input_manifest_sha256"] != INVENTORY or signature(source["probes"]) != source["analysis_manifest_sha256"]):
        raise ValueError("The full native detector packet must remain the authenticated named DS30 input")
    issued = {visit for member in members for visit in range(member*MEMBER_VISITS, (member+1)*MEMBER_VISITS)}
    kept = [visit for visit, _ in inventories(native) if visit in issued]
    excluded = {row["visit"] for row in provenance["excluded_windows"]} & issued
    if set(kept) | excluded != issued:
        raise ValueError("The frozen diagnostic requires every original visit of each member to be accounted for")
    projected = select_document(native, kept, source["analysis_manifest_sha256"])
    digest = signature(projected["source"]["probes"])
    projected["source"]["analysis_manifest_sha256"] = digest
    projected["provenance"]["run_id"] = "cropped-graph-"+digest[7:35]
    return projected, kept, len(excluded)


def screen(native, members, assets):
    from leo.analysis.localization_v3 import tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.capture_bursts import inventories, select_document
    from empty_bootstrap import checked
    from short_graph_guard import RELEASE_PINS, TRACKS, TRACK_CONFIG, prove, time_support

    checked(Path(tracks.__file__), RELEASE_PINS[TRACKS])
    config = json.loads(checked(assets/"tracks.json", TRACK_CONFIG))["config"]
    document, kept, excluded = project(native, members, canonical_digest, inventories, select_document)
    cpu, wall = process_time(), perf_counter()
    proof = prove(document, assets, use_time_support=True, use_curvature_extent=True)
    result = tracks.prepare_tracks(document, TrackConfig(**config))
    bounds = {key: config[key] for key in ("min_span_s", "max_gap_s")}
    support = time_support(result["observations"], config["min_points"], **bounds)
    keep = set(kept)
    rows = [r for r in document["source"]["probes"] if r["visit_index"] in keep]
    durations = [row["end_s"]-row["start_s"] for row in result["tracks"]]
    return dict(members=members, issued_visits=len(kept)+excluded, admitted_visits=len(kept), excluded_visits=excluded,
                nominal_packet_issued=native["provenance"]["window_count"],
                source_sha256=SOURCE_SHA256, selected_rows_sha256=canonical_digest(rows),
                projection_sha256=canonical_digest(document), clock_anchor_retained=document["clock_anchor"] == native["clock_anchor"],
                delivery_ledger_retained=document["delivery_clocks"] == native["delivery_clocks"],
                lane_calls_available=len(rows), receiver_candidates=sum(len(r["candidates"]) for r in rows),
                candidates_by_member=dict(Counter(r["visit_index"]//MEMBER_VISITS for r in rows if r["candidates"])),
                signed_graph_source_sha256=RELEASE_PINS[TRACKS], config=proof.get("track_config_sha256"),
                status=result["status"], curves=len(result["curved_indices"]), tracks=len(durations),
                longest_track_s=max(durations, default=0), graph_points=result["graph_points"],
                winning_observations=len(result["observations"]), lane_temporal_bound=support, proof=proof,
                paid_cpu_s=process_time()-cpu, paid_elapsed_s=perf_counter()-wall)


def run(output, *, design=False):
    from empty_bootstrap import RELEASE, checked
    sys.path.insert(0, str(RELEASE/"src"))
    from dense_geographic_trial import host

    machine = host()
    if output.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a new tmpfs receipt")
    native = json.loads(checked(SOURCE, SOURCE_SHA256))
    assets = RELEASE/"assets"
    if design:
        prespecified = ((0, 2, 4, 6, 8), tuple(range(8)), tuple(range(16)))
        runs = [screen(native, members, assets) for members in prespecified]
    else:
        pair = screen(native, (0, 7), assets)
        runs = [pair]
        if pair["status"] != "tracks_prepared":
            runs.append(screen(native, (0, 3, 7), assets))
    with output.open("x") as stream:
        json.dump(dict(machine=machine, scope="projected named signed detector packet through exact Graph only",
                       fixture_design=design,
                       waveform_reads=0, archive_reads=0, inference_runs=0, runs=runs),
                  stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--design", action="store_true")
    args = cli.parse_args()
    run(args.output, design=args.design)
