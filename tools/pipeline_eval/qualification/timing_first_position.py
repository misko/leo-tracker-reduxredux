"""Feed a blind timing-first receiver's native measurements into the published v5 solver."""

import argparse
import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import process_time
from unittest.mock import patch

from .. import corpus
from ..scoring import distance_km
from ..variants import iq_stream
from ..variants import timing_first_receiver as portable
from . import original_v5, recording_to_v5
from .full_v5_check import BULK, _load_case, _probe, _sha, factor_candidate
from .original_kernel_trial import MAX_PREFIX
from .reverse_glrt_reference import ARMS, CASES, REPORT, digest, read_bound
from .reverse_glrt_report import literal, read, write_csv
from .reverse_glrt_search import WORK, Verifier
from .timing_first_roster import OUT
from .timing_first_trial import SCRATCH


def compatible_factor(proposed, verify):
    if proposed is None:
        return None, "withheld"
    integer = round(proposed["epoch"]) % 13333
    g = verify(integer, proposed["hz"])
    if not g["gate"]:
        return None, "fractional_gate_failed"
    if not literal(proposed, g):
        return None, "fractional_different_peak"
    offset = (g["epoch"] - integer + 6666.5) % 13333 - 6666.5
    return factor_candidate(
        0,
        integer,
        status="complete",
        offset=offset,
        cfo=g["hz"],
        exact=g["exact"],
        control=g["control"],
        margin=g["margin"],
    ), "passed"


def raw_windows(case, *, include_empty_visits=False):
    for loc in case["recording"]["segments"]:
        manifest = BULK / loc["path"]
        data = iq_stream._read_prefix(manifest, 65537)
        if digest(data) != loc["sha256"]:
            raise ValueError("recording segment manifest changed")
        policy = dict(recording_path=str(manifest), recording_sha256="sha256:" + loc["sha256"])
        for chunk in json.loads(data)["chunks"]:
            first = chunk["first_sequence"]
            with patch.multiple(
                iq_stream, MAX_CHUNK_PREFIX=MAX_PREFIX, MAX_DECODE_BYTES=MAX_PREFIX
            ):
                windows = iq_stream.load_windows(
                    policy,
                    range(first, first + chunk["window_count"]),
                    include_empty_visits=include_empty_visits,
                )
            yield from windows


