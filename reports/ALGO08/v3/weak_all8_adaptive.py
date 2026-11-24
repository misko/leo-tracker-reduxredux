"""Validate one full saved weak 20/8 ms publication with the adaptive research map."""

import argparse
import gzip
from hashlib import file_digest, sha256
import json
from pathlib import Path
from statistics import median, quantiles
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = Path("/dev/shm/leo-v3-weak-all8-combined/reports/ALGO08/v3")
CONTROL = Path("/dev/shm/leo-v3-weak-all8-combined-result02")
NAMED = Path("/dev/shm/leo-v3-raw-0016-best-results-01/stock")
NATIVE = "sha256:aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac"
NAMED_DATA = "33d6cab032ab19f6093d57d6017be32820d479e5e96c082a21b40d4ea75824c0"
BUILD_CLOCK = "ea78ecc07d20b61b5f3473d08f849efe178df093c53c095fa9a7a0d6152993f2"
PINS = {
    "binding.json": "c1e38e1ee9c27f0365672e19a96a4fe27f8d18e70044e76878a1f75d101e05b3",
    "clock.json": "d87ab46c9aa350f332043ff0eb280f1ec8e54496b20906f7c21d6789a3247f84",
    "seal.json": "b29c1e288400792af10176f5936fce7206ba7d5f5c817cf214ce08ad800e7cfc",
    "score.json": "4cd673e85915c59b1e5611cdaedbcb0ec9ca4b971ec56706cbd9d27bbec1a61f",
}
RECEIPT_FIELDS = ("run_id", "session_id", "window_count", "counts", "region", "decision", "terminal_sha256")
ARMS = ("c0", "fitted_c")
sys.path[:0] = [str(SOURCE), str(HERE.parents[2])]


