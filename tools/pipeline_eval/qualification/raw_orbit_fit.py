"""Compare locked lean geometry fits on exactly the same ordinary-IQ-derived packets."""

import argparse
import gzip
import json
import os
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, references, save_json, write
from ..scoring import ARMS, distance_km, distribution
from ..variants import robust_em, robust_orbit_fit
from . import raw_robust, robust_orbit_fit_trials
from .full_v5_check import BULK, REPO, _load_case, _sha
from .prefix_figures import TIMING_IDS, csv_file

METHODS = (robust_em.METHOD, robust_orbit_fit.METHOD)
FILES = dict(zip(METHODS, ("control-positions.jsonl.gz", "positions.jsonl.gz"), strict=True))
COHORT = "ordinary-iq-factors"
ROOT = REPO / "reports/2026_11_19_receiver_convergence"
CHECK = raw_robust.REPORT / "raw-robust"


def prior_and_sources():
    lock = json.loads((CHECK / "prediction-lock.json").read_bytes())
    path = CHECK / "positions.jsonl.gz"
    if _sha(path) != lock["files"][path.name]:
        raise ValueError("published ordinary-lean control bytes changed")
    prior = read_predictions(path)
    sources = robust_orbit_fit_trials.locked_sources()
    expected = json.loads((ROOT / "track-fit/source-lock.json").read_bytes())
    if (
        sources != expected
        or lock["frozen_tracker"] != raw_robust.locked_sources()["frozen_tracker"]
    ):
        raise ValueError("exact geometry, lean control, or graph tracker differs from its lock")
    return prior, sources


def check_packet(observation, packet, previous, checksum, authority):
    observation_sha = sha256(corpus._packed(observation)).hexdigest()
    packet_sha = sha256(encoded(packet)).hexdigest()
    if (
        observation_sha != previous["observation_sha256"]
        or packet_sha != previous["input_sha256"]
        or authority != previous["capture_authority"]
        or checksum != previous["native_sha256"]
    ):
        raise ValueError("reconstructed ordinary tracks differ from the locked lean fit packet")
    return observation_sha


def execute(case_id, index, cpu, work, upstream, previous, sources):
    case = _load_case(case_id)
    started = perf_counter()
    directory = upstream / case_id if case_id in raw_robust.RAW_CASES else None
    path, checksum, provenance = raw_robust.bind_detector(case, "ordinary-native", directory)
    if case_id in raw_robust.RAW_CASES and not (
        provenance["replayed_here"] and provenance["exact_prior_native"]
    ):
        raise ValueError("the two smoke recordings require the fresh earlier IQ replay receipts")
    graph = raw_robust.build_tracks(case, path, checksum, cpu)
    observation = graph["projection"]
    (tile,) = case["regions"]
    catalogue = case["catalog"]
    element_path = BULK / catalogue["path"]
    if _sha(element_path) != catalogue["sha256"]:
        raise ValueError("causal catalogue changed")
    packet = dict(observation=observation, offer=tile, catalogue=element_path.read_text("ascii"))
    checked = check_packet(observation, packet, previous, checksum, graph["authority"])
    tracking_wall = perf_counter() - started
    binds = dict(
        native_sha256=checksum,
        observation_sha256=checked,
        catalog_sha256=catalogue["sha256"],
        capture_authority=graph["authority"],
        tracker_source_sha256=previous["tracker_source_sha256"],
        track_config_sha256=case["track_config"]["sha256"],
        tracker_wall_s=tracking_wall,
        tracker_metrics=graph["metrics"],
        acquired_in_this_measurement=False,
        upstream_iq_replay=provenance if provenance["replayed_here"] else None,
        variant="session-verified-iq-factor-reuse"
        if provenance["replayed_here"]
        else "qualified-ordinary-factor-reuse",
    )
    order = METHODS if index % 2 == 0 else METHODS[::-1]
    results = {
        m: robust_orbit_fit_trials.execute(
            m, case_id, COHORT, "matched-tile", packet, binds, cpu, sources
        )
        for m in order
    }
    lean = results[robust_em.METHOD]["result"]
    same = (
        lean["status"] == previous["result"]["status"]
        and lean["arms"] == previous["result"]["arms"]
    )
    for method, row in results.items():
        row["identical_prior_lean_result"] = same
        save_json(work / method / f"{case_id}.json", row)


