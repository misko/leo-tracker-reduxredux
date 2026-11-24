"""Audit the frozen signed receiver's transform dependencies and saved CPU budget."""

from collections import Counter
import gzip
from hashlib import sha256
import json
from math import ceil, floor, log2
from pathlib import Path
import re

from all_full_receiver_frontier import load as first30
from field_speed_reachability import checked
from first30_empty_call_roof import FULL, SPARSE


HERE = Path(__file__).resolve().parent
BENCH = Path("/tmp/leo-algo08v2-2x-bench")
SHORT = Path("/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse")
SHORT_VERIFIER = Path("/var/tmp/leo-v3-eight-ms-build-padded/scouts/8ms/portable_verifier.c")
FULL_SOURCE = BENCH / "spectral-vectors-combined-v1/packed/timing_first_receiver.c"
FULL_BUILD = BENCH / "receiver-fractional-exact-v1"
FULL_DSO = Path("/opt/leo-algo08/algo08v3/payload/receiver.so")
PINS = {
    "full_timing_source": "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a",
    "full_build": "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d",
    "short_timing_source": "10d8ec75ac2d6e820dd9cee184b2825b8d6510a465bbb8bfa38fc782126daea5",
    "short_verifier_source": "bae3798db85b2682ae88d7ce545aac0d084c5f3a747d34cf5c43edd908e0996b",
    "short_verifier_object": "51f37c4be088bfd51b26d27cba18d236e238ceb12a2af2d9f5e855074e2db590",
    "sample-major-fft": "7246950b055aff2323b4539208e0d7e45924e132d67a33880245dc77a77243d7",
    "carrier-bound": "a00c64e73bc0a99d209fd0d0eb2d507d61fe8c93dff5612be14e4c099683fc7d",
}


def eligible_bins(size, rate, center, half_width):
    """Mirror the signed alias eligibility order, including cyclic bins."""
    lo, hi = center-half_width, center+half_width
    result = []
    for i in range(size):
        f = (i if i < size//2 else i-size) * float(rate) / size + center
        if ceil((lo-f)/rate) <= floor((hi-f)/rate):
            result.append(i)
    return result


def layout(selected, size, inner):
    """Any demanded residue requires that bin from every DIT child transform."""
    if size % inner or any(k < 0 or k >= size for k in selected) or len(set(selected)) != len(selected):
        raise ValueError("Expected valid unique output bins of a divisible transform")
    by_residue = Counter(k % inner for k in selected)
    return dict(subtransform_length=inner, subtransforms=size//inner,
                requested_residues=len(by_residue),
                wanted_outer_outputs_per_residue=dict(Counter(by_residue.values())),
                unused_output_bins=size-len(selected))


def numbers(source):
    fields = dict(re.findall(r"\b(points|count|clocks|lags|bins|choices) = (\d+),", source))
    if (len(fields) != 6 or "w->correlation_size = 19200 / stride;" not in source
            or "len = 64 * symbol / w->stride" not in source
            or "w->epochs = (int)nearbyint(w->rate / 750.);" not in source
            or "w->rate = 10000000 / stride;" not in source):
        raise ValueError("Unexpected original receiver geometry")
    return {k: int(v) for k, v in fields.items()}


def source_contract():
    build = json.loads(checked(FULL_BUILD/"build.json", PINS["full_build"]))
    if build["exact_sha256"] != FULL:
        raise ValueError("Full timing object is not from the original binary relink")
    checked(FULL_DSO, FULL)
    checked(FULL_SOURCE.with_suffix(".o"), build["parent_objects"]["timing_first_receiver.o"])
    checked(SHORT/"use.so", SPARSE)
    full = checked(FULL_SOURCE, PINS["full_timing_source"]).decode()
    short = checked(SHORT/"timing_first_receiver.c", PINS["short_timing_source"]).decode()
    checked(SHORT_VERIFIER.with_suffix(".o"), PINS["short_verifier_object"])
    verified_sources = {"full": checked(FULL_BUILD/"portable_verifier.c", build["verifier_source_sha256"]),
                        "short": checked(SHORT_VERIFIER, PINS["short_verifier_source"])}
    if ("sparse_carrier_power" in full or "sparse_carrier_power(&sweep" not in short
            or any("transform(w, bins, 0)" not in source for source in (full, short))
            or any(b"short_size = 128, glrt_size = 512" not in body
                   or b"for (int k = 0; k < glrt_size; ++k)" not in body for body in verified_sources.values())):
        raise ValueError("Original scout or GLRT branch changed")
    return dict(full=numbers(full), short=numbers(short), detector_sha256=dict(full=FULL, short=SPARSE),
                verifier_source_sha256={k: sha256(body).hexdigest() for k,body in verified_sources.items()})


def pricing():
    fft = json.loads(checked_gzip("sample-major-fft"))
    fields = ("carrier_forward", "lag_forward", "lag_inverse")
    if fft["identity"]["full"]["stock"] != FULL:
        raise ValueError("The paid transform donor lost its installed full identity")
    results = {}
    for aperture, scans in (("short", (0,)), ("full", (0, 1))):
        for field in fields:
            for scan in scans:
                row = fft["batches"][f"{aperture}/{field}/{scan}/2"]
                if (row["lanes"] != 2 or not row["groups"]
                        or (field == "carrier_forward" and "dft-ct-dit/32" not in row["plans"][0])):
                    raise ValueError("The comparator must be the scalar original-aligned transform")
                results[f"{aperture}/{field}/{scan}"] = dict(
                    per_transform_ns=row["kernel_cpu_ns"][0]/(row["groups"]*row["lanes"]),
                    measured_transforms=row["groups"]*row["lanes"], scalar_plan=row["plans"][0])
    return dict(identity=fft["identity"], clocks=results)


def checked_gzip(name):
    return checked_uncompressed(gzip.decompress((HERE/"measurements"/f"{name}.json.gz").read_bytes()), name)


def checked_uncompressed(data, name):
    if sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f"Changed original receipt for {name}")
    return data