def read(path, expected=None):
    data = path.read_bytes()
    if expected is not None and sha256(data).hexdigest() != expected:
        raise ValueError(f"Enrolled artifact changed at {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def pin(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def write(path, document):
    with path.open("x") as out:
        json.dump(document, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


def enrollment():
    import weak_all8_combined as weak
    from combined_raw_trial import PRODUCER, checked_producer

    details = {name: read(CONTROL/name, digest) for name, digest in PINS.items()}
    original = details["seal.json"]
    sources = details["binding.json"]["sources"]
    if (sources != weak.pins() or details["clock.json"]["exit_code"] or not all(original["parity"].values())
            or original["execution"]["identity"]["native_sha256"] != NATIVE
            or original["published"]["solve"]["grid_points"] != 179):
        raise ValueError("Require the original sealed and identical-source 4.166 s full-layout reference")
    producer = checked_producer(original["execution"]["identity"]["cutoff_utc_ns"])
    producer["build_clock"] = read(PRODUCER.file.parent/"dense-export-clock.json", BUILD_CLOCK)
    if producer["build_clock"]["exit_code"]:
        raise ValueError("Portable producer timing failed")
    return details, producer


def live_pins():
    return {x.name: pin(x) for x in (Path(__file__), HERE/"weak-all8-adaptive-protocol.md",
                                  HERE/"live_adaptive_grid.py", HERE/"live_adaptive_grid_entry.py")}


def worker(root):
    import raw_cfo_north_trial as port
    import weak_all8_combined as weak
    from reports.ALGO08.v3.live_adaptive_grid_entry import research_layout

    if read(root/"adaptive-binding.json")["sources"] != live_pins():
        raise ValueError("Adaptive experiment sources changed after freezing")
    original = port.publish_saved

    def adaptive(request, target, *args, **kwargs):
        if target != root/"candidate":
            raise ValueError("The candidate may only write its own research namespace")
        with research_layout(target):
            return original(request, target, *args, **kwargs)

    with patch.object(port, "publish_saved", adaptive):
        weak.worker(root)


def launch(root):
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm") or root.exists():
        raise ValueError("Use a fresh tmpfs scope")
    control, producer = enrollment()
    root.mkdir()
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for file in (CONTROL/"fonts").glob("fontlist-*.json"):
        (root/"fonts"/file.name).hardlink_to(file)
    argv = ["/usr/bin/timeout", "--kill-after=2s", "35s", RELEASE/"venv/bin/python", "-IB", Path(__file__), "worker", root]
    write(root/"binding.json", control["binding.json"])
    write(root/"adaptive-binding.json", dict(sources=live_pins(), host=host(), control=PINS, producer=producer,
           command=list(map(str, argv)), source_authority="original signed 20/8 ms acquisition"))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    clock = measure(argv, env, root/"candidate")
    write(root/"clock.json", clock)


def receive_tails(before, after):
    def sites(data):
        results = {}
        for row in data["source"]["probes"]:
            key = row["receiver_id"], row["valid_start_counter"]
            if key in results:
                raise ValueError("Duplicate original receiver opportunity")
            choices = [c for c in row["candidates"] if c["passed_fractional_margin_gate"]]
            peak = max(choices, key=lambda c: (c["fractional_margin"], -c["candidate_rank"])) if choices else None
            results[key] = (row["channel"], row["actual_rf_hz"], row["edge"],
                            None if peak is None else peak["fractional_tracking_cfo_hz"])
        return results

    original, candidate = sites(before), sites(after)
    if original.keys() != candidate.keys() or any(original[k][:3] != candidate[k][:3] for k in original):
        raise ValueError("Archived receivers must cover identical native lane opportunities")
    rows = {}
    for radio in sorted({r for r, _ in original}):
        common = [k for k in original if k[0] == radio and original[k][3] is not None and candidate[k][3] is not None]
        shifts = [abs(original[k][3]-candidate[k][3]) for k in common]
        rows[str(radio)] = dict(original_positive=sum(k[0] == radio and v[3] is not None for k, v in original.items()),
                               candidate_positive=sum(k[0] == radio and v[3] is not None for k, v in candidate.items()),
                               common=len(common), median_abs_cfo_delta_hz=median(shifts) if shifts else None,
                               p95_abs_cfo_delta_hz=quantiles(shifts, n=100, method="inclusive")[94] if len(shifts)>1 else max(shifts, default=None),
                               max_abs_cfo_delta_hz=max(shifts, default=None), beyond_250_hz=sum(v > 250 for v in shifts))
    return rows


def budget(original, acquisition, new, build):
    total = acquisition+new
    target = original/1.6
    return dict(historical_raw_acquisition_s=acquisition, fresh_saved_s=new, separate_clock_total_s=total,
                modeled_ratio=original/total, target_1p6_elapsed_s=target, saved_allowance_s=target-acquisition,
                target_gap_s=total-target, earlier_index_build_s=build, optional_serial_first_use_sum_s=total+build)


def score(root):
    from weak_all8_combined import disjoint
    from joint_publication import figure_evidence
    from leo.contracts.digests import canonical_digest, sha256_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from reports.ALGO08.v3.live_adaptive_grid import quality
    from reports.ALGO08.v3.live_adaptive_grid_entry import read_manifest, read_sidecar, research_folder

    controls, producer = enrollment()
    archived, geography = controls["seal.json"], controls["score.json"]
    clock, observed = read(root/"clock.json"), read(root/"execution.json")
    folder, stock_folder = root/"candidate", CONTROL/"candidate"
    full_trace, trace = (read(x/"joint-research-receipt.json") for x in (stock_folder, folder))
    published = read(folder/"all8-combined-publication.json")
    old_receipt, receipt = archived["published"]["receipt"], published["receipt"]
    run = receipt["run_id"]
    term, old_term = [read(x/"fast-scan-automatic-work"/run/"terminal.json") for x in (folder, stock_folder)]
    keys = ("choice", "refinement_calls", "would_refine", "would_refine_by_radio", "would_refine_stereo_visits", "native_sha256", "selected")
    old = archived["execution"]
    prep, = observed["orbit"]["transfers"]
    shape, = observed["orbit"]["attempts"]
    if (clock["exit_code"] or not published["staged_inventory"] or published["waveform_calls"] or published["handoffs"] != 1
            or archived["published"]["named_survivor_finish"] != published["named_survivor_finish"]
            or not published["named_survivor_finish"]["paid_final_fit"] or observed["identity"] != old["identity"]
            or any(observed["selection"][k] != old["selection"][k] for k in keys) or observed["original_native_sha256"] != old["original_native_sha256"]
            or any(receipt[k] != old_receipt[k] for k in RECEIPT_FIELDS) or term != old_term
            or canonical_digest(term) != receipt["terminal_sha256"] or trace["selected_rows"] != full_trace["selected_rows"]
            or trace["solve"]["objective_replay"] != full_trace["solve"]["objective_replay"]
            or trace["early_regional"][0]["result"] != full_trace["early_regional"][0]["result"]
            or prep["compatibility"]["fallback"] or prep["loading"]["fallback"] or shape["fallback"]
            or prep["counts"]["sidecar_hit_bodies"] != 19 or prep["counts"]["cold_bodies"] != 1
            or observed["rank_status"] != "compacted" or observed["rank"]["counts"]["compact_calls"] != 48):
        raise ValueError("The candidate needs the exact original saved route, both-arm outputs and held selection")
    if (published["png"]["verified"] != 8 or published["png"]["reused"] != 8 or published["png"]["fallbacks"]
            or (folder/"fast-scan-standard-v2").exists()):
        raise ValueError("Expected eight verified adaptive figures in the distinct research namespace")
    store = FastStandardAnalysisStore(stock_folder)
    original, previous_path = store.position_grid(run), store.position_path(run)
    research = read_manifest(folder, run)
    adaptive, path = (read_sidecar(folder, run, name) for name in ("sample", "path"))
    for row in (previous_path, path):
        row["binding"].pop("position_png_sha256")
    for grid, version in ((original, full_trace), (adaptive, trace)):
        expected = 2*grid["evaluated_points"]-2
        counters = version["receipt"]["posterior_grid_handoff"]
        if [counters["factor_calls"], counters["prediction_calls"]] != [expected, expected]:
            raise ValueError("Exact native grid calculation did not cover every paid non-endpoint evaluation")
    original_arms = {arm: {k: v for k, v in row.items() if k != "evaluation_error_m"}
                     for arm, row in store.detail(run)["arms"].items()}
    if (research["publication"]["arms"] != original_arms or path != previous_path
            or adaptive["endpoint_latlon"] != original["endpoint_latlon"]):
        raise ValueError("Adaptation changed published estimates, diagnostics or path")
    audit = quality(adaptive, original)
    for arm, comparisons in audit["arms"].items():
        low = comparisons["minimum"]+4.5
        def count_low(layout):
            return sum(row["scores"][arm] is not None and row["scores"][arm] <= low for row in layout["points"])

        comparisons["full_low_nodes"] = count_low(original)
        comparisons["retained_low_nodes"] = count_low(adaptive)
    images = {}
    for entry in research["publication"]["artifacts"]:
        digest, name = entry["sha256"], entry["name"]
        raw = (research_folder(folder, run)/(digest[7:]+".png")).read_bytes()
        measured = figure_evidence(raw, sha256_digest(raw))
        expected = full_trace["evidence"]["images"][name]
        if (measured["sha256"] != digest or list(measured["size"]) != expected["size"]
                or name != "position" and any(measured[k] != expected[k] for k in ("sha256", "rgba_sha256"))):
            raise ValueError(f"The research map changed an unrelated image or image dimensions: {name}")
        images[name] = measured
    target = read(SOURCE/"measurements/raw-0016-best.json.gz", NAMED_DATA)["original"]["stock"]
    raw, = NAMED.glob("fast-scan-automatic-work/*/detections.json")
    named_native = read(raw, target["native_file_sha256"])
    saved_native = read(root/"selected-detections.json", NATIVE[7:])
    if (named_native["source"]["raw_recording_authority_digest"] != saved_native["source"]["raw_recording_authority_digest"]
            or target["science"]["receipt"]["region"] != receipt["region"]
            or named_native["clock_anchor"]["before"]["realtime_ns"] != observed["identity"]["cutoff_utc_ns"]):
        raise ValueError("The deployed v3 named reference does not match original authority, cutoff and offer")
    output = dict(clock=clock, standard_clock=controls["clock.json"], named_clock=geography["original_v3"],
                  binding=read(root/"adaptive-binding.json"), held=observed["selection"], declared=receipt["counts"],
                  reused_portable=prep, prepared_orbits=shape, index_producer=producer, terminal_sha256=receipt["terminal_sha256"],
                  owner_rows_sha256=canonical_digest(trace["selected_rows"]), roles=trace["selected_roles"],
                  positions=geography["scientific_arms"], named_owners=target["owner_counts"], named_factors=target["factors"],
                  cfo_tails=receive_tails(named_native, saved_native), decision=receipt["decision"],
                  adaptive_grid={k:v for k,v in adaptive.items() if k != "points"}, audit=audit,
                  standard_grid_elapsed_s=original["elapsed_seconds"], images=images,
                  solve=published["solve"], render=published["layout"]["render"], raw_waveform_reads=0,
                  disjoint_saved_costs=disjoint(clock, observed["phases"], published["solve"], published["layout"]["render"]),
                  regional={k:v for k,v in trace["early_regional"][0]["result"].items() if k != "snapshots"})
    proof = published["graph_proof"]
    extent = proof["curvature_extent"]
    output["no_active_curve_gate"] = dict(minimum_points=proof["minimum_points"], winning_rows=proof["winning_rows"],
                                          proven=proof["proven"], curvature_extent={k:extent[k] for k in
                                          ("largest_lane_span_s", "required_track_span_s", "proven")})
    output["scorer_sha256"] = pin(Path(__file__))
    output["separate_clock_model"] = {key: budget(geography["original_v3"][key], geography["historical_raw_8ms_acquisition"][key],
                                                  clock[key], producer["build_clock"][key]) for key in ("elapsed_s", "cpu_s")}
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--score-output", type=Path)
    args = parser.parse_args()
    if args.action == "score":
        write(args.score_output or args.root/"result.json", score(args.root))
    else:
        (launch if args.action == "launch" else worker)(args.root)
