"""Price exact full-aperture native work and solve work from saved clocks."""

import gzip
from math import fsum, inf, isclose
from pathlib import Path
from statistics import median
import json

from field_speed_reachability import checked
from first30_empty_call_roof import FULL, PINS as CALL_RECEIPTS, SPARSE, saved


HERE = Path(__file__).resolve().parent / "measurements"
PINS = {
    "installed-receiver-first30": "164da2b6c62ee9e6b60b4918ce937d8d37475808b53d8e5f3269be30c70a7153",
    "first30-empty-call-roof": "6edf7f54ff0689eb27712cad780d7539a9fa8dc7f95c3d7dd379641580225eeb",
    "installed-receiver-control-0016": "e825bc3bc7bed415a21a65b35a0b7b75e12e65f57dde32864bdae829234c193d",
}
RATES = (1., 2., 3., 4., 8., inf)


def load(name):
    return json.loads(gzip.decompress(checked(HERE / f"{name}.json.gz", PINS[name])))


def observed(baseline, totals):
    ratio = [other / original for original, other in zip(baseline, totals, strict=True)]
    total, half = fsum(totals), fsum(baseline)/2
    return dict(total=total, paired_median=median(ratio), summed=total/(2*half),
                over_half_total_s=total-half, cases_at_half=sum(r <= .5 for r in ratio))


def requirement(baseline, fixed, work):
    """Common finite stage acceleration needed; null means no finite value."""
    def value(scale):
        return observed(baseline, [a + scale*b for a, b in zip(fixed, work, strict=True)])

    all_free, original = value(0.), value(1.)
    guarantees = {}
    near_free = sorted((p/t, w/t) for t, p, w in zip(baseline, fixed, work, strict=True))
    middle = len(near_free)//2
    middle_slope = (near_free[middle][1] if len(near_free) % 2
                    else (near_free[middle-1][1]+near_free[middle][1])/2)
    for gate, slope in (("paired_median", middle_slope), ("summed", fsum(work))):
        if original[gate] <= .5:
            guarantees[gate] = 1.
        elif all_free[gate] > .5 or (all_free[gate] == .5 and slope > 0):
            guarantees[gate] = None
        else:
            lo, hi = 0., 1.
            for _ in range(55):
                scale = (lo+hi)/2
                if value(scale)[gate] <= .5:
                    lo = scale
                else:
                    hi = scale
            guarantees[gate] = 1/lo if lo else None
    return dict(at_original_speed=original, free_stage=all_free, required_rate=guarantees,
                both=None if None in guarantees.values() else max(guarantees.values()))


def enrolled():
    stock = load("installed-receiver-first30")
    mixed = load("first30-empty-call-roof")
    if (len(stock["cases"]) != 30 or len(mixed["cases"]) != 30
            or stock["combined_export"] != "sha256:" + mixed["rows_sha256"]
            or stock["direct_installed_acquisition_coverage"] != 0):
        raise ValueError("Expected the same 30 signed original field pairs")
    by_case = {x["case"]: x for x in mixed["cases"]}
    cases = []
    for original in stock["cases"]:
        c = by_case.pop(original["case"])
        p = original["phases"]
        solve = p["inventory_to_terminal_write"] + p["inventory_to_failed_exit"]
        scoped = (p["through_native_write"], p["native_to_inventory_write"], solve,
                  p["terminal_to_exit"], p["verifier"])
        native = fsum(row["elapsed_ns"]/1e9 for row in c["modes"].values())
        if (original["wall"] != c["paid_installed_s"] or original["cpu"] != c["paid_installed_cpu_s"]
                or original["lanes"] != 2*c["admitted"] or original["outcome"] != c["installed_outcome"]
                or not isclose(fsum(scoped), original["wall"], abs_tol=1e-7, rel_tol=0.)
                or not 0 <= native <= c["acquisition"]["elapsed_s"] <= c["paid_candidate_s"]):
            raise ValueError("Field receiver/solver phases do not reconcile to original paid boundaries")
        cases.append(dict(c, prefix=p["through_native_write"], combined_solver_span=solve,
                          installed_native_sha256=original["native"], installed_result_sha256=original["result"],
                          mixed_native_wall=native, mixed_outside_native=c["paid_candidate_s"]-native))
    return cases


