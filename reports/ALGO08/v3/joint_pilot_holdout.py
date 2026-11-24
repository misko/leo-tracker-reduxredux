"""Price a free sparse linear joint-delay/carrier nomination on signed saved clips."""

import argparse
from collections import Counter
from contextlib import ExitStack, closing
import gzip
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
import subprocess
from time import process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, read_archive
from tools.pipeline_eval.variants.experimental.receiver_cancel_support import timing_context

from .anchored_phase import WEAK
from .cyclic_carrier_trial import resume_stock_scan
from .dense_geographic_trial import host
from .mixed_aperture_receiver import INSTALLED_SHA, NativePath, verified
from .short_cfo_refine import PREFIX_PIN, WEAK_PIN, center, signed_rows, window
from .timing_only_oracle import asset_for


HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
INSTALLED = Path("/opt/leo-algo08/algo08v3/payload/receiver.so")
SHORT = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so")
N, PERIOD, BIN_HZ, STRIDE, RANK, CARRIERS, DELAYS = 40000, 13333, 250, 4, 16, 8, 4
VIEW_START = (0, 80000)
FREQ_TOL, TIME_TOL = 4550, 7
CARRIER_BINS = np.arange(-3200, 3201, dtype=np.int32)
EPOCHS = np.arange(0, PERIOD, STRIDE, dtype=np.int32)
ARCHIVES = {
    "cyclic-carrier.json.gz": "ebc4855207121295b0c5db4a9280b2bd6567786e57441b1bfaee26561ddeea8b",
    "joint-envelope.json.gz": "f1c0219117692f212b58b181df0c13b53f7f6837b263d584bd430c7ade6beb8b",
    "cyclic-presence.json.gz": "c2521c28b6d3a193ed83ec3d81c8c6d6209c0031bd8c8836a7b6847dbc3ad65a",
    "short-primary-fusion-profile.json.gz": "0392dc8ae8d728cc59fbd1cddadf35cb60baa4ebfb6af1cba7d43defb7ccd83c",
    "short-primary-fusion-price.json": "0a1899d59d7890b6ec82b7ea3ac31f633e93a52b7a8351f0990136760d592e49",
}