def assemble(case, directory, binary, info, report):
    document = read_bound(case["native"])
    source = document["source"]
    excluded = {v["visit"]: v for v in document["provenance"]["excluded_windows"]}
    metadata = {
        (r["visit_index"], r["receiver_id"]): {k: v for k, v in r.items() if k != "candidates"}
        for r in source.pop("probes")
    }
    counts = Counter()
    signed = []
    probes = []
    proof = None
    cpu = 0.0
    try:
        with portable.Receiver(binary, info["edge"]) as receiver:
            for visit, w in enumerate(raw_windows(case)):
                acq = w.acquisition
                retune = json.loads(acq["retune_receipt"])
                if (
                    acq["global_visit"] != visit
                    or tuple(w.receiver_ids) != (0, 1)
                    or w.target["edge"] != info["edge"]
                    or w.sample_rate_hz != 10000000
                ):
                    raise ValueError("window order, RF edge or sampling authority changed")
                archived_clock = document["delivery_clocks"][visit]
                if any(
                    archived_clock.get(k) != v for k, v in retune["host_delivery_clock"].items()
                ):
                    raise ValueError("hardware delivery clock changed")
                if visit == 0 and retune["utc_clock_bracket"] != document["clock_anchor"]:
                    raise ValueError("recording UTC anchor changed")
                signed.append(w.iq_sha256)
                if visit in excluded:
                    e = excluded[visit]
                    if e["iq_sha256"] != w.iq_sha256 or e["sample_start"] != acq["sample_start"]:
                        raise ValueError("excluded hardware window changed")
                    continue
                if not acq["complete"] or acq["quality_flags"] or w.samples.shape != (200000, 2, 2):
                    raise ValueError("invalid capture in detector exposure")
                mid = w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                for rx in w.receiver_ids:
                    start = process_time()
                    proposed = receiver(w.samples, rx, mid - 800000.0, mid + 800000.0)
                    if proposed:
                        if proof is None:
                            proof = Verifier(
                                WORK / "portable-field.so", info["edge"], w.samples, rx
                            )
                        elif proof.lib.portable_verifier_load(proof.ctx, w.samples.ctypes.data, rx):
                            raise ValueError("fractional verifier failed to load current antenna")
                    factor, verdict = compatible_factor(proposed, proof)
                    cpu += process_time() - start
                    counts[verdict] += 1
                    row = _probe(w, rx, (factor,))
                    if {k: v for k, v in row.items() if k != "candidates"} != metadata.pop(
                        (visit, rx)
                    ):
                        raise ValueError("raw-to-v5 observation identity changed")
                    probes.append(row)
    finally:
        if proof is not None:
            proof.close()
    authority = recording_to_v5.digest([source["input_manifest_sha256"], signed])
    if (
        metadata
        or authority != source["raw_recording_authority_digest"]
        or len(signed) != case["recording"]["window_count"]
        or len(probes) != 2 * info["valid_visits"]
    ):
        raise ValueError("raw exposure differs from the complete authenticated recording")
    signature = recording_to_v5.digest(
        [authority, _sha(binary), _sha(WORK / "portable-field.so"), _sha(Path(__file__)), probes]
    )
    source.update(probes=probes, analysis_manifest_sha256=signature)
    document["provenance"].update(
        run_id="timing-first-" + signature[7:39],
        scope="ordinary timing-first acquisition with one native fractional validation",
        detector_sha256="sha256:" + _sha(binary),
        verifier_sha256="sha256:" + _sha(WORK / "portable-field.so"),
    )
    recording_to_v5.save(directory / "native.json", document)
    receipt = dict(
        case=case["id"],
        counts=counts,
        raw_authority=authority,
        recorded_visits=len(signed),
        tested_lanes=len(probes),
        capture_exclusions=len(excluded),
        detector_cpu_s=cpu,
        original_native_sha256=case["native"]["sha256"],
        new_native_sha256=_sha(directory / "native.json"),
        algorithm_source=_sha(Path(__file__)),
        protocol=_sha(report / "POSITION.md"),
        acquisition_sha256=_sha(binary),
        verifier_sha256=_sha(WORK / "portable-field.so"),
    )
    recording_to_v5.save(directory / "capture-receipt.json", receipt)


def full_identity(ident, request):
    binding = dict(
        case=ident,
        repetition=0,
        role="baseline",
        source=request["source"]["sha256"],
        native=request["native_manifest"],
        input=request["job"]["native_input"]["sha256"],
    )
    return "experiment-" + recording_to_v5.digest(binding)[7:47]


def run_one(args):
    ident, cpu, root, binary, out = args
    os.sched_setaffinity(0, {cpu})
    case = _load_case(ident)
    directory = root / "position" / ident
    directory.mkdir(exist_ok=True, parents=True)
    info = next(r for r in read(REPORT / "manifest.json")["cases"] if r["case"] == ident)
    if not (directory / "capture-receipt.json").exists():
        assemble(case, directory, binary, info, out)
    receipt = read(directory / "capture-receipt.json")
    if (
        receipt["new_native_sha256"] != _sha(directory / "native.json")
        or receipt["acquisition_sha256"] != _sha(binary)
        or receipt["protocol"] != _sha(out / "POSITION.md")
    ):
        raise ValueError("position input differs from capture receipt")
    parent = directory / "binding"
    parent.mkdir(exist_ok=True)
    basic = parent / "request.json"
    if not basic.exists():
        recording_to_v5.bind_request(case, directory / "native.json", basic)
    archived = read_bound(case["request"])
    if full_identity(ident, archived) != archived["job"]["identity"]["run_id"]:
        raise ValueError("original v5 experiment identity failed to reproduce")
    bound = read(basic)
    bound["job"]["identity"]["run_id"] = full_identity(ident, bound)
    binding = parent / "full-v5-request.json"
    if binding.exists():
        if read(binding) != bound:
            raise ValueError("full v5 identity no longer binds the frozen settings")
    else:
        recording_to_v5.save(binding, bound)
    public = dict(
        id=ident,
        panel=case["panel"],
        session_id=case["session_id"],
        regions=case["regions"],
        request_path=str(binding),
        native_path=str(directory / "native.json"),
        native_sha256="sha256:" + receipt["new_native_sha256"],
    )
    result_path = directory / "full-prediction.json"
    if not result_path.exists():
        print(
            "full raw recording authenticated, starting frozen v5",
            ident,
            dict(receipt["counts"]),
            flush=True,
        )
        prediction = original_v5.run(public, directory / "full-v5", "baseline")
        recording_to_v5.save(result_path, prediction)
    return ident, read(result_path)["status"]


