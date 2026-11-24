"""Price a strict full-data warm start and compare whole-visit exposure proxies."""

import argparse
from collections import defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter, process_time

import numpy as np

from leo.contracts.digests import canonical_digest


HERE = Path(__file__).resolve().parent
M = HERE/"measurements"
DENSE = Path("/dev/shm/leo-held-anchor-selected-dense-01")
SOUTH = Path("/dev/shm/leo-v3-named-south-transfer-01")
SOUTH_SHA = "26e4ce9c24e81761e4d92cf05e29474e4ced9ba4effdffff89b817c0ea9f9ce3"
SOUTH_REQUEST = {
    "containing": "e3ba4f9153eb1cc2348666aea2a9b3afdb98c8b3ec8e792413063d98ed5830fd",
    "near-omitted": "3ac64915a3fe5d5115ce0428ed0b133e00343bae45d0321acff804f62626c1b7",
}
DENSE_SHA = "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
DENSE_REQUEST = "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502"
DENSE_CONTROL = "17e1a6addf19f6bb22e6d7941a7bdfc6ab9a88d2b8c1c8ae960b5c7983f0b2d2"
TRACES = dict(dense="7805e88a1b0ae8ad96baf86e62be548682b146ef5bde13815b536976746cd33e",
              weak="d72d41dfc464c90e69793bddb3f5296fe0846324fe75dc20b62d29070e3525a2")
SOUTH_OUTCOME = "7653b038a30e723e46bf3a5cb690ce8a52d841378f5d60964e1708e2d51cdcca"
PERIOD = 1 / 4.4e-6
BLOCK = 8
GATE_NS = 2_000_000_000


def checked(path, digest):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError(f"Archived input changed at {path}")
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def frozen_local(path):
    local = path.resolve(strict=True)
    if not local.is_relative_to(Path("/dev/shm")):
        raise ValueError("Only preexisting tmpfs metadata can supply the diagnostic")
    return local


def packet_visit_rows(packet):
    source, run = packet["source"], packet["provenance"]
    probes = source["probes"]
    if (run["scope"] != "cancellation" or not source["qualified"] or run["skipped_fast_score"]
            or source["sample_rate_hz"] != 10_000_000
            or canonical_digest(["cancellation", source["raw_recording_authority_digest"],
                                 run["detector_sha256"].removeprefix("sha256:"), probes]) != source["analysis_manifest_sha256"]):
        raise ValueError("Use only complete signed detector evidence")
    visits = defaultdict(list)
    for probe in probes:
        visits[probe["visit_index"]].append(probe)
    issued = run["window_count"]
    exclusions = {row["visit"] for row in run["excluded_windows"]}
    if (list(visits) != sorted(set(range(issued))-exclusions) or len(visits) != run["processed_windows"]
            or len(exclusions) != run["invalid_capture"]):
        raise ValueError("Native opportunity sequence changed")
    previous = -1
    for lanes in visits.values():
        if (len(lanes) != 2 or [row["receiver_id"] for row in lanes] != [0, 1]
                or any(lanes[0][key] != lanes[1][key] for key in
                       ("valid_start_counter", "actual_rf_hz", "channel", "edge"))
                or lanes[0]["valid_start_counter"] <= previous):
            raise ValueError("Whole stereo visits must be chronological and sample-time matched")
        previous = lanes[0]["valid_start_counter"]
    return visits


def exposure(visits, anchor, end):
    """A full per-visit proxy Gram matrix, with independent positive lane weights."""
    counts = np.zeros((len(visits), 4, 2), dtype=np.int64)
    rows, weights, indexes = [], [], []
    for ix, lanes in enumerate(visits.values()):
        for lane in lanes:
            group = 2 * lane["receiver_id"] + int(lane["channel"] > 4)
            options = lane["candidates"]
            counts[ix, group] = bool(options), len(options)
            for candidate in options:
                if not candidate["passed_fractional_margin_gate"]:
                    raise ValueError("Unsigned nuisance factors cannot supply proxy exposure")
                sample = (lane["valid_start_counter"] - anchor + candidate["integer_epoch_sample"]
                          + candidate["fractional_epoch_offset_samples"])
                t = 2*sample/(end-anchor) - 1.
                signed = candidate["fractional_tracking_cfo_hz"]
                rf = lane["actual_rf_hz"] / 1e9 - 11.5
                rows.append((t, signed, rf, group))
                weights.append(1./len(options))
                indexes.append(ix)
    if not rows:
        return np.zeros((len(visits), 12, 12), dtype=np.float64), counts
    t, signed, rf, group = np.array(rows, dtype=np.float64).T
    if not np.isfinite((t, signed, rf)).all():
        raise ValueError("Finite hardware count, signed CFO and RF required")
    group = group.astype(int)
    change = 2.*np.pi*(np.remainder(signed, PERIOD)/PERIOD)
    design = np.zeros((len(rows), 12), dtype=np.float64)
    design[np.arange(len(rows)), group] = 1.
    design[np.arange(len(rows)), 4 + group] = t
    design[:, 8] = rf
    design[:, 9:] = np.column_stack((t*t, np.sin(change), np.cos(change)))
    contribution = np.array(weights)[:, None, None] * design[:, :, None] * design[:, None, :]
    gram = np.zeros((len(visits), 12, 12), dtype=np.float64)
    np.add.at(gram, indexes, contribution)
    return gram, counts


