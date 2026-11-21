"""Reacquire every raw visit, retain independently verified candidates and run frozen v5."""

import argparse
import gzip
import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import perf_counter, process_time

from ..variants import carrier_continuation, two_carrier
from . import original_v5, recording_to_v5
from .full_v5_check import _load_case, _probe, _sha
from .reverse_glrt_reference import CASES, REPORT, packed, read_bound
from .reverse_glrt_report import read
from .reverse_glrt_search import WORK as ORACLE
from .reverse_glrt_search import Verifier
from .timing_first_position import compatible_factor, full_identity, raw_windows
from .timing_first_trial import SCRATCH as PRIOR_WORK
from .two_carrier_roster import OUT, WORK

POLICIES = ("two_margin", "causal_choice", "causal_withhold")
ORIGINAL = ORACLE / "portable-field.so"


def peak(factor):
    return dict(
        epoch=(factor["integer_epoch_sample"] + factor["fractional_epoch_offset_samples"]) % 13333,
        hz=factor["fractional_tracking_cfo_hz"],
    )


class RawVerifier:
    def __init__(self, edge):
        self.edge = edge
        self.proof = None

    def factors(self, proposals, iq, rx):
        if proposals:
            if self.proof is None:
                self.proof = Verifier(ORIGINAL, self.edge, iq, rx)
            elif self.proof.lib.portable_verifier_load(self.proof.ctx, iq.ctypes.data, rx):
                raise ValueError("failed to bind raw verifier to the original antenna")
        verified, verdicts = [], []
        for rank, p in enumerate(proposals):
            f, status = compatible_factor(p, self.proof)
            if f:
                if any(two_carrier.same(peak(old), peak(f)) for old in verified):
                    status = "duplicate_after_refinement"
                else:
                    verified.append(dict(f, candidate_rank=rank))
            verdicts.append(status)
        return verified, verdicts

    def close(self):
        if self.proof is not None:
            self.proof.close()
            self.proof = None


def sources(out, binaries):
    parents = [
        Path(__file__),
        Path(two_carrier.__file__),
        Path(carrier_continuation.__file__),
        two_carrier.SOURCE,
        two_carrier.HEADER,
        *binaries,
        ORIGINAL,
        out / "PROTOCOL.md",
    ]
    return {p.name: _sha(p) for p in parents}


def write_native(root, document, case_id, policy, rows, authority, parent_hash, lock):
    stage = root / policy / case_id
    stage.mkdir(exist_ok=True, parents=True)
    signature = recording_to_v5.digest([authority, policy, lock, rows])
    document["source"].update(probes=rows, analysis_manifest_sha256=signature)
    document["provenance"].update(
        run_id="two-carrier-" + signature[7:39],
        scope=policy,
        detector_sha256="sha256:" + signature[7:],
    )
    path = stage / "native.json"
    recording_to_v5.save(path, document)
    return dict(
        policy=policy,
        case=case_id,
        native_sha256=_sha(path),
        raw_authority=authority,
        first_pass_native_sha256=parent_hash,
        probes=len(rows),
        factors=sum(len(p["candidates"]) for p in rows),
        sources=lock,
    )


