"""Audit a source-derived four-frame aperture against existing timing receipts."""

from collections import Counter
from hashlib import sha256
from itertools import combinations
from math import cos, pi, sin
from pathlib import Path
from statistics import median, pvariance
import argparse
import gzip
import json


RATE = 10_000_000
SCHEDULE_HZ = 750
PERIOD = 13_333
TAPS = 44
FIRST = 2*TAPS
FIR_RADIUS = 40
STRIDE = 4
STEREO_WINDOW = 200_000
SCOUT_WIDTH = round(RATE/(SCHEDULE_HZ*STRIDE)) + 128*TAPS//STRIDE - 1
REFERENCE = (0, 1, 2, 3, 4)
FULL_SCOUT = range(14)
HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE/"measurements"
LIBRARY = "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c"
EIGHT_CASES_PIN = "b937673935a3c9b3beaf99d2aa76a2de65b18874eaec67ce79d371917ca153fd"
FOUR_RECEIPTS = {
    "0008": "773d366dd41072b8b21fd5765955f1072d668e9d5f975c94cd2c118121743334",
    "0169": "ce47f0d99aade3226a5d320d1351c23b45d1b95a14e50cede2caf11a7becc08d",
}
SOURCE_PINS = {
    "/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse/timing_first_receiver.c":
        "10d8ec75ac2d6e820dd9cee184b2825b8d6510a465bbb8bfa38fc782126daea5",
    "/var/tmp/leo-v3-eight-ms-build-padded/8ms/two_carrier_receiver.c":
        "6f21e36a55caa489f5992a3fbae6006c2af549c30753b7053fae926d0cefb48e",
    "/var/tmp/leo-v3-eight-ms-build-padded/scouts/8ms/portable_verifier.c":
        "bae3798db85b2682ae88d7ce545aac0d084c5f3a747d34cf5c43edd908e0996b",
    "/var/tmp/leo-v3-eight-ms-build-padded/scouts/8ms/receiver_stencil_verify.inc":
        "8b2f4162d9637991e45b3e47eea28aadd9ff254bee02389569be69180f064a63",
    "/var/tmp/leo-v3-eight-ms-build-padded/scouts/8ms/delay_product_kernel.c":
        "d4f199ee7fe3d5208d15887054982206f659d58988c086439cff3b0e62e2bbf5",
    "/var/tmp/leo-v3-eight-ms-build-padded/scouts/8ms/tile.c":
        "a8247e63d632206360ce81d2f2216345bbd3bcde7b7fb8df79fbda94aa6ad8cf",
}


def choose_schedule():
    """Largest frame-time moment at original scout center and native parity."""
    def valid(f):
        return f[0]+f[3] == f[1]+f[2] == 13 and all(i%2 == frame%2 for i,frame in enumerate(f))

    return max((f for f in combinations(FULL_SCOUT,4) if valid(f)), key=pvariance)