def direct_donors():
    """All admitted lanes use original full DSO, with real short factors absent."""
    out = {}
    for case, row in saved("late-pilot-rescue").items():
        admit = row["admission.json"]
        full = row["long-receiver.json"]
        seal = row["sealed-long-receiver.json"]["document"]
        if (FULL not in admit["document"]["receivers"].values() or seal["long-receiver.json"] != full["source_sha256"]
                or seal["sealed-nominations.json"] != row["sealed-nominations.json"]["source_sha256"]
                or row["sealed-nominations.json"]["document"]["admission.json"] != admit["source_sha256"]):
            raise ValueError("All-full donor does not bind the measured call or installed binary")
        clocks = [hit["full_cpu_wall_ns"]["20-two"] for hit in full["document"]]
        out[case] = dict(calls=len(clocks), receipt_sha256=full["source_sha256"],
                         process_cpu_s_per_lane=fsum(x[0] for x in clocks)/len(clocks)/1e9,
                         wall_s_per_lane=fsum(x[1] for x in clocks)/len(clocks)/1e9)
    exact = load("installed-receiver-control-0016")
    native = exact["native_work"]
    calls = native["native_calls"]["full"]
    if (not exact["qualified"] or not exact["science_exact"] or calls != out["DS30-0016"]["calls"]
            or exact["candidate"]["native_sha256"] != exact["stock_archival"]["native_sha256"]
            or exact["candidate"]["receiver_recipe"]["detector_sha256"] != FULL
            or exact["candidate"]["receiver_recipe"]["schedule"] != "all"):
        raise ValueError("The chronological all-full verification case differs from installed output")
    out["exact_chronological_DS30-0016"] = dict(calls=calls, native_sha256=exact["candidate"]["native_sha256"],
                       thread_cpu_s_per_lane=native["native_cpu_ns"]["full"]/calls/1e9,
                       native_wall_s_per_lane=native["native_wall_ns"]["full"]/calls/1e9,
                       installed_wall=exact["stock_archival"]["process"]["clock"]["elapsed_s"],
                       charted_receiver_acquisition=exact["candidate"]["phases"]["authenticated_raw_acquisition"])
    return out


def assess(cases, native):
    base = [c["paid_installed_s"] for c in cases]
    # The modeled arithmetic cannot occupy more than the actually measured prefix.
    # No case hits this cap in the enrolled 30 at any donor or anchor rate.
    old = [min(c["prefix"], n) for c, n in zip(cases, native, strict=True)]
    fixed_stock = [old_total-n for old_total, n in zip(base, old, strict=True)]
    solve = [c["combined_solver_span"] for c in cases]
    outside_both = [f-s for f, s in zip(fixed_stock, solve, strict=True)]
    outside_mixed = [c["mixed_outside_native"] for c in cases]
    grid = {}
    for speed in RATES:
        tag = "free" if speed == inf else str(int(speed))
        left = [p+n/speed for p, n in zip(outside_both, old, strict=True)]
        chart = [p+n/speed for p, n in zip(outside_mixed, native, strict=True)]
        grid[tag] = dict(installed=requirement(base, left, solve), charted=observed(base, chart))
    return dict(modeled_native_s=fsum(native), modeled_native_per_case=native,
                clipped_at_installed_prefix=sum(n != p for n,p in zip(native,old,strict=True)),
                installed_if_only_native_changes=requirement(base, fixed_stock, old),
                installed_native_requirement_with_free_solver=requirement(base, outside_both, old),
                charted_same_outside_native=requirement(base, outside_mixed, native),
                charted_native_2x_minimum_additional_wall_cut_fraction_of_outside_native=(
                    max(0., grid["2"]["charted"]["over_half_total_s"])/fsum(outside_mixed)),
                frontier=grid)


def study():
    cases, rates = enrolled(), direct_donors()
    base = [c["paid_installed_s"] for c in cases]
    donor = {key: [2*c["admitted"]*(rate.get("thread_cpu_s_per_lane") or rate["process_cpu_s_per_lane"])
                   for c in cases] for key, rate in rates.items()}
    donor["exact_chronological_DS30-0016_callback_wall"] = [
        2*c["admitted"]*rates["exact_chronological_DS30-0016"]["native_wall_s_per_lane"] for c in cases]
    for label, key in (("same_field_anchor_process_cpu", "process_cpu_ns"),
                       ("same_field_anchor_callback_wall", "elapsed_ns")):
        donor[label] = [2*c["admitted"]*c["modes"]["full"][key]/c["modes"]["full"]["lanes"]/1e9 for c in cases]
    current = {}
    for key in ("elapsed_ns", "process_cpu_ns"):
        paid = [fsum(m[key] for m in c["modes"].values())/1e9 for c in cases]
        rest = [c["paid_candidate_s"]-n for c,n in zip(cases,paid,strict=True)]
        current[key] = dict(native_s=fsum(paid), requirements=requirement(base, rest, paid),
                            needed_saving_fraction_of_work=observed(base,[c["paid_candidate_s"] for c in cases])["over_half_total_s"]/fsum(paid))
    inputs = PINS | {"late-pilot-rescue": CALL_RECEIPTS["late-pilot-rescue"]}
    return dict(inputs=inputs, field_native_sha256={"20ms_full": FULL, "8ms_short": SPARSE},
                cases=[c["case"] for c in cases], baseline=fsum(base),
                observed_mixed=observed(base,[c["paid_candidate_s"] for c in cases]),
                installed_solver_and_terminal_spans_s=fsum(c["combined_solver_span"] for c in cases),
                mixed_outside_native_wall_s=fsum(c["mixed_outside_native"] for c in cases),
                actual_current_mix_common_native=current, direct_donors=rates,
                modeled_return_to_all_full={key: assess(cases, value) for key,value in donor.items()},
                new_native_calls=0, new_solves=0, waveform_orbit_reads=0)


if __name__ == "__main__":
    print(json.dumps(study(), indent=2, sort_keys=True, allow_nan=False))