def archived(name):
    path = HERE / "measurements" / name
    data = verified(path, ARCHIVES[name])
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def sparse_plan(pilot, view, rank=RANK):
    """Choose each signed frequency's strongest lines using the pilot asset alone."""
    if pilot.shape != (N,) or view not in (0, 1) or rank <= 0:
        raise ValueError("Invalid signed synthesis or view")
    power = np.abs(pilot)**2
    line_order = np.argsort(-power, kind="stable")
    selected = np.empty((len(CARRIER_BINS), rank), dtype=np.int32)
    count = np.zeros(len(CARRIER_BINS), dtype=np.intp)
    for line in line_order:
        shifted = (line + CARRIER_BINS + N//2) % N - N//2
        in_band = shifted < 0 if view == 0 else shifted >= 0
        include = np.flatnonzero(in_band & (count < rank))
        selected[include, count[include]] = line
        count[include] += 1
        if np.all(count == rank):
            break
    if np.any(count != rank):
        raise ValueError("The requested line count does not exist in every signed cell")
    response = np.ascontiguousarray(pilot[selected].conj())
    energy = power[selected].sum(axis=1)
    if not np.all(np.isfinite(energy) & (energy > 0)):
        raise ValueError("A signed pilot subband has zero or nonfinite support")
    return dict(lines=selected, observed=(selected + CARRIER_BINS[:, None]) % N,
                coefficients=response, energy=energy)


def asset_plan(asset):
    # At 10 MS/s, 40,000 fixed samples contain exactly three schedule periods.
    waveform = asset[4*PERIOD + 81:].view(np.complex64)
    response = np.fft.fft(waveform[(3*np.arange(N)) % N]) / N
    shared = [sparse_plan(response, view) for view in (0, 1)]
    energy = [p["energy"] / np.sum(np.abs(response)**2) for p in shared]
    return shared, [list(map(float, (min(v), np.median(v), max(v)))) for v in energy]


def view_lines(samples, lane, view, plan):
    first = VIEW_START[view]
    slab = samples[first:first+N, lane]
    if slab.shape != (N, 2) or samples.dtype != np.dtype("<i2"):
        raise ValueError("The holdouts require two complete disjoint native CI16 blocks")
    spectrum = np.fft.fft(slab[:, 0].astype(np.float32) + 1j * slab[:, 1]) / N
    return spectrum[plan["observed"]] * plan["coefficients"]


def greedy(weights, positions, limit, spacing, period=None):
    """First ordered maximum and exact exclusion on the declared grid."""
    work = weights.copy()
    keep = []
    for _ in range(limit):
        best = int(np.argmax(work))
        if not np.isfinite(work[best]) or work[best] <= 0:
            break
        keep.append(best)
        distance = abs(positions - positions[best])
        if period is not None:
            distance = np.minimum(distance, period - distance)
        work[distance < spacing] = -np.inf
    return keep


def delay_list(line, plan, cell):
    spectral = np.zeros(N, dtype=np.complex128)
    spectral[plan["lines"][cell]] = line[cell]
    # Under x[n] = p[n-d] exp(+iωn), this inverse has its peak at +d.
    delay = np.fft.ifft(spectral)[EPOCHS] * N
    power = (np.abs(delay)**2) / plan["energy"][cell]
    peaks = greedy(power, EPOCHS, DELAYS, 2*TIME_TOL, PERIOD)
    return [(int(EPOCHS[index]), int(CARRIER_BINS[cell])*BIN_HZ, float(power[index])) for index in peaks]


def nominate(line, plan):
    upper = (np.abs(line).sum(axis=1)**2) / plan["energy"]
    cells = greedy(upper, CARRIER_BINS*BIN_HZ, CARRIERS, 2*FREQ_TOL)
    candidates = [p for cell in cells for p in delay_list(line, plan, cell)]
    return candidates, [int(CARRIER_BINS[cell])*BIN_HZ for cell in cells]


def distance(a, b):
    return abs(remainder(a-b, PERIOD))


def supported(factor, proposals):
    _, integer, offset, hz, *_ = factor
    return any(distance(delay, integer+offset) <= TIME_TOL and abs(estimate-hz) <= FREQ_TOL
               for delay, estimate, _ in proposals)


def score_factor(factor, proposals, lines, plans):
    if factor is None:
        return None
    index = int(np.clip(round(factor[3]/BIN_HZ) - int(CARRIER_BINS[0]), 0, len(CARRIER_BINS)-1))
    aligned = [delay_list(line, plan, index) for line, plan in zip(lines, plans, strict=True)]
    return dict(views=[supported(factor, values) for values in proposals],
                known_carrier=[supported(factor, values) for values in aligned], known_carrier_delays=aligned)


def overlaps(proposals):
    return sum(distance(a[0], b[0]) <= 2*TIME_TOL and abs(a[1]-b[1]) <= 2*FREQ_TOL
               for a in proposals[0] for b in proposals[1])


def assay(samples, lane, plan, full_factor, short_factors=None):
    coeff = [view_lines(samples, lane, view, template) for view, template in enumerate(plan)]
    views, centers = zip(*(nominate(line, template) for line, template in zip(coeff, plan, strict=True)), strict=True)
    result = dict(views=views, centers=centers, paired_intersections=overlaps(views),
                  full=score_factor(full_factor, views, coeff, plan))
    if short_factors is not None:
        short, = short_factors or (None,)
        result["short"] = score_factor(short, views, coeff, plan)
    return result


def frozen_lanes():
    dense, source = signed_rows("dense")
    dense = [(f"DS30-0008:{row['key']}", source["iq"][row["key"]], row["edge"], row["lane"], row["tune"],
              row["iq"], row["mode"] == "short_primary") for row in dense]
    verified(WEAK, WEAK_PIN)
    weak = []
    for meta, samples in read_archive(WEAK, 18):
        shaped = window(meta, samples)
        for lane in (0, 1):
            weak.append((meta["key"], meta["sha256"], shaped.target["edge"], lane, center(shaped), samples, True))
    if len(dense) != 48 or len(weak) != 36:
        raise ValueError("The saved clip roster changed")
    return dict(dense=dense, weak=weak), dict(dense=source, weak_zip_sha256=WEAK_PIN)


def count_panel(records):
    totals = {}
    for scope in ("short", "full_primary", "full_residual"):
        summary = Counter()
        for row in records:
            scans = row["scans"]
            if scope == "full_residual" and len(scans) < 2:
                continue
            probe = scans[int(scope == "full_residual")]
            if scope == "short" and "short" not in probe:
                continue
            prediction = probe["short" if scope == "short" else "full"]
            if prediction is None:
                summary.update(empty=1, empty_either_emits=any(probe["views"]),
                               empty_views_agree=bool(probe["paired_intersections"]))
            else:
                a, b = prediction["views"]
                summary.update(positive=1, supported_a=a, supported_b=b, supported_either=a or b,
                               supported_both=a and b, known_carrier_either=any(prediction["known_carrier"]),
                               known_carrier_both=all(prediction["known_carrier"]),
                               positive_any_agreement=bool(probe["paired_intersections"]))
        totals[scope] = dict(summary)
    return totals


def budget(result, profile, transfer):
    dense = transfer["projections"]["DS30-0008"]
    mass = []
    for key, count in zip(("positive", "empty"), (dense["positive"], dense["short_calls"]-dense["positive"]), strict=True):
        stage = profile["profile"]["grouped"][key]["stage_ns_per_lane"]
        mass.append(count * (stage["lag_timing"] + stage["carrier_grid"]))
    grid_cpu = dense["projections"]["all_timing_and_carrier_grids"]["cpu_saved"]
    positive_cpu, empty_cpu = (grid_cpu*x/sum(mass) for x in mass)
    found = result["dense"]["summary"]["short"]
    target = 3.49
    favorable = found["supported_either"] / found["positive"]
    verified_views = found["supported_both"] / found["positive"]
    return dict(conditional_target_cpu_s=target, full_grid_cpu_s=grid_cpu,
                grid_cpu_positive_s=positive_cpu, grid_cpu_empty_s=empty_cpu,
                coverage_grant_either_view=favorable, coverage_both_views=verified_views,
                assumed_zero_cost_positive_grant_all_empty_cpu_s=empty_cpu+positive_cpu*favorable,
                assumed_zero_cost_positive_both_all_empty_cpu_s=empty_cpu+positive_cpu*verified_views,
                positive_recall_needed_free_all_empty=(target-empty_cpu)/positive_cpu,
                positive_recall_needed_80us_all_empty=(target+dense["short_calls"]*80e-6-empty_cpu)/positive_cpu,
                zero_retry_overhead_allowance_us=(grid_cpu-target)/dense["short_calls"]*1e6,
                linear_line_terms_per_scan=2*len(CARRIER_BINS)*RANK,
                direct_delay_complex_terms_per_scan=2*CARRIERS*len(EPOCHS)*RANK)


def run(root):
    current = host()
    if root.absolute() != root.resolve() or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use a fresh tmpfs destination")
    root.mkdir()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", str(WEAK)], text=True).strip() != "tmpfs":
        raise ValueError("Use the existing original tmpfs archive")
    verified(INSTALLED, INSTALLED_SHA)
    verified(SHORT, PREFIX_PIN)
    cyclic = archived("cyclic-carrier.json.gz")["raw"]
    envelope = archived("joint-envelope.json.gz")["groups"]
    presence = archived("cyclic-presence.json.gz")["cohorts"]
    profile = archived("short-primary-fusion-profile.json.gz")
    transfer = archived("short-primary-fusion-price.json")
    lanes, references = frozen_lanes()
    outputs, plans, asset_support, engines = {}, {}, {}, {}
    residual = np.empty((200000, 2, 2), dtype="<i2")
    scratch = np.empty(80000, dtype="<f4")
    with ExitStack() as resources:
        for edge in ("lower", "upper"):
            asset = asset_for(RELEASE / "assets", edge)
            plan, energy = asset_plan(asset)
            plans[edge], asset_support[edge] = plan, energy
            full = resources.enter_context(closing(Receiver(INSTALLED, asset)))
            context = timing_context(full, asset)
            resources.callback(full.lib.timing_first_free, context)
            short = resources.enter_context(closing(NativePath(SHORT, asset, "short_primary")))
            engines[edge] = full, short, context, asset
        for label, panel in lanes.items():
            indexed = {(r["key"], r["input_sha256"], r["edge"], r["lane"]): r for r in cyclic[label]}
            timing = {(r["key"], r["iq_sha256"], r["edge"]): r for r in envelope[label]["detail"]}
            short_ref = {(r["key"], r["digest"], r["edge"], r["lane"]): r["factor"] for r in presence[label]}
            prior, records = Counter(), []
            begin = process_time_ns()
            for key, digest, edge, lane, tune, samples, supported_short in panel:
                if tune != 0:
                    raise ValueError("The frozen nominal zero-center controls changed")
                identity = (key, digest, edge, lane)
                donor = indexed.pop(identity)
                mirror = timing[identity[:3]]
                full, short, context, asset = engines[edge]
                factors, _, _ = full.timed(samples, lane, tune)
                stock = [r["factor"] for r in donor["scans"] if r["factor"] is not None]
                if sorted(map(list, factors)) != sorted(stock) or sorted(stock) != sorted(mirror["stock"][lane]):
                    raise ValueError("Signed original factor and clip identities disagree with the published scout controls")
                reached = resume_stock_scan(full, context, asset, samples, lane, tune, residual, scratch)
                if (1 + reached) != len(donor["scans"]):
                    raise ValueError("The original signed cancellation path changed")
                short_factors = short.run(samples, lane, tune)[0] if supported_short else None
                if supported_short and list(map(list, short_factors)) != short_ref.pop(identity):
                    raise ValueError("The short-primary scope changed from the published signed presence control")
                factor_by_rank = {f[0]: f for f in factors}
                scans = []
                for rank, waveform in enumerate((samples, residual) if reached else (samples,)):
                    factor = factor_by_rank.get(rank)
                    scans.append(assay(waveform, lane, plans[edge], factor, short_factors if rank == 0 else None))
                    if factor is not None:
                        phase = mirror["proposal"][f"rx{lane}"]
                        old = donor["scans"][rank]["measures"]
                        candidate_time = any(distance(p[0], factor[1]+factor[2]) <= TIME_TOL for p in phase)
                        candidate_hz = any(abs(hz-factor[3]) <= FREQ_TOL for view in old.values() for hz in view["hz"])
                        name = "primary" if rank == 0 else "residual"
                        prior.update({name+"_time": candidate_time, name+"_frequency": candidate_hz,
                                      name+"_joint": candidate_time and candidate_hz})
                records.append(dict(key=key, digest=digest, edge=edge, lane=lane, factors=factors,
                                    short_factors=short_factors, scans=scans))
            if indexed or short_ref:
                raise ValueError("Original signed clip enrollment changed")
            outputs[label] = dict(rows=records, summary=count_panel(records), old_controls=dict(prior),
                                  audit_cpu_ns=process_time_ns()-begin)
    result = dict(panels=outputs, budget=budget(outputs, profile, transfer), asset_line_energy=asset_support,
                  archives=ARCHIVES, references=references, worker=current, first_use_input="fixed pilot and own disjoint I/Q",
                  original_recording_reads=0, costs_are_oracle=True,
                  source_sha256={p.name: sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__), HERE/"joint-pilot-holdout-protocol.md")})
    with (root / "result.json").open("x") as output:
        json.dump(result, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    run(cli.parse_args().root)
