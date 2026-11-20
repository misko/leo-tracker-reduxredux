"""Bind released complex beacon samples and isolate anonymous and assisted workers."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.io import loadmat, whosmat

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import bearing_transfer as model
from . import physical_transfer as authority
from .armijo_finish_results import pack
from .cold_missing import _sandbox
from .fresh_scenes import _destination
from .physical_differences import consolidate, simultaneous

OUT = ROOT / "reports/2026_11_19_receiver_screening/retry-and-transfer/bearing-transfer"
CAP, CPU = 40, (18, 19)
MODES = ("containing", "near-missing")
ARTIFACT = "positions.jsonl.gz"
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time

start, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (640 << 20, 640 << 20))
from tools.pipeline_eval.variants import bearing_transfer as m
request = json.load(sys.stdin)
assert set(request) == {'observation', 'catalogue', 'centre', 'labels'}
assert set(request['observation']) == {'clock', 'arcs'}
result = m.solve(request['observation'], request['catalogue'], request['centre'], request['labels'])
json.dump(dict(results=result, worker_wall_s=perf_counter()-start, cpu_s=process_time()-cpu,
               rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def observations(document):
    mats = document["main_tone_dict"].ravel()
    identity = [str(label.item()) for label in document["id_dict"].ravel()]
    if len(mats) != len(identity) or any(r.shape[1] != 5 or not np.iscomplexobj(r) for r in mats):
        raise ValueError("the verified field archive lacks the released complex array samples")
    arcs = [consolidate(r) for r in mats]
    _, overlaps = simultaneous(arcs)
    duplicates = set()
    for r in overlaps:
        if r["harmonic_like"]:
            duplicates.add(min(r["track_rows"], key=lambda k: (np.ptp(arcs[k][0]), -k)))
    kept = [dict(arc=i, pairs=model.secants(r)) for i, r in enumerate(mats) if i not in duplicates]
    summary = dict(
        authored_arcs=len(mats),
        raw_complex_rows=sum(len(x) for x in mats),
        potential_harmonic_duplicate_arcs=sorted(duplicates),
        admitted_phase_pairs=sum(len(a["pairs"]) for a in kept),
        exact_native_epochs=len(np.unique(np.concatenate([r[:, 0].real for r in mats]))),
    )
    return kept, identity, summary


def inspect_calibrations(root, capture):
    path = root / (capture["date"] + "-calibration.mat")
    raw = path.read_bytes()
    fields = whosmat(BytesIO(raw))
    variables = loadmat(BytesIO(raw))
    samples = variables["ref_sig_idx"][:, 0] / 2e6
    names = ("phase_offset_01", "phase_offset_21")
    return dict(
        date=capture["date"],
        calibration_sha256=digest(raw),
        fields=fields,
        reference_times=len(samples),
        phase_range_rad={k: float(np.ptp(np.unwrap(variables[k].ravel()))) for k in names},
        median_reference_gap_s=float(np.median(np.diff(samples))),
    )


def stage(raw_root, calibration_root):
    study = authority.STUDY
    receipt = read(study / "field-receipt.json")
    source = read(study / "field_private/source_provenance.json")
    routes = [
        {k: v[k] for k in ("pair", "condition", "id", "true_region")}
        for v in json.loads(authority._verified_truth(receipt))["cases"]
    ]
    offered = {r["pair"]: r for r in routes if r["condition"] == "present"}
    scopes, inventory, jobs = set(), [], []
    for recording in source["captures"]:
        route = offered[recording["pair"]]
        ident = route["id"]
        public = study / "public_field"
        q = json.loads(
            authority._read(
                public / "queries" / f"{ident}.json", receipt["public_query_sha256"][ident]
            )
        )
        meta = json.loads(
            authority._read(public / "observations" / f"{q['observation']}.json", q["observation"])
        )
        catalogue = authority._read(public / "orbits" / f"{q['catalog']}.tle", q["catalog"]).decode(
            "ascii"
        )
        (centre,) = (r["center"] for r in q["regions"] if r["id"] == route["true_region"])
        stamp = recording["date"]
        mat_bytes = authority._read(
            raw_root / stamp / "tracked_tones.mat", recording["track_file_sha256"]
        )
        document = loadmat(BytesIO(mat_bytes), variable_names=["main_tone_dict", "id_dict"])
        arcs, labels, summary = observations(document)
        clock = {
            k: meta[k]
            for k in ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s")
        }
        if clock["catalog_timestamp_ns"] > clock["cutoff_utc_ns"]:
            raise ValueError("future catalogue")
        site = recording["site_group"]
        repeat = site in scopes
        scopes.add(site)
        alias = f"{site}-{'repeat' if repeat else 'first'}"
        turn = int(digest(f"bearing-transfer-near-20261119/{recording['pair']}".encode())[:2], 16)
        near = _destination(centre, 26, np.pi / 2 * (turn % 4))
        summary.update(
            id=alias, site=site, date=stamp, repeated_site=repeat, native_sha256=digest(mat_bytes)
        )
        if calibration_root is not None:
            summary["hardware_only_calibration"] = inspect_calibrations(calibration_root, recording)
        inventory.append(summary)
        for mode, point in zip(MODES, (centre, near), strict=True):
            for assisted in (False, True):
                packet = dict(
                    observation=dict(clock=clock, arcs=arcs),
                    catalogue=catalogue,
                    centre=point,
                    labels=labels if assisted else None,
                )
                payload = encoded(packet)
                binding = dict(
                    id=f"{alias}-{mode}",
                    mode=mode,
                    author_id=assisted,
                    site=site,
                    repeat=repeat,
                    original_case_id=ident,
                    tile=dict(center=point, width_km=25),
                    native_sha256=summary["native_sha256"],
                    catalogue_sha256=q["catalog"],
                    measured_pairs_sha256=digest(encoded(arcs)),
                    input_sha256=digest(payload),
                )
                jobs.append((binding, payload))
    if len(inventory) != 11 or len(scopes) != 8 or len(jobs) != 44:
        raise ValueError("expected all eleven captures, eight physical sites and paired offers")
    return jobs, inventory, receipt["sealed_truth_sha256"]


def sources():
    module = ROOT / "tools/pipeline_eval"
    return [
        module / p
        for p in (
            "__init__.py",
            "reference/__init__.py",
            "reference/grid.py",
            "variants/__init__.py",
            "variants/peak_paths.py",
            "variants/bearing_transfer.py",
        )
    ]


def command(cpu):
    argv = _sandbox(cpu, [])
    for p in sources():
        argv[-4:-4] = ["--ro-bind", str(p), str(Path("/worker") / p.relative_to(ROOT))]
    argv[-1] = WORKER
    return ["nice", "-n", "10", *argv]


def attempt(cpu, binding, payload):
    start = perf_counter()
    try:
        p = subprocess.run(
            command(cpu), input=payload, capture_output=True, check=True, timeout=CAP
        )
        value = json.loads(p.stdout)
    except (OSError, subprocess.SubprocessError) as e:
        detail = (getattr(e, "stderr", None) or b"").decode(errors="replace")[-1500:]
        fail = dict(
            status="timed_out" if isinstance(e, subprocess.TimeoutExpired) else "failed",
            reason=detail or str(e),
            boundary=model.BOUNDARY,
            metrics={},
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
        value = dict(results=[fail, fail])
    elapsed = perf_counter() - start
    results = value.pop("results")
    rows = []
    for label, result in zip(model.METHODS, results, strict=True):
        validate_result(result)
        suffix = "_author_id" if binding["author_id"] else ""
        rows.append(
            binding | value | dict(method=label + suffix, result=result, elapsed_s=elapsed, cpu=cpu)
        )
    print(
        binding["id"],
        binding["author_id"],
        results[0]["status"],
        results[0]["metrics"].get("modeled_arcs"),
        round(elapsed, 2),
        flush=True,
    )
    return rows


def run(raw, calibration):
    staged, meta, truth = stage(raw, calibration)
    paths = [
        *sources(),
        Path(__file__),
        OUT / "PROTOCOL.md",
        authority.STUDY / "field-receipt.json",
        authority.STUDY / "field_private/source_provenance.json",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        Path(__file__).with_name("physical_differences.py"),
        Path(__file__).with_name("cold_missing.py"),
    ]
    frozen = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}
    save_json(OUT / "source-lock.json", frozen)
    save_json(
        OUT / "blind-plan.json",
        dict(cases=[r for r, _ in staged], scoring_truth_sha256=truth, cpus=CPU, deadline_s=CAP),
    )
    save_json(OUT / "measurement-inventory.json", dict(captures=meta))

    def batches(i):
        return [r for b, p in staged[i::2] for r in attempt(CPU[i], b, p)]

    with ThreadPoolExecutor(2) as pool:
        evaluated = [r for part in pool.map(batches, range(2)) for r in part]
    if any(digest((ROOT / p).read_bytes()) != h for p, h in frozen.items()):
        raise ValueError("source changed during the isolated replay")
    artifacts = ("blind-plan.json", "source-lock.json", "measurement-inventory.json")
    files = {p: digest((OUT / p).read_bytes()) for p in artifacts}
    files[ARTIFACT] = pack(OUT, ARTIFACT, evaluated)
    save_json(OUT / "prediction-lock.json", dict(files=files, calls=len(staged)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--calibration", type=Path)
    args = parser.parse_args()
    run(args.raw, args.calibration)