def evaluate(out, work, ids, cpus):
    binary = portable.build(work)
    if len(set(cpus)) != len(cpus) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("supply distinct available CPU cores")
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        for item in pool.map(
            run_one, [(c, cpus[i % len(cpus)], work, binary, out) for i, c in enumerate(ids)]
        ):
            print(*item, flush=True)


def score(out, work, ids):
    records = []
    evidence = {}
    truth = {r["id"]: r["truth"] for r in corpus.references("ds26-all159")}
    bank = {r["case"]: r for r in read(REPORT / "manifest.json")["cases"]}
    for ident in ids:
        directory = work / "position" / ident
        case = _load_case(ident)
        worker = (BULK / case["request"]["path"]).with_name("worker-result.json")
        archived = read(worker)
        if recording_to_v5.digest(archived) != bank[ident]["worker_sha256"]:
            raise ValueError("archived position worker changed")
        raw = read(directory / "capture-receipt.json")
        original = original_v5._result(archived, None)
        fresh = read(directory / "full-prediction.json")
        inference = directory / "full-v5"
        request = read(inference / "experimental-request.json")
        baseline_request = read_bound(case["request"])
        if (
            request["job"]["native_input"]["sha256"] != "sha256:" + raw["new_native_sha256"]
            or request["job"]["evaluation_reference"] is not None
            or any(
                request[k] != baseline_request[k]
                for k in ("source", "model", "causal_snapshots", "policy", "native_manifest")
            )
            or any(
                request["job"][k] != baseline_request["job"][k]
                for k in ("track_config", "screen_center", "search_center")
            )
        ):
            raise ValueError("original v5 model, catalogue or position prior changed")
        integrity = None
        if fresh["status"] == "ok":
            integrity = read(inference / "validated-archive.json")
            if not integrity["validated"] or integrity["artifact"]["sha256"] != "sha256:" + _sha(
                inference / "experimental-evidence.zip"
            ):
                raise ValueError("full position output was not independently validated")
        evidence[ident] = dict(
            capture=raw,
            original_worker=bank[ident]["worker_sha256"],
            original_evidence=bank[ident]["archive_sha256"],
            new_inference=directory.name,
            new_request_sha256=recording_to_v5.digest(request),
            new_prediction_sha256=_sha(directory / "full-prediction.json"),
            new_status=fresh["status"],
            reason=fresh.get("reason"),
            log=str(inference / "v5-worker.log"),
            log_sha256=_sha(inference / "v5-worker.log"),
            validated_archive=integrity,
        )
        for method, result in (("original", original), ("timing_first_plus_fractional", fresh)):
            for arm in ARMS:
                p = result["arms"][arm]
                records.append(
                    dict(
                        case=ident,
                        method=method,
                        arm=arm,
                        status=result["status"],
                        reason=result.get("reason"),
                        latlon=p.get("latlon"),
                        error_km=distance_km(p.get("latlon"), truth[ident]),
                        rf_rms_hz=p.get("rf_rms_hz"),
                        frequency_score=result["metrics"].get(arm + "_frequency_score"),
                        associated_observations=result["metrics"].get(
                            arm + "_associated_observations"
                        ),
                        raw_authority=raw["raw_authority"],
                        native_sha256=raw[
                            "original_native_sha256"
                            if method == "original"
                            else "new_native_sha256"
                        ],
                        evidence_sha256=result.get("evidence", {}).get("sha256"),
                    )
                )
    write_csv(out / "positions.csv", records)
    (out / "position-evidence.json").write_text(
        json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("infer", "score"))
    p.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    p.add_argument("--cpus", nargs="+", type=int, default=[8, 10])
    p.add_argument("--report", type=Path, default=OUT)
    p.add_argument("--work", type=Path, default=SCRATCH)
    a = p.parse_args()
    if a.action == "infer":
        evaluate(a.report, a.work, a.cases, a.cpus)
    else:
        score(a.report, a.work, a.cases)