def information(gram, fitted):
    i = 9 if fitted else 8
    adjusted = gram[9:, 9:] - gram[9:, :i] @ np.linalg.solve(gram[:i, :i] + np.eye(i), gram[:i, 9:])
    return (adjusted + adjusted.T) / 2.


def choose(gram, counters):
    uniform, weighted = [], []
    strata, remainder = divmod(len(counters), 3*BLOCK)
    if strata < 3:
        raise ValueError("At least three full strata required for a controlled comparison")
    for group in range(strata):
        start = group*3*BLOCK
        blocks = np.arange(start, start+3*BLOCK).reshape(3, BLOCK)
        # Subtract before taking a mean to preserve small timing differences.
        time = counters[blocks] - counters[start]
        neutral = int(np.argmin(np.abs(time.mean(axis=1) - (time[0, 0]+time[-1, -1])/2.)))
        proxy = gram[blocks].sum(axis=1)
        priorities = [min(np.linalg.slogdet(np.eye(3) + information(g, fit))[1] for fit in (False, True))
                      for g in proxy]
        winner = int(np.argmax(priorities))
        if group in (0, strata-1):
            winner = neutral = 0 if group == 0 else 2
        uniform.extend(blocks[neutral])
        weighted.extend(blocks[winner])
    tail = list(range(len(counters)-remainder, len(counters)))
    return np.asarray(uniform + tail), np.asarray(weighted + tail)