def acquire(args):
    ident, cpu, out, work, binaries = args
    os.sched_setaffinity(0, {cpu})
    directory = work / "captures" / ident
    directory.mkdir(exist_ok=True, parents=True)
    done = directory / "capture.json"
    lock = sources(out, binaries)
    if done.exists():
        record = read(done)
        if record["sources"] != lock or any(
            _sha(work / policy / ident / "native.json") != arm["native_sha256"]
            for policy, arm in record["inputs"].items()
        ):
            raise ValueError("complete-recording receiver or its measured inputs changed")
        return ident, record["counts"]
    case = _load_case(ident)
    past = PRIOR_WORK / "position" / ident
    document = read_bound(case["native"])
    previous = read(past / "capture-receipt.json")
    if (
        previous["acquisition_sha256"] != _sha(binaries[0])
        or previous["verifier_sha256"] != _sha(ORIGINAL)
        or previous["new_native_sha256"] != _sha(past / "native.json")
        or previous["original_native_sha256"] != case["native"]["sha256"]
    ):
        raise ValueError("single-carrier reference changed")
    original = {(p["visit_index"], p["receiver_id"]): p for p in document["source"].pop("probes")}
    first = {
        (p["visit_index"], p["receiver_id"]): p["candidates"]
        for p in read(past / "native.json")["source"]["probes"]
    }
    exclusions = {p["visit"]: p for p in document["provenance"]["excluded_windows"]}
    edge = next(v["edge"] for v in read(REPORT / "manifest.json")["cases"] if v["case"] == ident)
    signed, rows = [], {policy: [] for policy in POLICIES}
    counts, cpu_s = Counter(), Counter()
    hint = carrier_continuation.Continuation()
    verifier = RawVerifier(edge)
    began = perf_counter()
    path = directory / "candidates.jsonl.gz"
    with (
        two_carrier.Receiver(binaries, edge) as receive,
        gzip.open(path.with_suffix(".partial"), "wb", compresslevel=1) as audit,
    ):
        try:
            for visit, w in enumerate(raw_windows(case)):
                acq = w.acquisition
                retune = json.loads(acq["retune_receipt"])
                if (
                    visit != acq["global_visit"]
                    or w.target["edge"] != edge
                    or tuple(w.receiver_ids) != (0, 1)
                    or w.sample_rate_hz != 10000000
                    or any(
                        document["delivery_clocks"][visit].get(k) != v
                        for k, v in retune["host_delivery_clock"].items()
                    )
                    or (visit == 0 and retune["utc_clock_bracket"] != document["clock_anchor"])
                ):
                    raise ValueError("capture identity or hardware clocks changed")
                signed.append(w.iq_sha256)
                if visit in exclusions:
                    e = exclusions[visit]
                    if e["iq_sha256"] != w.iq_sha256 or e["sample_start"] != acq["sample_start"]:
                        raise ValueError("capture exclusion differs from original")
                    continue
                if not acq["complete"] or acq["quality_flags"] or w.samples.shape != (200000, 2, 2):
                    raise ValueError("invalid antenna samples")
                mid = w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                for rx in w.receiver_ids:
                    t = process_time()
                    proposals = receive(w.samples, rx, mid - 800000.0, mid + 800000.0)
                    v = process_time()
                    factors, status = verifier.factors(proposals, w.samples, rx)
                    cpu_s["acquisition"] += v - t
                    cpu_s["fractional"] += process_time() - v
                    if [f for f in factors if f["candidate_rank"] == 0] != first.pop((visit, rx)):
                        raise ValueError("first factor differs from frozen single-carrier output")
                    p = _probe(w, rx, factors)
                    old = original.pop((visit, rx))
                    if any(old[k] != val for k, val in p.items() if k != "candidates"):
                        raise ValueError("original observation metadata changed")
                    t = process_time()
                    pick, safe, votes = hint.select(p)
                    cpu_s["continuation"] += process_time() - t
                    rows["two_margin"].append(p)
                    for policy, index in (("causal_choice", pick), ("causal_withhold", safe)):
                        rows[policy].append(
                            dict(p, candidates=[] if index is None else [factors[index]])
                        )
                    counts.update(
                        dict(
                            probes=1,
                            proposed=len(proposals),
                            two_proposed=len(proposals) == 2,
                            verified=len(factors),
                            two_verified=len(factors) == 2,
                            causal_swaps=pick is not None
                            and factors[pick]
                            != max(
                                factors,
                                key=lambda f: (f["fractional_margin"], -f["candidate_rank"]),
                            ),
                            selective_admitted=safe is not None,
                        )
                    )
                    audit.write(
                        packed(
                            dict(
                                visit=visit,
                                rx=rx,
                                channel=p["channel"],
                                counter=acq["sample_start"],
                                iq=w.iq_sha256,
                                proposals=proposals,
                                checks=status,
                                verified=factors,
                                votes=votes,
                                causal_index=pick,
                                selective_index=safe,
                            )
                        )
                        + b"\n"
                    )
        finally:
            verifier.close()
    authority = recording_to_v5.digest([document["source"]["input_manifest_sha256"], signed])
    if (
        original
        or first
        or authority != previous["raw_authority"]
        or len(signed) != previous["recorded_visits"]
        or counts["probes"] != previous["tested_lanes"]
    ):
        raise ValueError("incomplete physical recording")
    path.with_suffix(".partial").replace(path)
    inputs = {
        policy: write_native(
            work, document, ident, policy, values, authority, previous["new_native_sha256"], lock
        )
        for policy, values in rows.items()
    }
    recording_to_v5.save(
        done,
        dict(
            case=ident,
            inputs=inputs,
            raw_authority=authority,
            recorded_visits=len(signed),
            excluded=len(exclusions),
            counts=counts,
            cpu_s=cpu_s,
            wall_s=perf_counter() - began,
            candidates_sha256=_sha(path),
            sources=lock,
        ),
    )
    return ident, dict(counts)


