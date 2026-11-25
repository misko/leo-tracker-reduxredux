"""Price exact residual reuse and a primary-only radio search change from saved clocks."""

from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


ALGO = Path(__file__).resolve().parents[1]
FULL = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
LIVE = Path("/opt/leo-algo08/algo08v3/payload/receiver.so")
NATIVE = Path("/tmp/leo-algo08v2-2x-bench")
PROBES = {
    LIVE: FULL,
    NATIVE / "receiver-fractional-exact-v1/exact.so": FULL,
    NATIVE / "receiver-fractional-exact-v1/build.json": "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d",
    NATIVE / "spectral-vectors-combined-v1/packed/timing_first_receiver.c": "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a",
    NATIVE / "site-free-mode-pair-pgo/candidate/objects/two_carrier_receiver.c": "4f3326eee5522f02ee05a236f22a41fc1af5bb0f21b6e3fe337711a66226f5f7",
    NATIVE / "c803-packed-cancel-trial-v2/candidate/pilot_cancel.c": "34e186b48005ec68ad9a16024a691b12c9ad71d06e40985104ce086cf077d3f0",
    NATIVE / "c803-packed-cancel-trial-v2/candidate/pilot_cancel.o": "c7d370eef755ba71c225bf91992d94d79c6b2a886eea434ae6555179f2c9e316",
}
RECEIPTS = {
    "single-core-2x/receiver-cancel-support-results.json": "61b865634bebcad7e80705c7ee5e7701563c8f2fef21d921da13a9bc825f1e56",
    "single-core-2x/measurements/receiver-packed-cancellation.json": "27856b712905a8b51c7dfdae7893b59e183b21852914fa22ebedf5646c68eb78",
    "v3/measurements/receiver-jacobi-columns-0169.json": "5a047e9230905a906723e594eef5477e2d89dde5e69eecf20e2baede3dc62b12",
    "v3/measurements/ds30-0049-receiver-factorial.json.gz": "4af8b73101dce9b71a06b38a10e2484ef04b74f42b5221cfec1e818d21ea3b58",
    "v3/measurements/directed-verifier.json.gz": "dc132cbaac6cb3eddb21ec4c7df950b03eb1713461dac2d50ff0a92ac3e9a13b",
    "v3/measurements/all-full-receiver-frontier.json.gz": "0170159fb9835bf7f5ca8501275f8aa0d93195e8eac67cdf71c6b60be18e1aec",
}