def coverage(native):
    source = native["source"]
    visits = packet_visit_rows(native)
    ids = np.asarray(list(visits))
    counters = np.asarray([lanes[0]["valid_start_counter"] for lanes in visits.values()], dtype=np.int64)
    start = process_time()
    gram, counts = exposure(visits, counters[0], counters[-1] + source["sample_rate_hz"]*source["probe_ms"]//1000)
    uniform, weighted = choose(gram, counters)
    choice_cpu_s = process_time()-start
    arm_names = ("c0", "fitted_c")
    base = [information(gram.sum(axis=0), fitted) for fitted in (False, True)]
    results = {}
    for mode, pick in (("full", np.arange(len(ids))), ("uniform", uniform), ("weighted", weighted)):
        evidence = gram[pick].sum(axis=0)
        proxy_fraction = {}
        for index, arm in enumerate(arm_names):
            if np.linalg.eigvalsh(base[index])[0] <= 0.:
                proxy_fraction[arm] = None
                continue
            lower = np.linalg.cholesky(base[index])
            whitened = np.linalg.solve(lower, information(evidence, bool(index)))
            whitened = np.linalg.solve(lower, whitened.T).T
            proxy_fraction[arm] = float(np.linalg.eigvalsh(whitened)[0])
        subtotal = counts[pick].sum(axis=0)
        results[mode] = dict(visits=len(pick), viable_lanes=int(subtotal[:, 0].sum()), factors=int(subtotal[:, 1].sum()),
                             receiver_band_counts=subtotal.tolist(), weaker_direction_proxy_fraction=proxy_fraction,
                             visit_ids_digest=canonical_digest(ids[pick].tolist()))
    return dict(views=results, choice_cpu_s=choice_cpu_s, chosen_overlap=int(len(set(uniform) & set(weighted))),
                analysis_manifest=source["analysis_manifest_sha256"], authority=source["raw_recording_authority_digest"],
                inventory=source["input_manifest_sha256"])


def optimizer_budget(trace):
    if not all(trace["checks"].values()):
        raise ValueError("Expect the verified complete original calibration pair")
    result = {}
    for stage in ("cold", "post_cold"):
        arms = trace["diagnostics"][stage]
        result[stage] = {}
        for arm in ("c0", "fitted_c"):
            parts = arms[arm]
            if parts["derivative"]["cpu_ns"] != parts["final_derivative"]["cpu_ns"] + parts["removable"]["cpu_ns"]:
                raise ValueError("The archived pre-final derivative accounting changed")
            def total(*keys):
                return sum(parts[key]["cpu_ns"] for key in keys)
            result[stage][arm] = dict(free_derivative_ns=total("removable"),
                                     free_warm_ns=total("removable", "trust_accepted", "trust_rejected"),
                                     retained_start_and_final_derivative_ns=total("starting", "final_derivative"),
                                     full_objective_ns=total("starting", "derivative", "trust_accepted", "trust_rejected"))
    return dict(per_stage=result, trace_solve_cpu_s=trace["solver_cpu_s"], native_digest=trace["input_sha256"],
                total_derivative_ns=sum(row["free_derivative_ns"] for arms in result.values() for row in arms.values()),
                total_warm_ns=sum(row["free_warm_ns"] for arms in result.values() for row in arms.values()))


def run(output):
    if subprocess.check_output(["findmnt", "-T", output.parent, "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh tmpfs result")
    clock = (process_time(), perf_counter())
    dense_request = checked(frozen_local(DENSE/"request.json"), DENSE_REQUEST)
    dense_native = checked(frozen_local(DENSE/"original-detections.json"), DENSE_SHA)
    dense = coverage(dense_native)
    if (dense["authority"] != dense_request["authority"] or dense["inventory"] != dense_request["inventory"]
            or dense_request["original"]["file"] != str(DENSE/"original-detections.json")):
        raise ValueError("Dense native and request identity disagree")

    south = {}
    for offer, pin in SOUTH_REQUEST.items():
        request = checked(frozen_local(SOUTH/(offer+"-request.json")), pin)
        (packet,) = (SOUTH/offer/"fast-scan-automatic-work").glob("*/detections.json")
        native = checked(frozen_local(packet), SOUTH_SHA)
        proof = coverage(native)
        if proof["authority"] != request["authority"] or proof["inventory"] != request["inventory"] or request["native"] != "sha256:" + SOUTH_SHA:
            raise ValueError("South offered inputs no longer share the original native source")
        south[offer] = proof
    if south["containing"]["views"] != south["near-omitted"]["views"]:
        raise ValueError("Selection changed with the geographic offer")

    work = {case: optimizer_budget(checked(M/(f"optimizer-quadrature-{case}.json.gz"), trace))
            for case, trace in TRACES.items()}
    complete = checked(M/"cold-exact-budget-dense-control.json.gz", DENSE_CONTROL)
    old = complete["stages"]["work"]
    # Independently scored geographic evidence is read after selection. Its
    # labels are never used by the visit selector.
    geo = checked(frozen_local(SOUTH/"result.json"), SOUTH_OUTCOME)
    if not geo["verified"]:
        raise ValueError("The archived opposite-region pair has no verification")
    for budget in work.values():
        budget["gate_ns"] = GATE_NS
    for mode in ("uniform", "weighted"):
        p = dense["views"][mode]["factors"]/dense["views"]["full"]["factors"]
        work["dense"][mode+"_linear_factor_savings_ns"] = int(work["dense"]["total_warm_ns"] * (1-p))
    data = dict(dense=dense, south=south, budgets=work, eligible=work["dense"]["total_warm_ns"] >= GATE_NS,
                same_clock_rank_already_paid_cpu_s=old["ranks"][0]["cpu_ns"]/1e9,
                same_clock_cold_outside_rank_cpu_s=(old["scopes"][0]["cpu_ns"]-old["ranks"][0]["cpu_ns"])/1e9,
                same_clock_dense_numerical_solve_cpu_s=complete["solve"]["cpu_s"],
                archived_geographic={offer: {name: record[name] for name in ("arms", "status", "truth_face", "terminal_sha256")}
                                   for offer, record in geo["cases"].items()},
                pins=dict(dense_native=DENSE_SHA, dense_request=DENSE_REQUEST, south_native=SOUTH_SHA,
                          south_requests=SOUTH_REQUEST, dense_control=DENSE_CONTROL, south_outcome=SOUTH_OUTCOME, traces=TRACES,
                          source=sha256(Path(__file__).read_bytes()).hexdigest(),
                          protocol=sha256((HERE/"visit-information-warm-start-protocol.md").read_bytes()).hexdigest()),
                observer=dict(cpu_s=process_time()-clock[0], wall_s=perf_counter()-clock[1], waveform_calls=0, position_solves=0))
    with output.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