def trial(work, upstream, cpus):
    if not set(cpus) <= os.sched_getaffinity(0) or len(set(cpus)) != len(cpus):
        raise ValueError("select distinct available CPUs")
    prior, sources = prior_and_sources()

    def lane(i):
        for index in range(i, len(TIMING_IDS), len(cpus)):
            case = TIMING_IDS[index]
            execute(case, index, cpus[i], work, upstream, prior[case], sources)

    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        list(pool.map(lane, range(len(cpus))))
    if robust_orbit_fit_trials.locked_sources() != sources:
        raise ValueError("fit implementations changed during paired inference")


def publish(work, output):
    prior, sources = prior_and_sources()
    pair = {
        m: [json.loads((work / m / f"{c}.json").read_bytes()) for c in TIMING_IDS] for m in METHODS
    }
    for case_id, lean, exact in zip(TIMING_IDS, *pair.values(), strict=True):
        if any(
            row["id"] != case_id
            or row["method"] != method
            or row["implementation_sha256"] != sources[method + ".py"]
            for row, method in zip((lean, exact), METHODS, strict=True)
        ):
            raise ValueError("fit receipt differs from the paired roster or locked code")
        for key in (
            "input_sha256",
            "native_sha256",
            "observation_sha256",
            "capture_authority",
            "track_config_sha256",
            "catalog_sha256",
            "tile",
        ):
            if not lean[key] == exact[key] == prior[case_id][key]:
                raise ValueError(f"fit pair differs from its common {key}")
    files = {}
    for method, rows in pair.items():
        compressed = gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
        write(output / FILES[method], compressed)
        files[FILES[method]] = sha256(compressed).hexdigest()
    save_json(output / "prediction-lock.json", dict(cases=TIMING_IDS, files=files, sources=sources))


def score(output):
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    records = {}
    for m, name in FILES.items():
        path = output / name
        if _sha(path) != lock["files"][name]:
            raise ValueError("fit predictions changed before scoring")
        records[m] = read_predictions(path)
    refs = {}
    for panel, prefix in (("ds26-common127", "DS26"), ("roof16", "DS29")):
        ids = [case for case in TIMING_IDS if case.startswith(prefix)]
        refs.update((r["id"], r) for r in references(panel, ids)[1])
    v5 = read_predictions(raw_robust.ORDINARY_RECEIPT.parent / "positions.jsonl.gz")
    rows = []
    for case_id in TIMING_IDS:
        for method in METHODS:
            row = records[method][case_id]
            for arm in ARMS:
                fitted = row["result"]["arms"][arm]
                truth = refs[case_id]["truth"]
                rows.append(
                    dict(
                        id=case_id,
                        method=method,
                        arm=arm,
                        status=row["result"]["status"],
                        error_km=distance_km(fitted["latlon"], truth),
                        forced_error_km=distance_km(fitted.get("forced_latlon"), truth),
                        conditional_rms_hz=fitted.get("rf_rms_hz"),
                        frequency_score=fitted.get("frequency_score"),
                        capture_v5_km=refs[case_id]["reference"]["baseline"][arm]["error_km"],
                        ordinary_v5_km=distance_km(
                            v5[case_id]["result"]["arms"][arm]["latlon"], truth
                        ),
                        fit_wall_s=row["worker_wall_s"],
                        tracker_wall_s=row["tracker_wall_s"],
                        fit_peak_rss_kib=row["max_rss_kib"],
                        scope=row["variant"],
                    )
                )
    csv_file(output / "scores.csv", rows)
    save_json(
        output / "summary.json",
        {
            m: {
                a: distribution(r["error_km"] for r in rows if r["method"] == m and r["arm"] == a)
                for a in ARMS
            }
            for m in METHODS
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cpus", nargs="+", type=int, default=(0, 1, 2, 3))
    args = parser.parse_args()
    work, output = local_output(args.work), local_output(args.out)
    trial(work, args.upstream, args.cpus)
    publish(work, output)
    score(output)


if __name__ == "__main__":
    main()