def checked(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Changed archived input: {path}")
    return body


def load(path, pin):
    data = checked(path, pin)
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def readout():
    support, packed, stage, broad, directed, field = [load(ALGO / p, pin) for p, pin in RECEIPTS.items()]
    if (broad["admission.json"]["document"]["native"][str(LIVE)] != FULL
            or directed["build"]["installed_sha256"] != FULL or field["field_native_sha256"]["20ms_full"] != FULL):
        raise ValueError("The full native controls differ")
    census = [row for cohort in support["cohorts"].values() for row in cohort["cases"]]
    clean = Counter(row["actual"]["fir_clean"] for row in census)
    max_clean = max(row["actual"]["native_clean"] for row in census)
    unchanged_rows = sum(row["actual"]["clean_modes_rows"] for row in census)
    support_stats = dict(receiver_sha256=support["receiver_sha256"], scans=len(census),
                         exported_rank1=sum(row["second_factor"] for row in census),
                         fir_unchanged_counts=dict(sorted(clean.items())), min_native_changed_fraction=1-max_clean/200_000,
                         covariance_rows=14*len(census), unchanged_covariance_rows=unchanged_rows,
                         max_fir_reuse_fraction=max(clean)/50_000)

    full = stage["scopes"]["full20"]
    full_ns = median(row["shipped"]["native"]["full_cpu_ns"] for row in full["repeats"])
    paid_cancel = full["stages"]["scalar"]["trace"]["full"]["scouts"]-full["lane_calls"]
    packed_profile = packed["native"]["candidate-profile"]["profiles"][1]["cancel"]
    cap_ns = packed_profile["cpu_s"]*1e9 / packed_profile["calls"] * paid_cancel
    cancel = dict(donor_scope=packed_profile, original_shipped_cpu_ns=full_ns,
                  reached_cancellations=paid_cancel, original_lanes=full["lane_calls"],
                  projected_if_free_cpu_ns=cap_ns, projected_if_free_fraction=cap_ns/full_ns)

    lanes, sums = Counter(), {key:Counter() for key in ("empty", "primary_only", "with_residual")}
    for row in broad["native-rows.json"]["document"]:
        reference, primary = (row["alternatives"][key] for key in ("20-two", "20-primary"))
        if primary != [factor for factor in reference if factor["candidate_rank"] == 0]:
            raise ValueError("The primary helper ceased to reproduce the original rank-zero bytes")
        label = "empty" if not reference else ("with_residual" if any(f["candidate_rank"] == 1 for f in reference)
                                               else "primary_only")
        lanes[label] += 1
        for key in ("20-two", "20-primary"):
            cpu, elapsed = row["clocks"][key]
            sums[label].update({key+"_cpu_ns": cpu, key+"_elapsed_ns": elapsed})
    total = sum(sums.values(), Counter())
    work_ns = total["20-two_cpu_ns"]
    primary_ns = total["20-primary_cpu_ns"]
    difference = work_ns-primary_ns
    all_lanes = lanes.total()
    field_donor = field["direct_donors"]["DS30-0049"]["process_cpu_s_per_lane"]
    field_total_native = field["modeled_return_to_all_full"]["DS30-0049"]["modeled_native_s"]
    field_lanes = round(field_total_native / field_donor)
    lane_cap_ns = (field["baseline"]/2-field["mixed_outside_native_wall_s"])*1e9 / field_lanes
    positive_ns = work_ns - sums["empty"]["20-two_cpu_ns"]
    positive_difference = positive_ns - (primary_ns-sums["empty"]["20-primary_cpu_ns"])
    projected = dict(issued_lanes_modeled=field_lanes, conditional_all_native_cpu_ns_per_lane=lane_cap_ns,
                     paid_increment_at_free_primary_cpu_ns_per_lane=difference/all_lanes,
                     remaining_if_entire_primary_helper_free_ns_per_lane=lane_cap_ns-difference/all_lanes,
                     all_empty_free_preserve_positives_cpu_ns_per_lane=positive_ns/all_lanes,
                     all_empty_and_primary_free_cpu_ns_per_lane=positive_difference/all_lanes,
                     remaining_at_both_grants_ns_per_positive=(lane_cap_ns*all_lanes-positive_difference)/(all_lanes-lanes["empty"]))
    direct = {}
    for name, group in directed["groups"].items():
        row = group["checks"]["strict_decode"]
        if row["counts"]["byte_equal_lanes"] != group["lanes"]:
            raise ValueError("The directed oracle ceased to match original factor bytes")
        direct[name] = dict(lanes=group["lanes"], original_native_cpu_ms_mean=group["installed_cpu_ms"]["mean"],
                            exact_oracle_cpu_ms_mean=row["cpu_ms"]["mean"],
                            exact_oracle_stages_ms=row["mean_stages_ms"], counts=row["native_stage_counts"])
    return dict(support=support_stats, cancel=cancel, measured_native_delta_0049={"lane_counts": lanes, "all": total,
                "by_returned_outcome": sums}, field_price=projected, exact_oracle=direct, receipts=RECEIPTS)


if __name__ == "__main__":
    verified = {str(path): sha256(checked(path, pin)).hexdigest() for path, pin in PROBES.items()}
    print(json.dumps(dict(readout(), verified_sources=verified, new_waveform_reads=0, native_calls=0),
                     sort_keys=True, allow_nan=False, indent=2))