def origin(frame, stride=1):
    # The literal frame arithmetic rounds the fractional 40,000/3 samples.
    return (40_000*frame + (3*stride)//2)//(3*stride)


def span(frames, samples):
    """Count original stride-four FIR tiles and enclosing input dependency intervals."""
    tiles, reads = [], []
    pad = FIR_RADIUS//STRIDE
    for f in frames:
        at = origin(f,STRIDE)+FIRST//STRIDE
        lo = pad + (at-pad)//4*4
        hi = pad + (at+SCOUT_WIDTH-pad+3)//4*4
        if lo < pad or hi > samples//STRIDE-pad:
            raise ValueError("FIR frame requires special treatment at full-aperture edge")
        tiles.append((lo,hi))
        # Wrap, late confirmation, fractional and FIR dependencies. Keep 16
        # extra ending positions, as in the earlier distributed-arm check.
        latest = origin(f)+PERIOD-1+FIRST+(232+64)*TAPS
        reads.append((max(0,min(origin(f)-16,lo*STRIDE-FIR_RADIUS)),
                      min(samples,max(latest+16,(hi-1)*STRIDE+FIR_RADIUS+1))))
        if latest > samples:
            raise ValueError("Incomplete native confirmation support")
    def union(intervals):
        output = []
        for left,right in intervals:
            if output and left <= output[-1][1]:
                output[-1] = output[-1][0],max(output[-1][1],right)
            else:
                output.append((left,right))
        return output
    return dict(fir_tiles=union(tiles), necessary_fir_outputs=sum(r-l for l,r in union(tiles)),
                cautious_sample_ranges=union(reads), sample_slots=sum(r-l for l,r in union(reads)),
                latest_confirmation_exclusive=latest, default_ci16_samples_per_positive=samples)


def coherent_power(frames, delta_hz):
    """Ideal coherent frame-array ambiguity. The released verifier sums powers."""
    phase = [2*pi*delta_hz*origin(frame)/RATE for frame in frames]
    return (sum(cos(p) for p in phase)**2+sum(sin(p) for p in phase)**2)/len(frames)**2


def geometry():
    schedules = dict(contiguous5=REFERENCE, distributed4=choose_schedule(),
                     earlier_distributed8=(0,1,4,5,8,9,12,13))
    result = {}
    for label, frames in schedules.items():
        moments = pvariance(origin(frame)/RATE for frame in frames)
        result[label] = dict(frames=frames, offsets_samples=[origin(f) for f in frames],
            frame_variance_ms2=1e6*moments, coherent_equal_snr_information=len(frames)*moments,
            phase_free_equal_snr_information_scale=len(frames)/len(REFERENCE),
            diagnostic_coherent_power={str(f):coherent_power(frames,f)
                                       for f in (62.5,125.,150.,250.,375.,750.)},
            confirmation_groups=[list(frames[i::2]) for i in range(2)],
            physical_parity_counts=dict(Counter(str(f%2) for f in frames)),
            **span(frames,80_000 if label=="contiguous5" else STEREO_WINDOW))
    return result


def timing_gates(attempts, short, fraction, *, clock, total_native=False):
    """Apply a transparent optimistic reduction inside the paid original clocks."""
    pairs = [(t["case"], t[clock], attempts[(t["case"],"successor")][clock])
             for (k,role),t in attempts.items() if role=="installed"]
    if (not pairs or set(short)!={k for k,_,_ in pairs} or len(attempts)!=2*len(pairs)
            or not 0 <= fraction <= 1):
        raise ValueError("The timing scope must bind exactly to measured pairs")
    scope = "native" if total_native else "short"
    measured = []
    for case, stock, candidate in pairs:
        value = short[case][clock][scope]
        if not 0 <= value < candidate:
            raise ValueError("Native clock is outside its measured paid boundary")
        measured.append((stock,candidate,candidate-fraction*value))
    total_stock = sum(x[0] for x in measured)
    total_candidate = sum(x[2] for x in measured)
    summed = total_candidate/total_stock
    middle = median(x[2]/x[0] for x in measured)
    return dict(n=len(pairs),saved_s=sum(x[1]-x[2] for x in measured),through_exit_s=total_candidate,
                summed_speedup=1/summed,median_paired_speedup=1/middle,
                passes={str(g):dict(summed=summed<=1/g,median_paired=middle<=1/g) for g in (1.6,2.)})


def required_short_fraction(attempts, measured, clock, target, gate):
    def passes(fraction):
        return timing_gates(attempts,measured,fraction,clock=clock)["passes"][str(target)][gate]

    if passes(0.):
        return 0.
    if not passes(1.):
        return None
    lower,upper = 0.,1.
    for _ in range(52):
        mid = (lower+upper)/2
        if passes(mid):
            upper = mid
        else:
            lower = mid
    return upper


def content(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"Sealed timing evidence differs at {path}")
    return data


def native_clocks(campaign, enrolled, rows):
    measured = {}
    for item in enrolled:
        case = item["case"]
        row, = [r for r in rows if r["algorithm"]=="successor" and r["case"]==case
                and r["attempt_result_sha256"]==item["attempt_sha256"]]
        folder = campaign/row["attempt"]
        actual = json.loads(content(folder,item["attempt_sha256"]))
        witness = json.loads(content(folder.parent/"publication/unified-short-bootstrap.json",item["witness_sha256"]))
        audit = witness["receiver_audit"]
        held = witness["held_anchor_route"]
        recipe = held["receiver_recipe"]
        clocks = audit["native"]
        values = {}
        for foreign, local in (("cpu","cpu_s"),("wall","elapsed_s")):
            by_role = clocks[f"native_{foreign}_ns"]
            if set(by_role)!={"full","short_primary"}:
                raise ValueError("Unexpected native receiver roles")
            values[local] = dict(short=by_role["short_primary"]/1e9,native=sum(by_role.values())/1e9)
        if (not row["verified_pair"] or actual["elapsed_s"]!=item["successor_s"]
                or witness["native_sha256"]!=actual["native_sha256"]
                or recipe["shortened_sha256"]!=LIBRARY or recipe["aperture_samples"]!=[200_000,80_000]
                or audit["recording_authority"]!=actual["raw_identity"]["raw_authority_sha256"]
                or values["elapsed_s"]["native"]!=item["native_detector_s"]):
            raise ValueError("Short receiver and original scope no longer match the archived pair")
        measured[case] = dict(calls=clocks["native_calls"],witness_sha256=item["witness_sha256"],**values)
    return measured


def run(campaign):
    for path,pin in SOURCE_PINS.items():
        content(Path(path),pin)
    first = json.loads(content(MEASUREMENTS/"first-eight-two-gate-budget.json",EIGHT_CASES_PIN))
    rows = list(map(json.loads,(campaign/"rows.jsonl").read_text().splitlines()))
    measured = native_clocks(campaign,first["all_timed"]["budget"]["cases"],rows)
    scores,minimum = {},{}
    for cohort in ("all_timed","both_reached_publication"):
        attempts = {(a["case"],a["algorithm"]):a for a in first[cohort]["attempts"]}
        by_case = {case: clocks for case,clocks in measured.items() if (case,"successor") in attempts}
        scores[cohort] = {
            clock: {label:timing_gates(attempts,by_case,fraction,clock=clock,total_native=all_roles)
                    for label,fraction,all_roles in (("archive",0.,False),("optimistic_four",.12,False),
                        ("remove_one_fifth_short",.20,False),("free_short",1.,False),
                        ("free_all_native",1.,True))}
            for clock in ("elapsed_s","cpu_s")}
        minimum[cohort] = {clock: {str(target): {
            gate:required_short_fraction(attempts,by_case,clock,target,gate) for gate in ("summed","median_paired")}
            for target in (1.6,2.)} for clock in ("elapsed_s","cpu_s")}
    controls = {}
    for case,pin in FOUR_RECEIPTS.items():
        data = json.loads(gzip.decompress(content(MEASUREMENTS/f"four-frame-primary-{case}.json.gz",pin)))
        controls[case] = dict(gates=data["science"]["gates"],passed=data["passed"],
            comparisons=[{k:row[k] for k in ("order","acquisition_cpu_saving_ns","short_native_cpu_saving_ns")}
                         for row in data["comparisons"]])
    return dict(geometry=geometry(),archived_native=measured,contiguous_four_prior=controls,projections=scores,
                minimum_short_fraction=minimum,source_pins=SOURCE_PINS,
                archived_scope_sha256=EIGHT_CASES_PIN,prior_member_sha256=FOUR_RECEIPTS,
                waveform_reads=0,new_benchmarks=0)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign",type=Path)
    print(json.dumps(run(parser.parse_args().campaign),indent=2,sort_keys=True,allow_nan=False))