def solve(args):
    ident, policy, cpu, work = args
    os.sched_setaffinity(0, {cpu})
    directory = work / policy / ident
    receipt = read(work / "captures" / ident / "capture.json")["inputs"][policy]
    native = directory / "native.json"
    if _sha(native) != receipt["native_sha256"]:
        raise ValueError("candidate policy input changed")
    case = _load_case(ident)
    binding = directory / "binding.json"
    if not binding.exists():
        recording_to_v5.bind_request(case, native, directory / "basic.json")
        req = read(directory / "basic.json")
        req["job"]["identity"]["run_id"] = full_identity(ident, req)
        recording_to_v5.save(binding, req)
    request = read(binding)
    if (
        request["job"]["identity"]["run_id"] != full_identity(ident, request)
        or request["job"]["native_input"]["sha256"] != "sha256:" + receipt["native_sha256"]
    ):
        raise ValueError("v5 binding no longer matches candidate measurements")
    answer = directory / "prediction.json"
    if not answer.exists():
        public = dict(
            id=ident,
            panel=case["panel"],
            session_id=case["session_id"],
            regions=case["regions"],
            request_path=str(binding),
            native_path=str(native),
            native_sha256="sha256:" + receipt["native_sha256"],
        )
        prediction = original_v5.run(public, directory / "full-v5", "baseline")
        recording_to_v5.save(answer, prediction)
    p = read(answer)
    return ident, policy, p["status"], p.get("reason")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("acquire", "solve"))
    parser.add_argument("--case", nargs="+", default=CASES, choices=CASES)
    parser.add_argument("--policy", nargs="+", default=POLICIES, choices=POLICIES)
    parser.add_argument("--cpus", type=int, nargs="+", default=[0, 2, 4, 6, 7])
    parser.add_argument("--report", type=Path, default=OUT)
    parser.add_argument("--work", type=Path, default=WORK)
    a = parser.parse_args()
    if len(set(a.cpus)) != len(a.cpus) or not set(a.cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose distinct available cores")
    if a.action == "acquire":
        binaries = two_carrier.build(a.work)
        jobs = [
            (c, a.cpus[i % len(a.cpus)], a.report, a.work, binaries) for i, c in enumerate(a.case)
        ]
    else:
        pairs = [(c, p) for p in a.policy for c in a.case]
        jobs = [(c, p, a.cpus[i % len(a.cpus)], a.work) for i, (c, p) in enumerate(pairs)]
    with ProcessPoolExecutor(max_workers=len(a.cpus)) as pool:
        for result in pool.map(acquire if a.action == "acquire" else solve, jobs):
            print(*result, flush=True)