def old_screen():
    history = json.loads(checked(HERE/"measurements/carrier-bound.json", PINS["carrier-bound"]))
    if history["reference"] != FULL:
        raise ValueError("Retrospective carrier bound was measured on another detector")
    cost_of_coarse = 2048*log2(2048)/(4096*log2(4096))
    out = {}
    for case in ("weak", "south"):
        sections = [history[case][name] for name in ("primary", "residual")]
        coarse = [r["2048-bounds-first"] for r in sections]
        total = sum(r["epochs"] for r in coarse)
        full = sum(r["full"] for r in coarse)
        best = sum(min(r["coarse"]*cost_of_coarse+r["full"] for order,r in section.items()
                       if order.startswith("2048-")) for section in sections)
        out[case] = dict(original_rows=total, omitted_rows=total-full, bound_violations=sum(r["bounds_failed"] for r in coarse),
                         half_reuse_free_work_fraction=(total-full)/(2*total),
                         independent_all_coarse_plus_fallback_cost_ratio=cost_of_coarse+full/total,
                         best_independent_coarse_plus_fallback_cost_ratio=best/total,
                         rows_1024_omitted=sum(r["1024-bounds-first"]["epochs"]-r["1024-bounds-first"]["full"]
                                               for r in sections))
    return out


def field_budget(receipt, donor):
    work = receipt["modes"]
    short, full = work["short_primary"], work["full"]
    # A positive full call has a confirmed first scout, so the second already ran.
    second_min = full["lanes"]-full["empty_lanes"]
    deficit = receipt["thresholds"]["required_wall_s"]
    clocks = {k: v["per_transform_ns"] for k,v in donor["clocks"].items()}
    results = {}
    for label, second in (("minimum", second_min), ("maximum", full["lanes"])):
        scout_counts = {"short/0": short["lanes"], "full/0": full["lanes"], "full/1": second}
        seconds = {}
        for stage, count in (("carrier_forward", 24), ("lag_forward", 8), ("lag_inverse", 8)):
            seconds[stage] = sum(count*c*clocks[f"{aperture}/{stage}/{scan}"]/1e9
                                 for key,c in scout_counts.items() for aperture,scan in [key.split("/")])
        carrier = seconds["carrier_forward"]
        all_three = sum(seconds.values())
        results[label] = dict(scouts=scout_counts, all_carrier_transforms=24*sum(scout_counts.values()),
                               modeled_transform_cpu_s=seconds, all_three_cpu_s=all_three,
                               gap_left_if_carrier_free_s=deficit-carrier,
                               gap_left_if_all_three_free_s=deficit-all_three,
                               fraction_of_gap_if_carrier_free=carrier/deficit,
                               fraction_of_gap_if_all_three_free=all_three/deficit)
    return results


def audit():
    source = source_contract()
    n, rate, support = 4096, 2_500_000, 704
    selected = eligible_bins(n, rate, 0., 800_000.)
    donor = pricing()
    return dict(source=source, pins=PINS, source_stride=4, rate_hz=rate, sample_support=support,
                lengths=dict(lag=4800, carrier=n, confirmation=64, verifier_frame=128, verifier_grid=512),
                eligible=len(selected), circular_spacing_bins=ceil(10_000*n/rate),
                actual_radix_32_dit=layout(selected, n, 128), radix2_comparison=layout(selected, n, n//2),
                direct_all_eligible_complex_taps_per_mode=len(selected)*support,
                radix2_reference_butterflies_per_mode=int(n*log2(n)/2),
                fft_plan_evidence=donor, previous_signed_row_bound=old_screen(),
                field_transfer=field_budget(first30("first30-empty-call-roof"), donor),
                new_native_calls=0, waveform_reads=0, solver_runs=0)


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
