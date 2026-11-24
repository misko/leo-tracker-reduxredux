"""Price a causal geographic carrier mask at the installed 20 ms rank boundary."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from math import ceil, floor, isfinite
from pathlib import Path


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
FULL = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
REFERENCE = {
    "refine-bound-audit.json.gz": "a0a1e7f3eb9b923fa0aef18164c6b81175ab21a15282f1816492556f51037cb7",
    "scout-readout.json.gz": "5d1998cee0e16165f2c355059d28b4b96f2486cc9297e7c55d760d4784f34431",
    "selective-carrier-transform.json": "f6ada6eace39309a1c7a96065eb63f9744a9006875ca5a07959fc69f6227595a",
}
NATIVE = {
    "build": "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d",
    "timing_source": "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a",
    "timing_object": "5ffc8eb34785b7d20535549da23ba521cf954f86b6cfabce96c0c71ac664292d",
    "wrapper_source": "4f3326eee5522f02ee05a236f22a41fc1af5bb0f21b6e3fe337711a66226f5f7",
    "wrapper_object": "5da4a22216750400f8cd669a4487b3d22c9458092dd4555739d59366090ef9f7",
    "installed": FULL,
}
SIZE = 4096
RATE = 2_500_000
WIDTH_HZ = 800_000
STEP = RATE / SIZE
FINAL_ALIAS = 10_000_000 / 44
TIMINGS = 12
MODES = 2
REQUESTS = 4


def read(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Archived evidence changed: {path}")
    return body


def decode(path, pin):
    data = read(path, pin)
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def signed_index(index, size=SIZE):
    return index if index < size//2 else index-size


def full_bank(center=0.0):
    lo, hi = center-WIDTH_HZ, center+WIDTH_HZ
    return tuple(index for index in range(SIZE)
                 if ceil((lo-center-signed_index(index)*STEP)/RATE) <= floor((hi-center-signed_index(index)*STEP)/RATE))


def lifted_envelope(intervals, alias=None):
    """Illustrate the proof boundary for hypothetical certified signed intervals."""
    bank = full_bank()
    if not intervals or any(not (isfinite(lo) and isfinite(hi) and lo <= hi) for lo, hi in intervals):
        return bank
    if alias is not None and (not isfinite(alias) or alias <= 0):
        return bank
    if alias is None:
        return tuple(i for i in bank if any(lo <= signed_index(i)*STEP <= hi for lo, hi in intervals))
    if any(hi-lo >= alias for lo, hi in intervals):
        return bank
    return tuple(i for i in bank if any(ceil((lo-signed_index(i)*STEP)/alias) <=
                                      floor((hi-signed_index(i)*STEP)/alias) for lo, hi in intervals))


def seed_index(hz, center):
    signed = (hz-center) / STEP
    if signed != int(signed) or abs(signed) > floor(WIDTH_HZ/STEP):
        raise ValueError("A traced native request is off the exact signed scout grid")
    return int(signed) % SIZE


def native_source(bench, binary):
    timed = bench / "spectral-vectors-combined-v1/packed/timing_first_receiver"
    wrapper = bench / "site-free-mode-pair-pgo/candidate/objects/two_carrier_receiver"
    read(binary, FULL)
    build = decode(bench / "receiver-fractional-exact-v1/build.json", NATIVE["build"])
    for key, path in (("timing", timed), ("wrapper", wrapper)):
        read(path.with_suffix(".o"), NATIVE[key+"_object"])
        read(path.with_suffix(".c"), NATIVE[key+"_source"])
        if build["parent_objects"][path.name+".o"] != NATIVE[key+"_object"]:
            raise ValueError("The archived object is outside the installed relink")
    if build["exact_sha256"] != FULL:
        raise ValueError("The relink does not match the installed 20 ms binary")
    return NATIVE


def measured_scans(scope, readout):
    centers = {(r["key"], r["lane"], r["digest"]): r for r in readout["rows"]}
    keys = set()
    scans = []
    for row in scope["lanes"]:
        key = row["window"], row["lane"], row["iq_sha256"]
        other = centers[key]
        keys.add(key)
        if len(row["scans"]) not in (1, 2) or other["center_hz"] != 0 or row["factors"] != other["released"]:
            raise ValueError("The two signed 20 ms ledgers differ")
        for rank, scan in enumerate(row["scans"]):
            bins = [seed_index(seed["hz"], other["center_hz"]) for seed in scan["seeds"]]
            if len(bins) != REQUESTS:
                raise ValueError("The signed 20 ms trace no longer retains the full four-request order")
            scans.append((rank, bins))
    if keys != centers.keys():
        raise ValueError("The seed and signed readout do not bind all original lanes")
    return scans


def oracle_bound(scans):
    bank = full_bank()
    size = len(bank)
    mask = {bin_ for _, bins in scans for bin_ in bins}
    hull = min(map(signed_index, mask)), max(map(signed_index, mask))
    rank_visits = lambda outputs: 2 * TIMINGS * outputs
    n = len(scans)
    return dict(scouts=n, refinement_requests=REQUESTS*n, hypothetical_region_confirmed_omissions=0,
                carrier_fft_invocations=TIMINGS*MODES*n, installed_all_bin_power_terms=SIZE*TIMINGS*MODES*n,
                native_rank_indices=rank_visits(size*n),
                retained_requests_at_full_fallback=REQUESTS*n,
                hindsight_fixed_bin_count=len(mask), hindsight_fixed_touched_inner_dit_residues=len({i % 128 for i in mask}),
                hindsight_fixed_signed_hull_bins=hull[1]-hull[0]+1, signed_hull_hz=[edge*STEP for edge in hull],
                hindsight_fixed_rank_indices=rank_visits(len(mask)*n),
                hindsight_per_scout_unique_bins=dict(sorted(Counter(len(set(bins)) for _, bins in scans).items())),
                hindsight_per_scout_rank_indices=rank_visits(sum(len(set(bins)) for _, bins in scans)),
                hindsight_retained_top_four_requests=REQUESTS*n,
                installed_fft_calls_omitted_even_with_hindsight_mask=0)


def summarize(bench=None, binary=None):
    traces = {name: decode(MEASUREMENTS / name, pin) for name, pin in REFERENCE.items()}
    seeds = traces["refine-bound-audit.json.gz"]
    scout = traces["scout-readout.json.gz"]
    if seeds["reference_sha256"] != FULL or scout["build"]["installed_sha256"] != FULL:
        raise ValueError("Expected the reference receiver's real 20 ms requests")
    data = {}
    for cohort in ("dense", "weak"):
        scans = measured_scans(seeds[cohort], scout["groups"][cohort])
        data[cohort] = dict(lanes=len(seeds[cohort]["lanes"]), factors=sum(len(row["factors"]) for row in seeds[cohort]["lanes"]),
                            raw=oracle_bound([s for s in scans if s[0] == 0]),
                            residual=oracle_bound([s for s in scans if s[0] == 1]),
                            both=oracle_bound(scans))
    transform = traces["selective-carrier-transform.json"]
    if transform["eligible"] != len(full_bank()) or (bench is None) != (binary is None):
        raise ValueError("The source or reference bin eligibility changed")
    native = native_source(bench, binary) if bench is not None else None
    centers_hz = (0, STEP, -(SIZE//4)*STEP)
    invariance = [lifted_envelope([(c-FINAL_ALIAS, c+FINAL_ALIAS)], FINAL_ALIAS) == full_bank() for c in centers_hz]
    if lifted_envelope(None) != full_bank() or not all(invariance):
        raise ValueError("Missing or alias-filling region must keep the full bank")
    return dict(native_sha256=native, reference_sha256=REFERENCE, grid_hz=STEP,
                quarter_rate_alias_period_hz=RATE, final_observation_alias_period_hz=FINAL_ALIAS,
                missing_region_retained_bins=len(full_bank()), lifted_alias_fill_same_bank=invariance,
                signed_scout_bins=len(full_bank()), sites=data, source_waveform_opens=0, catalogue_opens=0,
                new_native_calls=0, solver_calls=0)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--bench", type=Path)
    cli.add_argument("--binary", type=Path)
    args = cli.parse_args()
    print(json.dumps(summarize(args.bench, args.binary), indent=2, sort_keys=True))
